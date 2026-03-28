"""
Optimized graph builder: LLM Intent Router + Redis Cache + Dual-LLM ReAct.

Graph structure:
  START -> cache_check -> (HIT) -> END
                       -> (MISS) -> intent_classifier (8061)
                                      -> "response" -> response_node (8061) -> END
                                      -> "supervisor" -> supervisor_node (8021, tools)
                                                           -> tools -> supervisor (loop)
                                                           -> response_node (8061) -> END
"""
from typing import Dict, Any, Literal, Optional
from langgraph.graph import StateGraph, START, END
from langgraph.checkpoint.base import BaseCheckpointSaver
from langgraph.prebuilt import ToolNode
from langgraph.types import Command
from langchain_core.messages import BaseMessage, AIMessage, HumanMessage, ToolMessage, SystemMessage
import logging

from app.agents.state import QuotationAgentState
from app.agents.supervisor import SupervisorAgent, SUPERVISOR_TOOLS
from app.core.config import settings

logger = logging.getLogger(__name__)


# ─── Response Prompt (for 8061) ────────────────────────────────────────

RESPONSE_SYSTEM_PROMPT = """You are an expert Construction Finishing Advisor for the Egyptian market.
You work for a construction company. You ARE the advisor — not a middleman or referral service.

=== YOUR ROLE ===
You are the RESPONSE generator in a multi-agent system:
- A separate tool-calling agent gathers data and calculates costs using real database prices
- You ONLY format and present results, or ask follow-up questions to collect missing data
- You NEVER invent, estimate, or hallucinate prices, costs, or material rates
- If tool results contain cost data, present it clearly
- If no tool results exist yet, guide the user through data collection

=== DATA COLLECTION FLOW ===
When the user wants a quotation and data is still being gathered (Phase: GATHERING):
1. Ask for missing information ONE topic at a time:
   - Project type (apartment/villa/office/commercial)
   - Size in sqm (if not mentioned)
   - Current finish level (core shell / on plaster / semi-finished)
   - Target finish level (fully finished / luxury / etc.)
   - Room breakdown (bedrooms, bathrooms, kitchens, living areas)
2. Acknowledge what the user already provided
3. Do NOT provide cost estimates — wait for the calculation tools
4. Keep your response SHORT (3-5 sentences max). Just confirm and ask the next question.

=== ABSOLUTE PROHIBITIONS ===
- NEVER make up prices, cost ranges, or material rates (e.g. "35,000 to 70,000 EGP per sqm")
- NEVER say "consult a specialist" or "contact a contractor" or "استشارة متخصصين"
- NEVER suggest the user go somewhere else — YOU handle everything
- NEVER generate fake download links or URLs
- NEVER list materials, costs, or technical details unless they come from tool results
- NEVER give general construction advice or material recommendations unprompted
- If you don't have tool results with costs, just say you're preparing the quotation

=== WHAT TO DO INSTEAD ===
- If user provides project details → confirm receipt, ask for the NEXT missing piece
- If user asks for quotation → say you're calculating it (tools handle this)
- If cost data exists in conversation → present it in a clear table
- If user asks general question → answer briefly, stay focused on their project

=== LANGUAGE RULES ===
- ALWAYS respond in Egyptian Arabic (اللهجة المصرية العامية), regardless of what language the user writes in
- Even if the user writes in English, reply in Egyptian Arabic
- Use natural Egyptian dialect (e.g. "إيه", "عايز", "بتاع", "ازيك", "تمام") — not formal Modern Standard Arabic
- Numbers and prices must always be in Western digits: "125,000 EGP" (never Eastern Arabic ١٢٥٬٠٠٠)

=== OUTPUT FORMATTING (CRITICAL) ===
- ALWAYS use Western/English numerals (0-9), NEVER Eastern Arabic numerals (٠١٢٣٤٥٦٧٨٩)
- ALWAYS write prices in English format: "125,000 EGP" (comma for thousands, Western digits)
- NEVER use Arabic numerals like ۲۷,۰۰۰ or ٤٥,٠٠ٰ — always 27,000 or 45,000
- Markdown tables for cost breakdowns
- Keep responses concise and structured (max 10 lines unless presenting a cost table)

=== CONTEXT ===
Phase: {current_phase}
Quotation ID: {quotation_id}
"""


# ─── Routing Logic ─────────────────────────────────────────────────────

def should_continue(
    state: QuotationAgentState, max_iterations: Optional[int] = None
) -> Literal["continue", "end"]:
    """Determine if supervisor should loop (tools) or finish (response)."""
    max_iter = max_iterations or getattr(settings, "MAX_ITERATIONS", 15)
    messages = state.get("messages", [])
    if not messages:
        return "end"

    last_message = messages[-1]
    iteration = state.get("iteration_count", 0)

    if iteration >= max_iter:
        quotation_id = state.get("quotation_id", "unknown")
        logger.warning(
            f"Quotation {quotation_id} hit max iterations ({max_iter}). Force stopping."
        )
        return "end"

    if hasattr(last_message, "tool_calls") and last_message.tool_calls:
        return "continue"

    return "end"


# ─── Node: cache_check ─────────────────────────────────────────────────

async def cache_check_node(state: QuotationAgentState) -> Command:
    """
    Redis lookup for cached responses.
    If hit: inject cached response as AIMessage and route to END.
    If miss: route to intent_classifier.
    """
    from app.services.response_cache import get_response_cache

    messages = state.get("messages", [])
    if not messages:
        return Command(goto="intent_classifier")

    last_msg = messages[-1].content.strip() if hasattr(messages[-1], "content") else ""
    if not last_msg:
        return Command(goto="intent_classifier")

    cache = get_response_cache()
    try:
        cached = await cache.get_response(last_msg)
        if cached:
            logger.info(f"Cache HIT for: '{last_msg[:40]}'")
            return Command(
                goto="__end__",
                update={"messages": [AIMessage(content=cached)]},
            )
    except Exception as e:
        logger.warning(f"Cache check failed: {e}")

    return Command(goto="intent_classifier")


# ─── Node: supervisor ──────────────────────────────────────────────────

async def supervisor_node(
    state: QuotationAgentState, supervisor: SupervisorAgent
) -> Dict[str, Any]:
    """Run the Supervisor Agent (8021, tool-calling LLM)."""
    from app.core.structured_logging import log_tool_selection

    current_iteration = state.get("iteration_count", 0) + 1
    quotation_id = state.get("quotation_id", "unknown")
    session_id = state.get("session_id")
    phase = state.get("current_phase", "UNKNOWN")

    result = await supervisor.invoke(state)

    # Log tool selections
    messages = result.get("messages", [])
    if messages:
        last_message = messages[-1]
        if hasattr(last_message, "tool_calls") and last_message.tool_calls:
            for tool_call in last_message.tool_calls:
                tool_name = tool_call.get("name", "unknown")
                reasoning = (
                    last_message.content[:200]
                    if hasattr(last_message, "content") and last_message.content
                    else "Tool call from supervisor"
                )
                log_tool_selection(
                    quotation_id=quotation_id,
                    tool_name=tool_name,
                    reasoning=reasoning,
                    phase=phase,
                    session_id=session_id,
                    iteration=current_iteration,
                )

    return {"messages": result["messages"], "iteration_count": current_iteration}


# ─── Node: response ────────────────────────────────────────────────────

def _build_clean_messages(messages, system_prompt: str):
    """
    Build a clean user/assistant alternating message list from the full
    LangGraph history. The response LLM (vLLM) strictly requires:
    system, user, assistant, user, assistant, ...
    """
    # Step 1: Extract only user and assistant messages
    pairs = []
    for msg in messages:
        if isinstance(msg, SystemMessage):
            continue
        if isinstance(msg, ToolMessage):
            continue
        if isinstance(msg, AIMessage) and hasattr(msg, "tool_calls") and msg.tool_calls:
            continue
        if isinstance(msg, HumanMessage):
            content = msg.content.strip() if msg.content else ""
            if content:
                pairs.append(("user", content))
        elif isinstance(msg, AIMessage):
            content = msg.content.strip() if msg.content else ""
            # Filter out supervisor "DONE" signal — not user-facing
            if content and content.upper() != "DONE":
                pairs.append(("assistant", content))

    # Step 2: Merge consecutive same-role messages
    merged = []
    for role, content in pairs:
        if merged and merged[-1][0] == role:
            merged[-1] = (role, merged[-1][1] + "\n" + content)
        else:
            merged.append((role, content))

    # Step 3: Ensure it starts with user
    while merged and merged[0][0] == "assistant":
        merged.pop(0)

    # Step 4: Ensure strict alternation
    alternating = []
    expected_role = "user"
    for role, content in merged:
        if role == expected_role:
            alternating.append((role, content))
            expected_role = "assistant" if role == "user" else "user"
        else:
            if alternating and alternating[-1][0] == role:
                alternating[-1] = (role, alternating[-1][1] + "\n" + content)

    # Step 5: Ensure last message is user
    while alternating and alternating[-1][0] == "assistant":
        alternating.pop()

    # Step 6: Build final message list
    clean = [SystemMessage(content=system_prompt)]
    for role, content in alternating:
        if role == "user":
            clean.append(HumanMessage(content=content))
        else:
            clean.append(AIMessage(content=content))

    if len(clean) == 1:
        clean.append(HumanMessage(content="Please provide a summary of the quotation."))

    logger.debug(
        f"_build_clean_messages: {len(messages)} raw -> {len(clean)} clean "
        f"(roles: {[type(m).__name__[0] for m in clean]})"
    )
    return clean


async def response_node(
    state: QuotationAgentState, supervisor: SupervisorAgent
) -> Dict[str, Any]:
    """
    Generate final user-facing response using the response LLM (8061).
    Caches chat responses in Redis for future lookups.
    """
    from app.agents.llm_client import get_response_llm_client, get_llm_client
    from app.services.response_cache import get_response_cache

    response_client = get_response_llm_client()
    tool_client = get_llm_client()

    messages = state.get("messages", [])
    quotation_id = state.get("quotation_id", "unknown")
    current_phase = state.get("current_phase", "GATHERING")

    # Check if last AI message is a real response (not "DONE" or tool calls)
    def _has_usable_response(msgs):
        if not msgs:
            return False
        last = msgs[-1]
        if not isinstance(last, AIMessage):
            return False
        if hasattr(last, "tool_calls") and last.tool_calls:
            return False
        content = (last.content or "").strip()
        return bool(content) and content.upper() != "DONE"

    # If response LLM is same as tool LLM, skip re-generation only if
    # the last message is already a valid user-facing response
    if response_client is tool_client and _has_usable_response(messages):
        return {"messages": messages}

    try:
        # Collect the last significant tool result so the response LLM can see
        # the actual cost breakdown — ToolMessages are stripped by _build_clean_messages.
        tool_context_lines = []
        for msg in reversed(messages):
            if isinstance(msg, ToolMessage) and msg.content:
                content = str(msg.content)
                # Include cost calculation results and data collection summaries
                if any(kw in content for kw in ("Cost Calculation Complete", "total", "Data Extracted", "Missing Info", "Follow-up Needed")):
                    tool_context_lines.insert(0, content[:1500])
                    if len(tool_context_lines) >= 2:
                        break

        system_prompt = RESPONSE_SYSTEM_PROMPT.format(
            current_phase=current_phase,
            quotation_id=quotation_id,
        )
        if tool_context_lines:
            system_prompt += "\n\n=== LATEST TOOL RESULTS (use these to answer the user) ===\n" + "\n---\n".join(tool_context_lines)

        clean_messages = _build_clean_messages(messages, system_prompt)

        response = await response_client.client.ainvoke(clean_messages)

        # Cache the response for chat-type messages
        if messages:
            user_msg = None
            for m in reversed(messages):
                if isinstance(m, HumanMessage):
                    user_msg = m.content.strip()
                    break
            if user_msg and response.content:
                cache = get_response_cache()
                is_tool_flow = current_phase not in (None, "", "GATHERING")
                if not is_tool_flow and len(user_msg.split()) <= 10:
                    try:
                        await cache.set_response(user_msg, response.content)
                    except Exception:
                        pass

        # Replace or append the response
        new_messages = list(messages)
        if new_messages and isinstance(new_messages[-1], AIMessage):
            last = new_messages[-1]
            if not (hasattr(last, "tool_calls") and last.tool_calls):
                new_messages[-1] = response
            else:
                new_messages.append(response)
        else:
            new_messages.append(response)

        return {"messages": new_messages}

    except Exception as e:
        logger.warning(f"Response LLM failed, generating fallback: {e}")
        # Don't return "DONE" or empty — provide a safe fallback
        fallback = AIMessage(content="I'm here to help with your construction quotation. How can I assist you?")
        new_messages = list(messages)
        if new_messages and isinstance(new_messages[-1], AIMessage):
            new_messages[-1] = fallback
        else:
            new_messages.append(fallback)
        return {"messages": new_messages}


# ─── Graph Builder ─────────────────────────────────────────────────────

def build_supervisor_graph(
    checkpointer: BaseCheckpointSaver,
    supervisor: Optional[SupervisorAgent] = None,
    max_iterations: Optional[int] = None,
    use_start_edge: bool = True,
):
    """
    Build the optimized supervisor graph with intent routing and caching.

    Nodes: cache_check -> intent_classifier -> supervisor <-> tools -> response -> END
    """
    if supervisor is None:
        supervisor = SupervisorAgent()

    builder = StateGraph(QuotationAgentState)

    # ── Bind closures ──

    async def call_cache_check(state: QuotationAgentState):
        return await cache_check_node(state)

    async def call_intent_classifier(state: QuotationAgentState):
        from app.graph.intent_classifier import classify_intent
        return await classify_intent(state)

    async def call_supervisor(state: QuotationAgentState):
        return await supervisor_node(state, supervisor)

    async def call_response(state: QuotationAgentState):
        return await response_node(state, supervisor)

    def should_continue_bound(state: QuotationAgentState):
        return should_continue(state, max_iterations)

    # ── Add Nodes ──

    builder.add_node("cache_check", call_cache_check)
    builder.add_node("intent_classifier", call_intent_classifier)
    builder.add_node("supervisor", call_supervisor)
    builder.add_node("tools", ToolNode(SUPERVISOR_TOOLS))
    builder.add_node("response", call_response)

    # ── Edges ──

    # Entry: always start with cache check
    if use_start_edge:
        builder.add_edge(START, "cache_check")
    else:
        builder.set_entry_point("cache_check")

    # cache_check and intent_classifier use Command API for routing
    # (no explicit conditional edges needed — Command(goto=...) handles it)

    # Supervisor: if tool_calls -> tools, else -> response
    builder.add_conditional_edges(
        "supervisor",
        should_continue_bound,
        {"continue": "tools", "end": "response"},
    )

    # Tools always loop back to supervisor
    builder.add_edge("tools", "supervisor")

    # Response is terminal
    builder.add_edge("response", END)

    return builder.compile(checkpointer=checkpointer)
