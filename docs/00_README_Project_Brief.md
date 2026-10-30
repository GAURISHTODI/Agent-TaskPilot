# TaskPilot: AI Ops Copilot for a WhatsApp Concierge Business

> Built as a portfolio project for the FAFF AI Engineer application. FAFF is a WhatsApp personal-assistant subscription (₹399 Mini / ₹1,999 Premium) where humans plus AI execute 30+ categories of errands. This project is **not a clone of FAFF**. It targets the problem the company description calls out as its core one: *"How can FAFF fulfil more customer requests without increasing operations headcount at the same rate?"*

## 1. Why this project (and not another)

| FAFF's stated challenge | What TaskPilot does about it |
|---|---|
| Ops cost per task is high and variable under a flat fee | Tracks time, LLM cost, and human minutes per task, then shows margin per subscriber |
| Scaling means hiring ops staff | The agent handles intake, clarification, vendor shortlisting and drafts. A human only approves and handles exceptions |
| Heavy users can make the flat plan unprofitable | Complexity scoring at intake plus a per-subscriber contribution-margin view |
| Third-party vendors are unreliable | Vendor outreach drafts, follow-up timers, and escalation rules |
| Service quality and trust | Human-in-the-loop approval gate, hallucination-safe vendor data, full audit trail |
| WhatsApp is the interface | Webhook-based WhatsApp intake (simulator first, Cloud API test number optional) |

This reuses what you already built and can speak to in the interview: **grounding** (Cost Watch), **eval harness** (Cost Watch, Sentinel), **guardrails and schema validation** (Sentinel triage, Agent SecOps cost caps), **FastAPI/Postgres/Docker/CI**.

## 2. One-paragraph pitch

A customer messages "Find someone to fix my AC, Saturday morning, Koramangala." TaskPilot classifies it into one of 30+ categories, extracts the details, asks only for what is missing, builds an execution plan, shortlists vendors from a verified vendor table (never invented), drafts the outreach, and puts it in front of an ops person for one-click approval. Status updates go back over WhatsApp. A dashboard shows tasks per ops person, cost per task, and margin per subscriber.

## 3. Document map

| File | Purpose |
|---|---|
| `01_PRD.md` | Problem, users, scope, functional requirements, success metrics |
| `02_Architecture_and_Data_Model.md` | System design, components, DB schema, API |
| `03_Agent_Guardrails_and_Evals.md` | Prompts and tools, guardrails, eval harness (the part recruiters care about) |
| `04_Build_Plan.md` | Milestones, task checklist, tech stack, repo layout, demo script |
| `05_Resume_and_Interview.md` | Resume bullets (fill in after measuring), interview talking points |

## 4. Rules for yourself while building

1. **Never put a number on the resume that is not in `results/metrics.json`.** Targets in these docs are targets, not results.
2. **Simulator first.** Do not wait on Meta business verification. A WhatsApp-style chat simulator proves the same thing.
3. **The LLM never executes irreversible actions** (payments, bookings, sending to a vendor). It drafts, a human approves.
4. **Vendor data comes from the database, not from the model.** Same anti-hallucination principle as Cost Watch.
5. Ship the eval harness in week 1, not at the end.
