# Architecture and Data Model

## 1. System overview

```
 Customer (WhatsApp / Simulator)
        │  webhook (POST /webhook/whatsapp)
        ▼
┌──────────────────────────────────────────────────────────────┐
│ FastAPI backend                                              │
│                                                              │
│  Ingest ──► Guard-in ──► Orchestrator (state machine)        │
│  (dedupe,   (PII redact,   │                                 │
│   idempotency) injection   ├─ Classifier   (LLM, schema)     │
│                scan)       ├─ Slot Extractor (LLM, schema)   │
│                            ├─ Clarifier     (LLM)            │
│                            ├─ Planner       (LLM, schema)    │
│                            ├─ Vendor Ranker (SQL + scoring)  │
│                            ├─ Drafter       (LLM)            │
│                            └─ Risk Scorer   (rules + LLM)    │
│                                  │                           │
│                          Guard-out (validators, allowlist)   │
│                                  │                           │
│               Approval queue ◄───┘                           │
└──────────┬───────────────────────────────┬───────────────────┘
           │                               │
      PostgreSQL / Redis            Ops Console + Dashboard
   (tasks, vendors, audit)          (React or Streamlit)
```

**Core principle:** the LLM proposes, deterministic code verifies, a human approves anything that leaves the system.

## 2. Task state machine

```
NEW → CLASSIFIED → NEEDS_INFO ⇄ READY_TO_PLAN → PLANNED → AWAITING_APPROVAL
    → IN_EXECUTION → AWAITING_VENDOR → CUSTOMER_UPDATE_DRAFTED → COMPLETED
                    └→ ESCALATED_TO_HUMAN (reachable from any state)
```
Tool permissions are tied to state. For example, the Drafter can run only in `PLANNED`, and nothing can "send" except the approval action.

## 3. Components

| Component | Responsibility | Implementation notes |
|---|---|---|
| Ingest | Receive messages, dedupe by message ID, store raw message | Idempotency key on WhatsApp message ID |
| Guard-in | Redact phone numbers, addresses, card-like numbers in logs and prompts; detect injection patterns | Regex plus a small classifier prompt. Redacted text is what the logs store |
| Classifier | Category and confidence from a fixed taxonomy | Structured output; low confidence goes to a human |
| Slot Extractor | Fill the category's typed schema | Pydantic models per category, with `null` allowed, never guess |
| Clarifier | One consolidated question for missing required slots | Capped at 2 rounds, then escalate |
| Planner | Ordered steps with owner and effort estimate | Schema-validated |
| Vendor Ranker | Shortlist from the DB | SQL filter plus score: area match, rating, past on-time rate, price band. **No LLM here** |
| Drafter | Outreach and customer-update drafts | Templates plus LLM polish with a quality gate (fallback to template) |
| Risk Scorer | Flag high spend, health, legal, payment, or ambiguous tasks | Rules first, LLM second opinion |
| Guard-out | Validate every output | Schema check, vendor-ID-in-DB check, banned-action check, budget cap check |
| Approval queue | Human approve, edit, reject | Single source of truth for anything outward-facing |
| Dashboard | Unit economics and quality | Reads from the audit and cost tables |

## 4. Data model (PostgreSQL)

```sql
customers(id, name_enc, phone_hash, plan ENUM('mini','premium'), plan_price, created_at)
customer_prefs(id, customer_id, key, value, source_task_id)

messages(id, customer_id, task_id, direction ENUM('in','out'),
         wa_message_id UNIQUE, body_redacted, created_at)

tasks(id, customer_id, category_id, status, confidence, risk_score, risk_reasons JSONB,
      slots JSONB, missing_slots JSONB, plan JSONB, complexity SMALLINT,
      created_at, completed_at, human_minutes NUMERIC, llm_cost_inr NUMERIC)

categories(id, name, required_slots JSONB, risk_default, schema_version)

vendors(id, name, category_ids INT[], areas TEXT[], rating, on_time_rate,
        price_band, contact_enc, verified BOOL, last_verified_at)

vendor_outreach(id, task_id, vendor_id, draft, status ENUM('drafted','approved','sent','replied','no_reply'),
                reply_raw, reply_parsed JSONB, sent_at, replied_at)

approvals(id, task_id, item_type, item_id, decision ENUM('approved','edited','rejected'),
          edited_diff, approver, decided_at)

audit_log(id, task_id, step, model, prompt_hash, input_redacted, output, tokens_in, tokens_out,
          cost_inr, latency_ms, validator_result, created_at)

eval_runs(id, git_sha, dataset_version, metrics JSONB, created_at)
```

## 5. API

| Method | Path | Purpose |
|---|---|---|
| POST | `/webhook/whatsapp` | Incoming customer message (Meta payload shape) |
| POST | `/sim/message` | Simulator equivalent for local dev and demo |
| GET | `/tasks?status=` | Ops queue |
| GET | `/tasks/{id}` | Full task with plan, shortlist, drafts, audit trail |
| POST | `/tasks/{id}/approve` | Approve, edit or reject an item |
| POST | `/tasks/{id}/vendor-reply` | Log a vendor reply, then parse and re-plan |
| GET | `/metrics/unit-economics` | Cost per task, minutes per task, margin per subscriber |
| GET | `/health` | Liveness |

## 6. Model strategy

- Use a **small, cheap model** for classification, slot extraction and risk (high volume, structured output) and a **larger model** only for planning and tricky drafts. Log which model handled each step.
- Provider-agnostic `LLMClient` interface (Claude, Gemini, or local Ollama for offline tests). Pick the current model IDs when you build.
- `temperature=0` for all structured steps. Cache by prompt hash.
- Per-task cost cap enforced in code. On breach, escalate to a human.

## 7. Tech stack

Python 3.11, FastAPI, Pydantic v2, PostgreSQL, Redis, SQLAlchemy/Alembic, pytest, Docker Compose, GitHub Actions, Streamlit or React for the console, Prometheus/Grafana optional.
