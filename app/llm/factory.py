from app.core.config import settings
from app.llm.base import CachingClient


def build_llm(provider: str | None = None, force_tier: str | None = None) -> CachingClient:
    provider = provider or settings.llm_provider
    if provider == "anthropic":
        from app.llm.anthropic_provider import AnthropicLLM

        inner = AnthropicLLM()
    elif provider == "ollama":
        from app.llm.ollama_provider import OllamaLLM

        inner = OllamaLLM()
    else:
        from app.llm.fake import FakeLLM

        inner = FakeLLM()
    return CachingClient(inner, force_tier=force_tier)
