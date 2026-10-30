from datetime import datetime, timezone

from sqlalchemy import JSON, Boolean, Float, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.session import Base


def utcnow() -> datetime:
    return datetime.now(timezone.utc).replace(tzinfo=None)


class Category(Base):
    __tablename__ = "categories"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(64), unique=True)
    required_slots: Mapped[list] = mapped_column(JSON, default=list)
    risk_default: Mapped[float] = mapped_column(Float, default=0.1)
    detailed: Mapped[bool] = mapped_column(Boolean, default=False)
    schema_version: Mapped[int] = mapped_column(Integer, default=1)


class Customer(Base):
    __tablename__ = "customers"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(80))
    phone_hash: Mapped[str] = mapped_column(String(64), unique=True)
    plan: Mapped[str] = mapped_column(String(10), default="mini")  # mini | premium
    plan_price: Mapped[float] = mapped_column(Float, default=399)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class CustomerPref(Base):
    __tablename__ = "customer_prefs"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    key: Mapped[str] = mapped_column(String(40))
    value: Mapped[str] = mapped_column(String(200))
    source_task_id: Mapped[int | None] = mapped_column(Integer, nullable=True)


class Task(Base):
    __tablename__ = "tasks"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    category_id: Mapped[int | None] = mapped_column(ForeignKey("categories.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="NEW")
    confidence: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_score: Mapped[float] = mapped_column(Float, default=0.0)
    risk_reasons: Mapped[list] = mapped_column(JSON, default=list)
    slots: Mapped[dict] = mapped_column(JSON, default=dict)
    missing_slots: Mapped[list] = mapped_column(JSON, default=list)
    plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    shortlist: Mapped[list] = mapped_column(JSON, default=list)
    complexity: Mapped[int] = mapped_column(Integer, default=1)
    clarify_rounds: Mapped[int] = mapped_column(Integer, default=0)
    escalation_reason: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)
    completed_at: Mapped[datetime | None] = mapped_column(nullable=True)
    human_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    manual_baseline_minutes: Mapped[float] = mapped_column(Float, default=0.0)
    llm_cost_inr: Mapped[float] = mapped_column(Float, default=0.0)

    category: Mapped[Category | None] = relationship()
    customer: Mapped[Customer] = relationship()


class Message(Base):
    __tablename__ = "messages"
    id: Mapped[int] = mapped_column(primary_key=True)
    customer_id: Mapped[int] = mapped_column(ForeignKey("customers.id"))
    task_id: Mapped[int | None] = mapped_column(ForeignKey("tasks.id"), nullable=True)
    direction: Mapped[str] = mapped_column(String(3))
    wa_message_id: Mapped[str | None] = mapped_column(String(80), unique=True, nullable=True)
    body_redacted: Mapped[str] = mapped_column(Text)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class Vendor(Base):
    __tablename__ = "vendors"
    id: Mapped[int] = mapped_column(primary_key=True)
    name: Mapped[str] = mapped_column(String(120))
    rating: Mapped[float] = mapped_column(Float)
    on_time_rate: Mapped[float] = mapped_column(Float)
    price_band: Mapped[int] = mapped_column(Integer)  # 1 budget, 2 mid, 3 premium
    contact: Mapped[str] = mapped_column(String(80))
    verified: Mapped[bool] = mapped_column(Boolean, default=True)
    last_verified_at: Mapped[datetime] = mapped_column(default=utcnow)


class VendorCategory(Base):
    __tablename__ = "vendor_categories"
    __table_args__ = (UniqueConstraint("vendor_id", "category_id"),)
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    category_id: Mapped[int] = mapped_column(ForeignKey("categories.id"))


class VendorArea(Base):
    __tablename__ = "vendor_areas"
    id: Mapped[int] = mapped_column(primary_key=True)
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    area: Mapped[str] = mapped_column(String(60))


class VendorOutreach(Base):
    __tablename__ = "vendor_outreach"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    vendor_id: Mapped[int] = mapped_column(ForeignKey("vendors.id"))
    draft: Mapped[str] = mapped_column(Text)
    draft_source: Mapped[str] = mapped_column(String(12), default="llm")  # llm | template
    status: Mapped[str] = mapped_column(String(12), default="drafted")
    reply_raw: Mapped[str | None] = mapped_column(Text, nullable=True)
    reply_parsed: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(nullable=True)
    replied_at: Mapped[datetime | None] = mapped_column(nullable=True)

    vendor: Mapped[Vendor] = relationship()


class CustomerUpdate(Base):
    __tablename__ = "customer_updates"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    draft: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(12), default="drafted")


class Approval(Base):
    __tablename__ = "approvals"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int] = mapped_column(ForeignKey("tasks.id"))
    item_type: Mapped[str] = mapped_column(String(24))
    item_id: Mapped[int] = mapped_column(Integer)
    decision: Mapped[str] = mapped_column(String(10))
    edited_diff: Mapped[str | None] = mapped_column(Text, nullable=True)
    approver: Mapped[str] = mapped_column(String(60))
    decided_at: Mapped[datetime] = mapped_column(default=utcnow)


class AuditLog(Base):
    __tablename__ = "audit_log"
    id: Mapped[int] = mapped_column(primary_key=True)
    task_id: Mapped[int | None] = mapped_column(Integer, nullable=True, index=True)
    step: Mapped[str] = mapped_column(String(40))
    model: Mapped[str | None] = mapped_column(String(60), nullable=True)
    prompt_hash: Mapped[str | None] = mapped_column(String(16), nullable=True)
    input_redacted: Mapped[str | None] = mapped_column(Text, nullable=True)
    output: Mapped[str | None] = mapped_column(Text, nullable=True)
    tokens_in: Mapped[int] = mapped_column(Integer, default=0)
    tokens_out: Mapped[int] = mapped_column(Integer, default=0)
    cost_inr: Mapped[float] = mapped_column(Float, default=0.0)
    latency_ms: Mapped[float] = mapped_column(Float, default=0.0)
    validator_result: Mapped[str | None] = mapped_column(String(200), nullable=True)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)


class EvalRun(Base):
    __tablename__ = "eval_runs"
    id: Mapped[int] = mapped_column(primary_key=True)
    git_sha: Mapped[str] = mapped_column(String(40))
    dataset_version: Mapped[str] = mapped_column(String(20))
    metrics: Mapped[dict] = mapped_column(JSON)
    created_at: Mapped[datetime] = mapped_column(default=utcnow)

