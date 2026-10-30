import hashlib
import json
import re
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Protocol

PROMPT_DIR = Path(__file__).resolve().parent.parent / "prompts"

# INR per 1k tokens (in, out). Placeholder pricing: override via PRICE_TABLE_JSON for real providers.
DEFAULT_PRICES = {"fake-small": (0.02, 0.06), "fake-large": (0.25, 0.75)}


@dataclass
class LLMResponse:
    text: str
    model: str
    tokens_in: int
    tokens_out: int
    cost_inr: float
    latency_ms: float
    cached: bool = False


class LLMClient(Protocol):
    def complete(self, step: str, system: str, user: str, tier: str = "small") -> LLMResponse: ...


class LLMError(Exception):
    pass


def load_prompt(step: str) -> tuple[str, str]:
    """Return (prompt text, short hash). Prompts are versioned files; the hash goes in the audit log."""
    text = (PROMPT_DIR / f"{step}.v1.txt").read_text(encoding="utf-8")
    return text, hashlib.sha256(text.encode()).hexdigest()[:12]


def est_tokens(text: str) -> int:
    return max(1, len(text) // 4)


def price_for(model: str, tin: int, tout: int) -> float:
    import os

    table = dict(DEFAULT_PRICES)
    if os.getenv("PRICE_TABLE_JSON"):
        table.update({k: tuple(v) for k, v in json.loads(os.environ["PRICE_TABLE_JSON"]).items()})
    pin, pout = table.get(model, (0.1, 0.4))
    return round(tin / 1000 * pin + tout / 1000 * pout, 5)


def extract_json(text: str) -> dict:
    """Parse a JSON object out of model text (tolerates code fences / chatter)."""
    text = text.strip()
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        m = re.search(r"\{.*\}", text, re.S)
        if not m:
            raise LLMError("no JSON object in model output")
        try:
            return json.loads(m.group(0))
        except json.JSONDecodeError as e:
            raise LLMError(f"invalid JSON: {e}") from e


class CachingClient:
    """Cache by (model-tier, step, prompt) hash. Cached calls cost nothing."""

    def __init__(self, inner: LLMClient, force_tier: str | None = None):
        self.inner = inner
        self.force_tier = force_tier
        self._cache: dict[str, LLMResponse] = {}
        self.hits = 0

    def complete(self, step: str, system: str, user: str, tier: str = "small") -> LLMResponse:
        tier = self.force_tier or tier
        key = hashlib.sha256(f"{tier}|{step}|{system}|{user}".encode()).hexdigest()
        if key in self._cache:
            self.hits += 1
            r = self._cache[key]
            return LLMResponse(r.text, r.model, r.tokens_in, r.tokens_out, 0.0, 0.1, cached=True)
        t0 = time.perf_counter()
        r = self.inner.complete(step, system, user, tier)
        r.latency_ms = r.latency_ms or (time.perf_counter() - t0) * 1000
        self._cache[key] = r
        return r
