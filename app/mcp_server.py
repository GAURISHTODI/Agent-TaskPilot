"""MCP server exposing TaskPilot's READ-ONLY tools (vendor search, task lookup, preferences, economics).

Deliberately has no send / pay / book / approve tool: the same rule as the agent. Run:
    python -m app.mcp_server        (stdio transport; add to an MCP client config)
"""
from mcp.server.fastmcp import FastMCP
from sqlalchemy import select

from app.db import models as m
from app.db.session import SessionLocal
from app.metrics import unit_economics
from app.vendors.ranker import search_vendors as _search

mcp = FastMCP("taskpilot")


def _category_id(db, name: str) -> int:
    cid = db.scalar(select(m.Category.id).where(m.Category.name == name))
    if cid is None:
        raise ValueError(f"unknown category {name!r}")
    return cid


@mcp.tool()
def search_vendors(category: str, area: str | None = None, budget: str | None = None) -> list[dict]:
    """Ranked shortlist of VERIFIED vendors from the vendor table (never invented). Read-only."""
    with SessionLocal() as db:
        return _search(db, _category_id(db, category), area, budget)


@mcp.tool()
def list_tasks(status: str | None = None, limit: int = 20) -> list[dict]:
    """Recent tasks, optionally filtered by status (e.g. AWAITING_APPROVAL, ESCALATED_TO_HUMAN)."""
    with SessionLocal() as db:
        q = select(m.Task).order_by(m.Task.id.desc()).limit(limit)
        if status:
            q = q.where(m.Task.status == status)
        return [{"id": t.id, "status": t.status, "category": t.category.name if t.category else None,
                 "risk_score": t.risk_score, "slots": t.slots} for t in db.scalars(q)]


@mcp.tool()
def get_customer_prefs(customer_id: int) -> list[dict]:
    """Stored preferences for repeat requests. Read-only."""
    with SessionLocal() as db:
        return [{"key": p.key, "value": p.value} for p in
                db.scalars(select(m.CustomerPref).where(m.CustomerPref.customer_id == customer_id))]


@mcp.tool()
def unit_economics_summary() -> dict:
    """Cost per task, escalation rate and margin per subscriber (ops minutes are modelled, not measured)."""
    with SessionLocal() as db:
        return unit_economics(db)


if __name__ == "__main__":
    mcp.run()
