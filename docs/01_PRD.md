# PRD: TaskPilot

| | |
|---|---|
| Owner | Gaurish Todi |
| Status | Draft v1 |
| Type | Portfolio MVP for a WhatsApp-based concierge business |

## 1. Problem

A subscription concierge earns a roughly fixed fee per customer, but the effort to fulfil a request varies a lot. Most of the effort is not the final booking. It is the **back-and-forth**: working out what the customer wants, collecting missing details, finding vendors, contacting them, chasing replies, and reporting back. Every one of these steps is done manually, which ties margin to headcount.

## 2. Goal

Cut the human minutes spent per task by automating intake, clarification, planning and vendor-outreach drafting, while keeping a human in control of every outward-facing or financial action.

**Non-goals (explicitly out of scope for the MVP):** payments, real vendor integrations or APIs, voice, multilingual support beyond English/Hinglish test messages, a customer mobile app, replacing the ops team.

## 3. Users

| User | Needs |
|---|---|
| **Customer** (busy professional) | Message in plain language on WhatsApp, be asked at most one or two sensible questions, get clear status updates |
| **Ops associate** | A prepared task (details, shortlist, drafted messages) to approve or edit in one click instead of building it from scratch |
| **Ops lead / founder** | Visibility into cost per task, tasks per associate, SLA breaches, and which subscribers are unprofitable |

## 4. User stories

1. As a customer, I send a free-text request and get an acknowledgement within seconds.
2. As a customer, if details are missing, I get **one consolidated** clarifying question, not ten.
3. As an ops associate, I see the task with its category, extracted fields, a proposed plan, a vendor shortlist and drafted outreach messages, and I can approve, edit or reject.
4. As an ops associate, I can log a vendor reply and the agent updates the plan and drafts the customer update.
5. As an ops lead, I see per-task time, LLM cost and human minutes, plus margin per subscriber.
6. As an ops lead, risky tasks (high spend, health, payment) are always routed to a human with a flag.

## 5. Functional requirements

### P0 (must ship)
| ID | Requirement |
|---|---|
| F1 | WhatsApp-style intake via webhook, with a web chat simulator and message history per customer |
| F2 | Category classification into a configurable taxonomy of 30+ categories with confidence score |
| F3 | Slot extraction into a typed schema per category (who, what, when, where, budget) with JSON-schema validation |
| F4 | Missing-slot detection and one consolidated clarifying question |
| F5 | Plan generation: ordered steps with owner (agent, human, vendor) and estimated effort |
| F6 | Vendor shortlist **only from the vendor table**, ranked by category, area, rating and past reliability |
| F7 | Outreach draft per vendor, never sent without approval |
| F8 | Ops console: approve, edit, reject, escalate |
| F9 | Risk and complexity scoring, with mandatory human review above a threshold |
| F10 | Audit log of every model call, tool call, decision and approval |
| F11 | Eval harness with a labelled dataset and a CI gate |

### P1 (should ship)
| ID | Requirement |
|---|---|
| F12 | Vendor reply parsing into structured quotes and status |
| F13 | Follow-up timers and an SLA breach alert |
| F14 | Unit-economics dashboard: cost per task, minutes per task, margin per subscriber on Mini vs Premium |
| F15 | Customer status updates drafted in a consistent brand tone |
| F16 | Repeat-request detection ("book my usual table") using stored preferences |

### P2 (stretch)
Real WhatsApp Cloud API test number, MCP server exposing the vendor and task tools, LLM-as-judge for reply quality, simple cost-based routing between a small and a large model.

## 6. Non-functional requirements

| Area | Requirement |
|---|---|
| Latency | Acknowledgement under 3 s. Plan and draft ready under 15 s (target) |
| Cost | Hard per-task LLM budget cap, with caching and the cheapest adequate model per step |
| Safety | PII redaction in logs, prompt-injection handling for vendor and customer text, no autonomous irreversible actions |
| Reliability | Idempotent webhook handling, retries with backoff, graceful fallback to "human takes over" on any model failure |
| Reproducibility | Evals run deterministically (temperature 0, fixed seeds, fixed dataset) |
| Observability | Structured logs, per-step latency and token cost, health endpoint |

## 7. Success metrics (targets to be measured, then reported honestly)

| Metric | Target |
|---|---|
| Category accuracy on labelled set | ≥ 90% |
| Slot-extraction field-level F1 | ≥ 0.90 |
| Unnecessary clarifying questions | ≤ 10% of tasks |
| Hallucinated vendors in shortlists | **0** |
| Prompt-injection suite pass rate | 100% (no unauthorised tool call) |
| Risky tasks correctly escalated (recall) | ≥ 95% |
| Median human minutes per task, with vs without copilot (simulated ops study) | ≥ 50% reduction |
| LLM cost per task | under ₹2 (target) |

## 8. Key risks

| Risk | Mitigation |
|---|---|
| Model invents a vendor, price or availability | Vendors and prices come only from DB records. Any vendor ID not in the DB fails validation |
| Customer or vendor text contains injected instructions | Treat as data, never as instructions. Tool calls are limited by an allowlist per state |
| Over-asking annoys customers | Metric on unnecessary questions, plus one-question-at-a-time rule |
| "Time saved" claim is unfalsifiable | Run a timed comparison with 2-3 friends acting as ops, using 30 scripted requests, and report the method |
| Synthetic data looks unrealistic | Build the dataset from your own real errands plus public-style vendor lists. State clearly that it is synthetic |

## 9. Open questions
1. Which 8-10 categories do you hand-craft in depth first (suggest: restaurant booking, home repair, groceries, travel, gifting, doctor appointment, delivery, personal admin)?
2. Do you want a real WhatsApp number in the demo, or the simulator only?
