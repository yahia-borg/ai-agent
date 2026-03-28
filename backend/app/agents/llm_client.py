from typing import Optional
from app.core.config import settings
from langchain_openai import ChatOpenAI
from langchain_anthropic import ChatAnthropic
from langchain_ollama import ChatOllama


class LLMClient:
    """Unified LLM client that supports OpenAI, Anthropic, and Ollama"""

    def __init__(self, base_url_override: Optional[str] = None, model_override: Optional[str] = None,
                 max_tokens_override: Optional[int] = None):
        self.provider = settings.LLM_PROVIDER.lower()
        self.model = model_override or settings.MODEL_NAME

        if self.provider == "openai":
            if not settings.RUNPOD_API_KEY:
                raise ValueError("RUNPOD_API_KEY not set in environment")

            base_url = base_url_override or settings.RUNPOD_BASE_URL

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
        """Invoke the LLM and return structured output matching the schema (Pydantic model)"""
        from langchain_core.messages import SystemMessage, HumanMessage
        
        structured_llm = self.client.with_structured_output(schema)
        
        messages = []
        if system_prompt:
            messages.append(SystemMessage(content=system_prompt))
        messages.append(HumanMessage(content=prompt))
        
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
            max_tokens_override=1024,  # Response LLM: leave headroom for long conversations
        )
        return _response_llm_client

    # No separate response LLM configured — use the main one
    return get_llm_client()
