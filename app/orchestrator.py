"""Orchestrator: the LLM proposes, deterministic code verifies, a human approves anything that leaves the system."""
import re
from datetime import datetime, timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.agents import core_agents as ag
from app.agents.runner import Runner, StepFailed, audit
from app.agents.taxonomy import BY_NAME
from app.core.config import settings
from app.core.costs import CostCapExceeded
from app.core.state import ESC, BannedAction, ToolGate, ToolNotAllowed, check_transition
from app.db.models import (
    Approval,
    Category,
    Customer,
    CustomerPref,
    CustomerUpdate,
    Message,
    Task,
    Vendor,
    VendorOutreach,
    utcnow,
)
from app.guards.injection import scan
from app.guards.redaction import hash_phone, redact
from app.guards.validators import validate_vendor_ids
from app.llm.base import LLMClient
from app.vendors.ranker import search_vendors

# Modelled (NOT measured) ops effort in minutes; see docs/human-minutes-study.md for the real protocol.
MIN_APPROVE, MIN_EDIT, MIN_REJECT, MIN_REVIEW = 1.5, 4.0, 2.0, 2.0
ESCALATION_SHARE_OF_MANUAL = 0.6
REPEAT_RE = re.compile(r"\b(usual|same as (?:last time|before)|as always|my regular|same again)\b", re.I)


class Orchestrator:
    def __init__(self, db: Session, llm: LLMClient, *, injection_scan: bool = True):
        self.db, self.llm = db, llm
        self.injection_scan = injection_scan
        self.gate = ToolGate()
        self.cats = {c.id: c for c in db.scalars(select(Category))}
        self.cat_ids = {c.name: c.id for c in self.cats.values()}

    # ------------------------------------------------------------------ helpers
    def _status(self, task: Task, new: str) -> None:
        check_transition(task.status, new)
        audit(self.db, task.id, "transition", result=f"{task.status}->{new}")
        task.status = new

    def _escalate(self, task: Task, reason: str) -> None:
        if task.status == "COMPLETED":
            return
        self.gate.call(task.status, "escalate_to_human", lambda: None)
        base = BY_NAME[task.category.name].manual_minutes if task.category else 20
        task.human_minutes += round(base * ESCALATION_SHARE_OF_MANUAL, 1)
        task.manual_baseline_minutes = base
        task.escalation_reason = reason[:200]
        self._status(task, ESC)

    def _run_tools(self, task: Task, tool_requests: list, source: str) -> None:
        """Model-proposed tool calls go through the gate. Banned/unlisted ones raise and are recorded."""
        for tr in tool_requests:
            try:
                self.gate.call(task.status, tr.tool, lambda: None)
            except (BannedAction, ToolNotAllowed) as e:
                audit(self.db, task.id, "blocked_tool_call", result=f"{source}:{type(e).__name__}:{tr.tool}"[:190])

    def _scan(self, text: str) -> list[str]:
        return scan(text) if self.injection_scan else []

    def _context_text(self, task: Task) -> str:
        rows = self.db.scalars(select(Message).where(Message.task_id == task.id, Message.direction == "in")
                               .order_by(Message.id)).all()
        return "\n".join(m.body_redacted for m in rows)

    def _customer(self, phone: str, name: str | None) -> Customer:
        h = hash_phone(phone)
        c = self.db.scalar(select(Customer).where(Customer.phone_hash == h))
        if not c:
            c = Customer(name=name or "New customer", phone_hash=h, plan="mini", plan_price=399)
            self.db.add(c)
            self.db.flush()
        return c

    def _say(self, customer: Customer, task: Task | None, text: str) -> None:
        self.db.add(Message(customer_id=customer.id, task_id=task.id if task else None, direction="out",
                            body_redacted=redact(text)))

    # ------------------------------------------------------------------ intake
    def handle_message(self, phone: str, body: str, wa_message_id: str | None = None,
                       customer_name: str | None = None) -> dict:
        if wa_message_id and self.db.scalar(select(Message).where(Message.wa_message_id == wa_message_id)):
            prev = self.db.scalar(select(Message).where(Message.wa_message_id == wa_message_id))
            return {"duplicate": True, "task_id": prev.task_id}
        cust = self._customer(phone, customer_name)
        task = self.db.scalar(select(Task).where(Task.customer_id == cust.id, Task.status == "NEEDS_INFO")
                              .order_by(Task.id.desc()))
        continuation = task is not None
        if not task:
            task = Task(customer_id=cust.id, status="NEW")
            self.db.add(task)
            self.db.flush()
        self.db.add(Message(customer_id=cust.id, task_id=task.id, direction="in", wa_message_id=wa_message_id,
                            body_redacted=redact(body)))
        hits = self._scan(body)
        audit(self.db, task.id, "guard_in", input_text=body, result=("injection:" + ",".join(hits)) if hits else "clean")
        runner = Runner(self.db, self.llm, task)
        try:
            reply = self._pipeline(task, cust, runner, body, hits, continuation)
        except CostCapExceeded as e:
            self._escalate(task, f"cost_cap: {e}")
            reply = "Thanks! Our team is picking this up personally and will message you shortly."
        except StepFailed as e:
            self._escalate(task, f"model_failure: {e}")
            reply = "Thanks! Our team is picking this up personally and will message you shortly."
        self._say(cust, task, reply)
        self.db.commit()
        return {"duplicate": False, "task_id": task.id, "status": task.status, "reply": reply,
                "injection_flags": hits, "blocked_tools": list(self.gate.blocked)}

    # ------------------------------------------------------------------ pipeline
    def _pipeline(self, task: Task, cust: Customer, runner: Runner, body: str, hits: list[str],
                  continuation: bool) -> str:
        ESC_REPLY = "Thanks! Our team is picking this up personally and will message you shortly."
        if not continuation:
            c = ag.classify(runner, body)
            task.confidence = c.confidence
            if c.category == "unknown" or c.confidence < settings.min_confidence:
                task.category_id = self.cat_ids.get(c.category)
                self._status(task, "CLASSIFIED")
                self._escalate(task, f"low_confidence:{c.confidence}")
                return ESC_REPLY
            task.category_id = self.cat_ids[c.category]
            task.category = self.cats[task.category_id]
            self._status(task, "CLASSIFIED")
        cat = task.category or self.cats[task.category_id]
        task.category = cat
        spec = BY_NAME[cat.name]

        new = ag.extract_slots(runner, body, cat.name)
        slots = dict(task.slots or {})
        for k, v in new.items():
            if v:
                slots[k] = v
        if REPEAT_RE.search(body):  # F16: fill gaps from stored preferences
            for p in self.gate.call(task.status, "get_customer_prefs", lambda: self.db.scalars(
                    select(CustomerPref).where(CustomerPref.customer_id == cust.id))):
                cat_name, _, slot = p.key.partition(".")
                if cat_name == cat.name and not slots.get(slot):
                    slots[slot] = p.value
                    audit(self.db, task.id, "pref_fill", result=p.key)
        task.slots = slots
        task.missing_slots = ag.missing_required(cat.name, slots)

        context = self._context_text(task)
        task.risk_score, task.risk_reasons = ag.score_risk(runner, context, cat.name, slots.get("budget"), hits)
        if hits:  # quarantine: injected text never reaches the planner/drafter
            self._escalate(task, "prompt_injection_quarantined")
            return ESC_REPLY

        risky = task.risk_score >= settings.risk_review_threshold
        if task.missing_slots and risky:  # humans handle risky tasks from the start; no bot Q&A first
            self._escalate(task, "risk_review:" + ",".join(task.risk_reasons))
            return ESC_REPLY
        if task.missing_slots:
            if task.clarify_rounds >= settings.max_clarify_rounds:
                self._escalate(task, "clarification_limit_reached")
                return ESC_REPLY
            task.clarify_rounds += 1
            q = ag.clarify(runner, cat.name, task.missing_slots)
            if task.status != "NEEDS_INFO":
                self._status(task, "NEEDS_INFO")
            return q

        self._status(task, "READY_TO_PLAN")
        plan = ag.plan(runner, cat.name, slots, context)
        self._status(task, "PLANNED")
        self._run_tools(task, plan.tool_requests, "planner")
        task.plan = {"steps": [s.model_dump() for s in plan.steps]}
        task.manual_baseline_minutes = spec.manual_minutes
        task.complexity = ag.complexity(slots.get("budget"), task.risk_score, task.clarify_rounds, spec.needs_vendor)

        if risky:
            self._escalate(task, "risk_review:" + ",".join(task.risk_reasons))
            return ESC_REPLY

        if spec.needs_vendor:
            shortlist = self.gate.call(task.status, "search_vendors", search_vendors, self.db, cat.id,
                                       slots.get("where"), slots.get("budget"))
            safe = []
            for v in shortlist:  # vendor names are data too
                if self._scan(v["name"]):
                    audit(self.db, task.id, "vendor_dropped", result=f"injection_in_vendor_name:{v['vendor_id']}")
                else:
                    safe.append(v)
            task.shortlist = safe
            if not safe:
                self._escalate(task, "no_verified_vendor_for_area")
                return ESC_REPLY
            db_ids = {i for (i,) in self.db.execute(select(Vendor.id).where(Vendor.verified.is_(True)))}
            ok, why = validate_vendor_ids([v["vendor_id"] for v in safe], db_ids, {v["vendor_id"] for v in safe})
            audit(self.db, task.id, "guard_out_vendors", result=why)
            if not ok:
                self._escalate(task, f"vendor_validation_failed:{why}")
                return ESC_REPLY
            allowed_names = {v["name"] for v in safe}
            for v in safe:
                draft, source, vres = self.gate.call(task.status, "draft_vendor_message", ag.draft_vendor_message,
                                                     runner, v, cat.name, slots, context, allowed_names)
                audit(self.db, task.id, "guard_out_draft", result=f"vendor={v['vendor_id']} source={source} {vres}"[:190])
                self.db.add(VendorOutreach(task_id=task.id, vendor_id=v["vendor_id"], draft=draft, draft_source=source))
        self.gate.call(task.status, "request_approval", lambda: None)
        self._status(task, "AWAITING_APPROVAL")
        return "Got it! Our team is lining up options and will confirm with you shortly."

    # ------------------------------------------------------------------ approvals (human actions)
    def decide(self, task_id: int, item_type: str, item_id: int | None, decision: str, approver: str,
               edited_text: str | None = None) -> Task:
        if decision not in ("approved", "edited", "rejected"):
            raise ValueError("decision must be approved|edited|rejected")
        task = self.db.get(Task, task_id)
        if not task:
            raise LookupError("task not found")
        minutes = {"approved": MIN_APPROVE, "edited": MIN_EDIT, "rejected": MIN_REJECT}[decision]
        diff = None
        if item_type == "vendor_outreach":
            o = self.db.get(VendorOutreach, item_id)
            if not o or o.task_id != task.id or o.status != "drafted":
                raise ValueError("outreach not pending")
            if task.status != "AWAITING_APPROVAL" and task.status != "AWAITING_VENDOR":
                raise ValueError(f"task in {task.status}")
            if decision == "rejected":
                o.status = "rejected"
            else:
                if decision == "edited":
                    if not edited_text:
                        raise ValueError("edited text required")
                    diff = f"-{o.draft}\n+{edited_text}"
                    o.draft = edited_text
                o.status, o.sent_at = "sent", utcnow()  # the human approval IS the send; the LLM never sends
                if task.status == "AWAITING_APPROVAL":
                    self._status(task, "IN_EXECUTION")
                    self._status(task, "AWAITING_VENDOR")
            pending = self.db.scalars(select(VendorOutreach).where(VendorOutreach.task_id == task.id,
                                                                   VendorOutreach.status.in_(["drafted", "sent", "replied"]))).all()
            if not pending:
                self._escalate(task, "all_outreach_rejected")
        elif item_type == "customer_update":
            u = self.db.get(CustomerUpdate, item_id)
            if not u or u.task_id != task.id or u.status != "drafted":
                raise ValueError("update not pending")
            if decision == "rejected":
                u.status = "rejected"
            else:
                if decision == "edited":
                    if not edited_text:
                        raise ValueError("edited text required")
                    diff = f"-{u.draft}\n+{edited_text}"
                    u.draft = edited_text
                u.status = "sent"
                self._say(task.customer, task, u.draft)
                self._complete(task)
        elif item_type == "plan":
            if task.status != "AWAITING_APPROVAL":
                raise ValueError(f"task in {task.status}")
            if decision == "rejected":
                self._escalate(task, "plan_rejected")
            else:
                self._status(task, "IN_EXECUTION")
                self._status(task, "AWAITING_VENDOR")
        else:
            raise ValueError("unknown item_type")
        task.human_minutes += minutes
        self.db.add(Approval(task_id=task.id, item_type=item_type, item_id=item_id or 0, decision=decision,
                             edited_diff=diff, approver=approver))
        audit(self.db, task.id, "approval", result=f"{item_type}:{item_id}:{decision}:{approver}")
        self.db.commit()
        return task

    def _complete(self, task: Task) -> None:
        self._status(task, "COMPLETED")
        task.completed_at = utcnow()
        for k in ("where", "budget"):  # remember preferences for repeat requests
            if task.slots.get(k) and task.category:
                self.db.add(CustomerPref(customer_id=task.customer_id, key=f"{task.category.name}.{k}",
                                         value=str(task.slots[k]), source_task_id=task.id))

    def finish_manual(self, task_id: int, approver: str = "ops") -> Task:
        """Non-vendor tasks (e.g. payments): the human does the action, the agent drafts the confirmation."""
        task = self.db.get(Task, task_id)
        if task.status not in ("AWAITING_VENDOR", "IN_EXECUTION"):
            raise ValueError(f"task in {task.status}")
        runner = Runner(self.db, self.llm, task)
        text = self.gate.call(task.status, "draft_customer_update", ag.draft_customer_update, runner,
                              {"vendor": "Our team", "price": None, "available": None, "slot": None})
        self.db.add(CustomerUpdate(task_id=task.id, draft=text))
        self._status(task, "CUSTOMER_UPDATE_DRAFTED")
        task.human_minutes += 6
        self.db.commit()
        return task

    # ------------------------------------------------------------------ vendor reply
    def vendor_reply(self, task_id: int, outreach_id: int, reply_text: str) -> Task:
        task = self.db.get(Task, task_id)
        o = self.db.get(VendorOutreach, outreach_id)
        if not task or not o or o.task_id != task.id or o.status != "sent" or task.status != "AWAITING_VENDOR":
            raise ValueError("outreach not awaiting a reply")
        o.reply_raw, o.replied_at, o.status = redact(reply_text), utcnow(), "replied"
        hits = self._scan(reply_text)
        audit(self.db, task.id, "guard_in_vendor_reply", input_text=reply_text,
              result=("injection:" + ",".join(hits)) if hits else "clean")
        runner = Runner(self.db, self.llm, task)
        try:
            parsed = ag.parse_vendor_reply(runner, reply_text)
        except (StepFailed, CostCapExceeded) as e:
            self._escalate(task, f"reply_parse_failed:{e}")
            self.db.commit()
            return task
        self._run_tools(task, parsed.tool_requests, "vendor_reply")
        o.reply_parsed = parsed.model_dump(exclude={"tool_requests"})
        if hits:
            task.risk_reasons = sorted(set(task.risk_reasons + ["injection_in_vendor_reply"]))
            self._escalate(task, "injection_in_vendor_reply")
            self.db.commit()
            return task
        try:
            text = self.gate.call(task.status, "draft_customer_update", ag.draft_customer_update, runner,
                                  {"vendor": o.vendor.name, "price": parsed.price, "available": parsed.available,
                                   "slot": parsed.slot})
        except CostCapExceeded as e:
            self._escalate(task, f"cost_cap: {e}")
            self.db.commit()
            return task
        self.db.add(CustomerUpdate(task_id=task.id, draft=text))
        self._status(task, "CUSTOMER_UPDATE_DRAFTED")
        self.db.commit()
        return task

    def resolve_escalation(self, task_id: int, approver: str = "ops") -> Task:
        task = self.db.get(Task, task_id)
        if task.status != ESC:
            raise ValueError("not escalated")
        self._status(task, "COMPLETED")
        task.completed_at = utcnow()
        audit(self.db, task.id, "approval", result=f"escalation_resolved:{approver}")
        self.db.commit()
        return task

    # ------------------------------------------------------------------ SLA (F13)
    def sla_breaches(self, now: datetime | None = None) -> list[dict]:
        now = now or utcnow()
        cutoff = now - timedelta(minutes=settings.vendor_followup_minutes)
        rows = self.db.scalars(select(VendorOutreach).where(VendorOutreach.status == "sent",
                                                            VendorOutreach.sent_at < cutoff)).all()
        return [{"task_id": o.task_id, "outreach_id": o.id, "vendor": o.vendor.name,
                 "minutes_waiting": int((now - o.sent_at).total_seconds() // 60)} for o in rows]
