import os
from dataclasses import dataclass


@dataclass
class Settings:
    database_url: str = os.getenv("DATABASE_URL", "sqlite:///./taskpilot.db")
    llm_provider: str = os.getenv("LLM_PROVIDER", "fake")  # fake | anthropic
    llm_model_small: str = os.getenv("LLM_MODEL_SMALL", "fake-small")
    llm_model_large: str = os.getenv("LLM_MODEL_LARGE", "fake-large")
    task_cost_cap_inr: float = float(os.getenv("TASK_COST_CAP_INR", "5.0"))
    max_clarify_rounds: int = 2
    min_confidence: float = 0.45
    risk_review_threshold: float = 0.6
    ops_cost_per_minute_inr: float = float(os.getenv("OPS_COST_PER_MIN_INR", "3.0"))
    vendor_followup_minutes: int = 60
    # Cost-based routing: re-classify with the large model when the small model's confidence is below this (0 = off)
    cascade_below: float = float(os.getenv("CASCADE_BELOW", "0"))


settings = Settings()
