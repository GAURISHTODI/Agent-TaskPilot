from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.core.config import settings
from app.db.models import Approval, AuditLog, Customer, Task


def unit_economics(db: Session) -> dict:
    tasks = db.scalars(select(Task)).all()
    custs = {c.id: c for c in db.scalars(select(Customer))}
    per_customer: dict[int, dict] = {}
    for t in tasks:
        row = per_customer.setdefault(t.customer_id, {"tasks": 0, "llm": 0.0, "min": 0.0, "base": 0.0})
        row["tasks"] += 1
        row["llm"] += t.llm_cost_inr
        row["min"] += t.human_minutes
        row["base"] += t.manual_baseline_minutes
    subs, plans = [], {}
    for cid, r in per_customer.items():
        c = custs[cid]
        ops_cost = r["min"] * settings.ops_cost_per_minute_inr
        margin = c.plan_price - r["llm"] - ops_cost
        subs.append({"customer": c.name, "plan": c.plan, "plan_price": c.plan_price, "tasks": r["tasks"],
                     "llm_cost_inr": round(r["llm"], 3), "human_minutes": round(r["min"], 1),
                     "ops_cost_inr": round(ops_cost, 1), "contribution_margin_inr": round(margin, 1),
                     "unprofitable": margin < 0})
        p = plans.setdefault(c.plan, {"subscribers": 0, "margin_total": 0.0, "unprofitable": 0})
        p["subscribers"] += 1
        p["margin_total"] += margin
        p["unprofitable"] += margin < 0
    by_plan = {k: {"subscribers": v["subscribers"], "avg_margin_inr": round(v["margin_total"] / v["subscribers"], 1),
                   "unprofitable_subscribers": v["unprofitable"]} for k, v in plans.items()}
    n = len(tasks)
    by_state: dict[str, int] = {}
    for t in tasks:
        by_state[t.status] = by_state.get(t.status, 0) + 1
    decisions = db.execute(select(Approval.decision, func.count()).group_by(Approval.decision)).all()
    dec = dict(decisions)
    total_dec = sum(dec.values())
    done = [t for t in tasks if t.status in ("COMPLETED", "ESCALATED_TO_HUMAN") and t.manual_baseline_minutes > 0]
    return {
        "tasks": n,
        "tasks_by_state": by_state,
        "avg_llm_cost_per_task_inr": round(sum(t.llm_cost_inr for t in tasks) / n, 4) if n else 0,
        "avg_human_minutes_per_task_modelled": round(sum(t.human_minutes for t in done) / len(done), 2) if done else 0,
        "avg_manual_baseline_minutes_modelled": round(sum(t.manual_baseline_minutes for t in done) / len(done), 2) if done else 0,
        "escalation_rate": round(by_state.get("ESCALATED_TO_HUMAN", 0) / n, 3) if n else 0,
        "approval_edit_rate": round(dec.get("edited", 0) / total_dec, 3) if total_dec else 0,
        "injection_flags": db.scalar(select(func.count()).select_from(AuditLog)
                                     .where(AuditLog.step.like("guard_in%"), AuditLog.validator_result.like("injection:%"))) or 0,
        "blocked_tool_calls": db.scalar(select(func.count()).select_from(AuditLog)
                                        .where(AuditLog.step == "blocked_tool_call")) or 0,
        "by_plan": by_plan,
        "subscribers": sorted(subs, key=lambda s: s["contribution_margin_inr"]),
        "assumptions": {"ops_cost_per_minute_inr": settings.ops_cost_per_minute_inr,
                        "note": "Human minutes are MODELLED from per-category baselines and approval actions, "
                                "not measured. See docs/human-minutes-study.md."},
    }
