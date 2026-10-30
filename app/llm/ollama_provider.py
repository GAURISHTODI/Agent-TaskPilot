"""Local, free provider via Ollama's HTTP API. Same prompts and schemas as the other providers.

Env: OLLAMA_HOST (default http://localhost:11434), OLLAMA_MODEL_SMALL, OLLAMA_MODEL_LARGE.
Cost is reported as 0 (local compute); latency is real.
"""
import os
import time

import httpx

from app.llm.base import LLMError, LLMResponse


class OllamaLLM:
    def __init__(self):
        self.host = os.getenv("OLLAMA_HOST", "http://localhost:11434").rstrip("/")
        self.models = {
            "small": os.getenv("OLLAMA_MODEL_SMALL", "qwen2.5:1.5b"),
            "large": os.getenv("OLLAMA_MODEL_LARGE", "qwen2.5:3b"),
        }
        self.timeout = float(os.getenv("OLLAMA_TIMEOUT", "300"))

    def complete(self, step: str, system: str, user: str, tier: str = "small") -> LLMResponse:
        model = self.models["large" if tier == "large" else "small"]
        t0 = time.perf_counter()
        try:
            r = httpx.post(f"{self.host}/api/chat", timeout=self.timeout, json={
                "model": model, "stream": False, "format": "json",
                "options": {"temperature": 0, "seed": 0, "num_predict": 400},
                "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
            })
            r.raise_for_status()
            body = r.json()
        except Exception as e:
            raise LLMError(f"ollama: {e}") from e
        text = body.get("message", {}).get("content", "")
        return LLMResponse(text, f"ollama/{model}", body.get("prompt_eval_count", 0), body.get("eval_count", 0),
                           0.0, (time.perf_counter() - t0) * 1000)
