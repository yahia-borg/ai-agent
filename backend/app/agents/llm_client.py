import ast
import json
import logging
import re
from typing import Optional

from app.core.config import settings
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama

_repair_logger = logging.getLogger(__name__)


def _repair_and_parse(raw: str, schema: type):
    """
    Extract JSON from raw LLM output, repair common formatting errors produced
    by local vLLM models (mixed quotes, Python literals, nested confidence_score,
    extra $comment fields), then validate against *schema*.

    Repair sequence:
      1. Strip markdown code fences and find the outermost { … } block.
      2. Try json.loads directly.
      3. Normalise Python literals (None→null, True→true, False→false) and retry.
      4. Fall back to ast.literal_eval for fully single-quoted Python dict literals.
      5. Validate with schema.model_validate (field validators handle residual noise).
    """
    # 1. Extract the JSON block
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", raw, re.DOTALL)
    if fence:
        text = fence.group(1)
    else:
        start = raw.find("{")
        end = raw.rfind("}")
        text = raw[start : end + 1] if start != -1 and end > start else raw

    data = None

    # 2. Standard JSON parse
    try:
        data = json.loads(text)
    except (json.JSONDecodeError, ValueError):
        pass

    # 3. Normalise Python literals then retry JSON
    if data is None:
        norm = re.sub(r"\bNone\b", "null", text)
        norm = re.sub(r"\bTrue\b", "true", norm)
        norm = re.sub(r"\bFalse\b", "false", norm)
        try:
            data = json.loads(norm)
        except (json.JSONDecodeError, ValueError):
            pass

        # 4. ast.literal_eval handles fully single-quoted Python dict literals
        if data is None:
            py_text = re.sub(r"\bnull\b", "None", norm)
            py_text = re.sub(r"\btrue\b", "True", py_text)
            py_text = re.sub(r"\bfalse\b", "False", py_text)
            try:
                data = ast.literal_eval(py_text)
            except Exception:
                pass

    if data is None:
        raise ValueError(f"Cannot parse LLM response as JSON: {text[:300]}")

    _repair_logger.debug("Repaired JSON parsed successfully; validating against schema.")
    return schema.model_validate(data)


class LLMClient:
    """Unified LLM client that supports OpenAI, Anthropic, and Ollama"""

    def __init__(self, base_url_override: Optional[str] = None, model_override: Optional[str] = None,
                 max_tokens_override: Optional[int] = None,
                 extra_body_override: Optional[dict] = None,
                 stop_override: Optional[list] = None):
        self.provider = settings.LLM_PROVIDER.lower()
        self.model = model_override or settings.MODEL_NAME

        if self.provider == "openai":
            if not settings.RUNPOD_API_KEY:
                raise ValueError("RUNPOD_API_KEY not set in environment")

            base_url = base_url_override or settings.RUNPOD_BASE_URL
            if not base_url:
                _repair_logger.warning(
                    "LLM_PROVIDER=openai but no base_url configured (RUNPOD_BASE_URL is "
                    "empty) — requests will default to api.openai.com and likely fail with "
                    "the RunPod key. Set RUNPOD_BASE_URL to your vLLM endpoint."
                )

            kwargs = {
                "model": self.model,
                "temperature": 0.2,
                "api_key": settings.RUNPOD_API_KEY,
                "streaming": False,
                "top_p": 0.7,
                "frequency_penalty": 1.2,
                "max_tokens": max_tokens_override or 4096,
                "default_headers": {
                    "Authorization": f"Bearer {settings.RUNPOD_API_KEY}"
                }
            }
            if base_url:
                kwargs["base_url"] = base_url
            # Decoding guardrails (response/intro client). repetition_penalty is a
            # vLLM extra; stop sequences cut the known degeneration-leak markers
            # before they can spiral. Harmless against a real OpenAI endpoint.
            extra_body = dict(extra_body_override) if extra_body_override else {}
            # Disable the model's hidden reasoning trace — otherwise it consumes the
            # entire max_tokens budget and returns empty content (see LLM_DISABLE_THINKING).
            # Applies to every consumer of this client: response, intent, and the
            # structured-extraction path (with_structured_output binds on top of it).
            if settings.LLM_DISABLE_THINKING:
                extra_body.setdefault("chat_template_kwargs", {})["enable_thinking"] = False
            if extra_body:
                kwargs["extra_body"] = extra_body
            if stop_override:
                kwargs["stop"] = stop_override

            self.client = ChatOpenAI(**kwargs)
        elif self.provider == "anthropic":
            if not settings.ANTHROPIC_API_KEY:
                raise ValueError("ANTHROPIC_API_KEY not set in environment")
            self.client = ChatAnthropic(
                model=self.model,
                temperature=0.3,
                max_tokens=4096,  # Prevent negative token errors
                anthropic_api_key=settings.ANTHROPIC_API_KEY
            )
        elif self.provider == "ollama":
            # Ollama with optional authentication (e.g. Ollama Cloud / ngrok / proxy)
            kwargs = {
                "base_url": settings.OLLAMA_BASE_URL,
                "model": settings.OLLAMA_MODEL,
                "temperature": 0.3,
                "num_predict": 2048,  # Ollama uses num_predict instead of max_tokens
            }
            if settings.OLLAMA_API_KEY:
               kwargs["headers"] = {"Authorization": f"Bearer {settings.OLLAMA_API_KEY}"}
               
            self.client = ChatOllama(**kwargs)
        else:
            raise ValueError(f"Unsupported LLM provider: {self.provider}")
    
    async def invoke(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Invoke the LLM with a prompt"""
        from langchain_core.messages import SystemMessage, HumanMessage
        
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        
        response = await self.client.ainvoke(messages)
        return response.content

    async def invoke_structured(self, prompt: str, schema: type, system_prompt: Optional[str] = None):
        """Invoke the LLM and return structured output matching the schema (Pydantic model)."""
        from langchain_core.messages import SystemMessage, HumanMessage

        logger = logging.getLogger(__name__)

        messages: list = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))

        if self.provider == "openai":
            # Best practice (LangChain v1 + vLLM): use the provider's native structured
            # output via with_structured_output(method="json_schema"). On a vLLM OpenAI
            # server this maps to guided/constrained decoding, which enforces the schema
            # at the token level — far more reliable than free-form json_mode, including
            # for nested schemas (rooms[], etc.).
            try:
                structured_client = self.client.with_structured_output(
                    schema, method="json_schema"
                )
                result = await structured_client.ainvoke(messages + [HumanMessage(content=prompt)])
                # with_structured_output returns the parsed schema instance directly.
                return result if isinstance(result, schema) else schema.model_validate(result)
            except Exception as exc:
                logger.warning(
                    "json_schema structured output failed (%s); falling back to "
                    "json_mode + _repair_and_parse().", exc,
                )

            # Fallback for models/servers without json_schema support: force a JSON
            # object, then repair and validate manually via _repair_and_parse().
            schema_json = json.dumps(schema.model_json_schema(), indent=2)
            json_prompt = (
                f"{prompt}\n\n"
                "Respond ONLY with a valid JSON object that strictly matches this schema "
                "(no markdown, no extra keys, no single quotes):\n"
                f"{schema_json}"
            )
            messages.append(HumanMessage(content=json_prompt))
            json_client = self.client.bind(response_format={"type": "json_object"})
            response = await json_client.ainvoke(messages)
            raw = response.content if hasattr(response, "content") else str(response)
            logger.debug("Raw LLM response for structured output (first 500 chars): %s", raw[:500])
            return _repair_and_parse(raw, schema)

        # Anthropic / Ollama: use default tool-calling structured output
        messages.append(HumanMessage(content=prompt))
        structured_llm = self.client.with_structured_output(schema)
        return await structured_llm.ainvoke(messages)
    
    def invoke_sync(self, prompt: str, system_prompt: Optional[str] = None) -> str:
        """Synchronous version of invoke"""
        from langchain_core.messages import SystemMessage, HumanMessage
        
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        
        response = self.client.invoke(messages)
        return response.content


# Global LLM client instances
_llm_client: Optional[LLMClient] = None
_response_llm_client: Optional[LLMClient] = None


def get_llm_client() -> LLMClient:
    """Get or create LLM client singleton (used for tool calls)"""
    global _llm_client
    if _llm_client is None:
        _llm_client = LLMClient()
    return _llm_client


def get_response_llm_client() -> LLMClient:
    """
    Get or create a separate LLM client for final user-facing responses.
    Uses RESPONSE_LLM_BASE_URL if configured, otherwise falls back to the main client.
    """
    global _response_llm_client
    if _response_llm_client is not None:
        return _response_llm_client

    if settings.RESPONSE_LLM_BASE_URL:
        _response_llm_client = LLMClient(
            base_url_override=settings.RESPONSE_LLM_BASE_URL,
            model_override=settings.RESPONSE_LLM_MODEL or None,
            # The response client writes only short conversational turns / cost
            # intros (the BOQ table is rendered in code). A tight token cap plus a
            # repetition penalty and stop markers bound any degeneration loop.
            max_tokens_override=400,
            extra_body_override={"repetition_penalty": 1.1},
            stop_override=["\\text", "-->", "Self-correction", "(Self-correction"],
        )
        return _response_llm_client

    # No separate response LLM configured — use the main one
    return get_llm_client()
