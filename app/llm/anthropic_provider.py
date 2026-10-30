"""Real provider. Needs ANTHROPIC_API_KEY. Same prompts and schemas as the fake provider."""
import os
import time

from app.llm.base import LLMError, LLMResponse, price_for


class AnthropicLLM:
    def __init__(self):
        import anthropic

        self.client = anthropic.Anthropic()
        self.models = {
            "small": os.getenv("LLM_MODEL_SMALL", "claude-haiku-5-5"),
            "large": os.getenv("LLM_MODEL_LARGE", "claude-sonnet-5-5"),
        }

    def complete(self, step: str, system: str, user: str, tier: str = "small") -> LLMResponse:
        model = self.models["large" if tier == "large" else "small"]
        t0 = time.perf_counter()
        try:
            msg = self.client.messages.create(
                model=model, max_tokens=800, temperature=0, system=system,
                messages=[{"role": "user", "content": user}],
            )
        except Exception as e:  # network / auth / rate limit: caller degrades to human
            raise LLMError(str(e)) from e
        text = "".join(b.text for b in msg.content if getattr(b, "type", "") == "text")
        tin, tout = msg.usage.input_tokens, msg.usage.output_tokens
        return LLMResponse(text, model, tin, tout, price_for(model, tin, tout), (time.perf_counter() - t0) * 1000)
