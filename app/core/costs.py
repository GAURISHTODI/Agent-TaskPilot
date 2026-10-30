from app.core.config import settings


class CostCapExceeded(Exception):
    pass


def check_cap(spent_inr: float, cap: float | None = None) -> None:
    cap = settings.task_cost_cap_inr if cap is None else cap
    if spent_inr > cap:
        raise CostCapExceeded(f"task LLM spend ₹{spent_inr:.3f} exceeds cap ₹{cap:.2f}")
