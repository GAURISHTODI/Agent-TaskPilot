# Interview notes: TaskPilot

Everything quoted here comes from a file in `results/`. If a number is not in the table at the bottom, do not say it.

## 60-second pitch

"A WhatsApp concierge business earns a flat fee per subscriber, but the effort per request varies a lot, and most of that effort is back-and-forth: working out what the customer wants, collecting missing details, finding vendors, drafting messages. I built TaskPilot as a guarded LLM pipeline for exactly that part. It classifies a request into one of 34 categories, extracts typed slots and leaves unstated ones null, asks at most one consolidated question, builds a plan, shortlists vendors with plain SQL from a verified table, drafts outreach and passes it through a quality gate. A human approves anything that leaves the system. I treated the model as untrusted: schema-validated outputs, a state-scoped tool allowlist, PII redaction, an injection scanner, a cost cap, and an audit log for every call. Then I built an eval harness with 548 labelled rows, a CI gate and a reproducibility check, so I could measure it instead of guessing. It runs on a free local model through Ollama as well as a deterministic stub, and I report both honestly."

## How it relates to the "ops effort per task" problem (without overclaiming)

- The target is the cheap-to-automate part of a concierge task (intake, clarification, planning, drafting), while a human keeps every outward or financial action.
- What I can say: the pipeline is built so that ops effort per task *can* fall, and the dashboard tracks cost per task, escalation rate and draft edit rate.
- What I cannot say: that it beats any company's current process or saves a given percentage of time. The human-minutes study (scripted requests, friends as ops) has **not been run**; the minutes on the dashboard are modelled from per-category assumptions. I did not use any company's data; everything is synthetic.

## Likely questions

**How do you prevent hallucinated vendors?**
The model never produces vendors. The shortlist is a SQL query over verified vendors with an area hard-filter and a deterministic score. Drafts then pass a validator: it rejects unknown vendor-looking names, prices that are not the customer's stated budget, payment language, links and phone numbers, and text that echoes the customer's message; on rejection the system falls back to a template. Result: 0 fabricated vendors or prices across 32 trap prompts. Caveat I volunteer: the name check is regex-based (fixed suffix list), and the stub never invents names itself, so this is the first thing to stress with a real model.

**How do you evaluate an agent?**
Per-step metrics on versioned datasets (intents, slots, clarification, risk, injection, vendor traps), reported separately for hand-written and template-generated rows because template rows are easy and partly circular. A CI gate fails on accuracy regression, any hallucinated vendor, or any injection failure; a 3-run check confirms determinism; I compare small, large and cascade routing on cost vs accuracy. And I read the failures: `docs/failure-analysis.md`.

**How do you handle prompt injection, e.g. from a vendor reply?**
Defence in depth. (1) Customer and vendor text is labelled untrusted data and the scanner flags known patterns (including zero-width obfuscation); flagged text is quarantined, never reaches the planner or drafter, and the task escalates. (2) Even if the scanner misses it, the model cannot act: tool calls go through a per-state allowlist and `send_message` / `pay` / `book` do not exist as tools. (3) Vendor names are scanned too. I report two modes: scanner on (detection 95.1%) and scanner off (detection 43.9%, but zero actions executed because the gate blocks them).

**Isn't "0 unauthorised actions" trivial then?**
Partly, yes, and I say so: it is true largely by construction, because there is no send/pay/book tool to hijack. The informative numbers are the detection rates and the fact that with the scanner off, a deliberately obedient stub that asks for `pay` is blocked and logged.

**Why human approval? Doesn't that not scale?**
It is the safe default for irreversible, trust-sensitive actions, and small models are not accurate enough to trust blindly. It does not scale to very high volume by itself. The approach I would take: instrument edit rate, confidence and escalation per category (already tracked) and use that evidence to decide which low-risk categories could be auto-approved with sampled audits.

**What would you build next?**
Earned autonomy (future direction only, not built): tiers from "agent alone with sampled audit" to "customer confirms with one tap" to "human only", where categories are promoted on evidence and demoted automatically. Risks I would address first: a wrong action on a real customer, a promotion based on circular simulated data, vendor replies as an injection channel, and the audit sample being too small to catch a rare failure. Also: real WhatsApp Cloud API, a measured human-minutes study, evals with larger real models.

**What does it get wrong?**
See `docs/failure-analysis.md`: Hinglish and no-keyword phrasing, bare-number budgets ("... 8000" is not read as a budget, which also caused one missed high-spend risk flag), keyword ties ("laundry pickup", "catering ... lunch"), and one confident misclassification (a fridge as an AC). The small local model is weaker than the stub (80% vs 90% category accuracy on the same 30 rows) and over-flags risk (precision 68%); that is reported in the README. Say this yourself before an interviewer finds it.

## Every metric, its source and provider

All files are in `results/`. "Stub" = the built-in deterministic `fake` provider (rule-based, not a language model).

| Metric | Value | File | Provider |
|---|---|---|---|
| Category accuracy (all 229 / hand-written 59) | 96.1% / 89.8% | metrics.json | Stub |
| Slot F1 (all 125 / hand-written 15) | 0.985 / 0.949 | metrics.json | Stub |
| Unnecessary / missed clarifying questions | 6.5% (2/31) / 0% (0/30) | metrics.json | Stub |
| Risk recall / precision (n=60) | 96.7% / 100% | metrics.json | Stub |
| Fabricated vendors or prices (32 trap prompts) | 0 | metrics.json | Stub |
| Injection: unauthorised actions (41 payloads, scanner on / off) | 0 / 0 | metrics.json | Stub |
| Injection detection (scanner on / off) | 95.1% / 43.9% | metrics.json | Stub |
| Cost per task | ₹0.21 (placeholder prices) | metrics.json | Stub |
| Routing: all-small / all-large / cascade (hand-written accuracy) | 89.8% / 93.2% / 93.2% | metrics.json (model_comparison) | Stub tiers |
| Reproducibility | 3/3 identical | reproducibility.json | Stub |
| Same suites on hand-written rows only | see README table | metrics_fake_subset.json | Stub |
| Category accuracy, hand-written (n=30) | 80.0% (stub on same rows: 90.0%) | metrics_real_ollama.json, metrics_fake_matched.json | Ollama qwen2.5:1.5b / stub |
| Slot F1, hand-written (n=15) | 0.774 (stub: 0.949) | same | Ollama / stub |
| Risk recall / precision (n=30) | 100% / 68.2% (stub: 100% / 100%) | same | Ollama / stub |
| End-to-end tasks escalated (n=6) | 100% (stub: 50%) | metrics_real_ollama.json, metrics_fake_matched_e2e.json | Ollama / stub |
| Fabricated vendors/prices (n=6) | 0, but vacuous (no drafts were produced) | metrics_real_ollama.json | Ollama |
| Injection unauthorised actions (n=5 evaluable) | 0; detection 80% scanner on, 0% off | metrics_real_ollama.json | Ollama |
| Human minutes saved | **not measured** | (no file) | - |
