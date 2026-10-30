import os
from contextlib import asynccontextmanager
from pathlib import Path

from fastapi import Depends, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, PlainTextResponse
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db import models  # noqa: F401  (register tables)
from app.db.models import Approval, AuditLog, Customer, CustomerUpdate, Message, Task, Vendor, VendorOutreach
from app.db.seed import seed
from app.db.session import Base, SessionLocal, engine, get_db
from app.llm.factory import build_llm
from app.metrics import unit_economics
from app.orchestrator import Orchestrator

CONSOLE = Path(__file__).resolve().parent.parent / "console" / "index.html"


@asynccontextmanager
async def lifespan(app: FastAPI):
    Base.metadata.create_all(engine)
    with SessionLocal() as db:
        seed(db)
    app.state.llm = build_llm()
    yield


app = FastAPI(title="TaskPilot", version="1.0.0", lifespan=lifespan)


def orch(request: Request, db: Session = Depends(get_db)) -> Orchestrator:
    return Orchestrator(db, request.app.state.llm)


class SimMessage(BaseModel):
    phone: str
    text: str
    name: str | None = None
    message_id: str | None = None


class Decision(BaseModel):
    item_type: str  # vendor_outreach | customer_update | plan
    item_id: int | None = None
    decision: str  # approved | edited | rejected
    approver: str = "ops"
    edited_text: str | None = None


class VendorReply(BaseModel):
    outreach_id: int
    reply: str


@app.get("/health")
def health():
    return {"status": "ok"}


@app.get("/", include_in_schema=False)
def console():
    return FileResponse(CONSOLE)


# ---------------- intake ----------------
@app.post("/sim/message")
def sim_message(m: SimMessage, o: Orchestrator = Depends(orch)):
    return o.handle_message(m.phone, m.text, m.message_id, m.name)


@app.get("/webhook/whatsapp", include_in_schema=False)
def webhook_verify(mode: str = Query(None, alias="hub.mode"), token: str = Query(None, alias="hub.verify_token"),
                   challenge: str = Query("", alias="hub.challenge")):
    if mode == "subscribe" and token == os.getenv("WA_VERIFY_TOKEN", "taskpilot-dev"):
        return PlainTextResponse(challenge)
    raise HTTPException(403, "bad verify token")


@app.post("/webhook/whatsapp")
async def webhook(request: Request, o: Orchestrator = Depends(orch)):
    """Meta Cloud API payload shape. Idempotent on the WhatsApp message id."""
    payload = await request.json()
    results = []
    for entry in payload.get("entry", []):
        for change in entry.get("changes", []):
            value = change.get("value", {})
            names = {c.get("wa_id"): c.get("profile", {}).get("name") for c in value.get("contacts", [])}
            for msg in value.get("messages", []):
                if msg.get("type") != "text":
                    continue
                results.append(o.handle_message(msg["from"], msg["text"]["body"], msg.get("id"), names.get(msg["from"])))
    return {"processed": len(results), "results": results}


@app.get("/sim/customers")
def sim_customers(db: Session = Depends(get_db)):
    return [{"id": c.id, "name": c.name, "plan": c.plan} for c in db.scalars(select(Customer))]


@app.get("/sim/history/{customer_id}")
def history(customer_id: int, db: Session = Depends(get_db)):
    rows = db.scalars(select(Message).where(Message.customer_id == customer_id).order_by(Message.id)).all()
    return [{"direction": m.direction, "text": m.body_redacted, "task_id": m.task_id,
             "at": m.created_at.isoformat()} for m in rows]


# ---------------- ops ----------------
def task_row(t: Task) -> dict:
    return {"id": t.id, "customer": t.customer.name, "customer_plan": t.customer.plan,
            "category": t.category.name if t.category else None, "status": t.status, "confidence": t.confidence,
            "risk_score": t.risk_score, "risk_reasons": t.risk_reasons, "complexity": t.complexity,
            "escalation_reason": t.escalation_reason, "created_at": t.created_at.isoformat()}


@app.get("/tasks")
def list_tasks(status: str | None = None, db: Session = Depends(get_db)):
    q = select(Task).order_by(Task.id.desc())
    if status:
        q = q.where(Task.status == status)
    return [task_row(t) for t in db.scalars(q)]


@app.get("/tasks/{task_id}")
def get_task(task_id: int, db: Session = Depends(get_db)):
    t = db.get(Task, task_id)
    if not t:
        raise HTTPException(404, "task not found")
    outreach = db.scalars(select(VendorOutreach).where(VendorOutreach.task_id == t.id)).all()
    updates = db.scalars(select(CustomerUpdate).where(CustomerUpdate.task_id == t.id)).all()
    msgs = db.scalars(select(Message).where(Message.task_id == t.id).order_by(Message.id)).all()
    audit = db.scalars(select(AuditLog).where(AuditLog.task_id == t.id).order_by(AuditLog.id)).all()
    approvals = db.scalars(select(Approval).where(Approval.task_id == t.id)).all()
    return {
        **task_row(t), "slots": t.slots, "missing_slots": t.missing_slots, "plan": t.plan, "shortlist": t.shortlist,
        "llm_cost_inr": t.llm_cost_inr, "human_minutes": t.human_minutes,
        "manual_baseline_minutes": t.manual_baseline_minutes,
        "outreach": [{"id": o.id, "vendor_id": o.vendor_id, "vendor": o.vendor.name, "draft": o.draft,
                      "draft_source": o.draft_source, "status": o.status, "reply_raw": o.reply_raw,
                      "reply_parsed": o.reply_parsed} for o in outreach],
        "customer_updates": [{"id": u.id, "draft": u.draft, "status": u.status} for u in updates],
        "messages": [{"direction": m.direction, "text": m.body_redacted} for m in msgs],
        "approvals": [{"item_type": a.item_type, "decision": a.decision, "approver": a.approver} for a in approvals],
        "audit": [{"id": a.id, "step": a.step, "model": a.model, "prompt_hash": a.prompt_hash,
                   "cost_inr": a.cost_inr, "latency_ms": a.latency_ms, "result": a.validator_result,
                   "output": a.output} for a in audit],
    }


def _guard(fn):
    try:
        return fn()
    except LookupError as e:
        raise HTTPException(404, str(e)) from e
    except ValueError as e:
        raise HTTPException(409, str(e)) from e


@app.post("/tasks/{task_id}/approve")
def approve(task_id: int, d: Decision, o: Orchestrator = Depends(orch)):
    t = _guard(lambda: o.decide(task_id, d.item_type, d.item_id, d.decision, d.approver, d.edited_text))
    return {"task_id": t.id, "status": t.status}


@app.post("/tasks/{task_id}/vendor-reply")
def vendor_reply(task_id: int, r: VendorReply, o: Orchestrator = Depends(orch)):
    t = _guard(lambda: o.vendor_reply(task_id, r.outreach_id, r.reply))
    return {"task_id": t.id, "status": t.status}


@app.post("/tasks/{task_id}/finish-manual")
def finish_manual(task_id: int, o: Orchestrator = Depends(orch)):
    t = _guard(lambda: o.finish_manual(task_id))
    return {"task_id": t.id, "status": t.status}


@app.post("/tasks/{task_id}/resolve")
def resolve(task_id: int, o: Orchestrator = Depends(orch)):
    t = _guard(lambda: o.resolve_escalation(task_id))
    return {"task_id": t.id, "status": t.status}


@app.get("/sla/breaches")
def sla(o: Orchestrator = Depends(orch)):
    return o.sla_breaches()


@app.get("/metrics/unit-economics")
def economics(db: Session = Depends(get_db)):
    return unit_economics(db)


@app.get("/vendors")
def vendors(db: Session = Depends(get_db)):
    return [{"id": v.id, "name": v.name, "rating": v.rating, "verified": v.verified} for v in db.scalars(select(Vendor))]
