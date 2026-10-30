# Resume Bullets and Interview Notes

## Resume entry (replace every `__` with a measured value from `results/metrics.json`)

**TaskPilot** | AI Ops Copilot for a WhatsApp Concierge Business | Python, FastAPI, PostgreSQL, Redis, Claude/Gemini API, Docker, GitHub Actions | GitHub

- Built an agentic copilot that turns WhatsApp requests into approved, vendor-ready tasks: classification across 30+ categories (__% accuracy), schema-validated slot extraction (F1 __), one-shot clarification, planning, and vendor-outreach drafts behind a human approval gate.
- Cut simulated ops time per task by __% (median, n=__ tasks) and LLM cost to ₹__ per task using a small-model/large-model split and caching.
- **Guardrails:** vendor shortlists come only from a verified DB (0 hallucinated vendors in __ adversarial cases), tool allowlist per task state, PII redaction, per-task cost caps, and a __-case prompt-injection suite (__% pass).
- **Harness:** versioned eval datasets (__ labelled cases), CI-gated regression checks, 3-run reproducibility verification, and a two-model cost-versus-accuracy comparison; unit-economics dashboard for margin per subscriber.

Do not publish the entry until the blanks are filled with real numbers. If a metric did not come out well, say what you learned instead.

## What to say about the FAFF problem

"FAFF's flat subscription means margin depends on how much human effort a task needs. I built a copilot that targets the cheapest part to automate, which is intake, clarification and drafting, and keeps a human on every outward action. I measured human minutes per task, not just model accuracy, because that is what drives the unit economics."

## Likely interview questions and where your answer comes from

| Question | Your answer source |
|---|---|
| How do you stop the model inventing vendors or prices? | Vendors and prices are DB-only, and validators reject unknown IDs (same idea as Cost Watch grounding) |
| How do you evaluate an agent? | Versioned datasets, per-step metrics, CI gate, reproducibility check, and a human-minutes study |
| How do you handle prompt injection from a vendor reply? | Untrusted-data delimiters, no send/pay tools, state-scoped allowlist, injection suite |
| Why not fully automate? | Irreversible and trust-sensitive actions need a human. The edit rate on approvals tells you when to loosen that |
| How do you control cost? | Small model for high-volume steps, caching, per-task cap with escalation on breach |
| What would you do next? | Learn from approval edits, vendor-reliability scoring from outcomes, real WhatsApp Cloud API, multilingual support |
| What does it get wrong? | Walk through `docs/failure-analysis.md`. Naming failures confidently is a strength |

## Before you apply

- Open the repo with a clean README, a demo video, and the results table.
- Mention in the application message that you studied FAFF's stated challenge (tasks per ops employee) and built against it.
- Do not claim the project uses FAFF's data or systems. It is a synthetic-data prototype inspired by the public description.
