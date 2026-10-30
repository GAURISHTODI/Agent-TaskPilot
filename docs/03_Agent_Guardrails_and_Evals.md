# Agent Design, Guardrails and Eval Harness

This is the section that matters most for an AI Engineer role. Build it first and show numbers.

## 1. Agent design

### Tools (allowlisted per state)
| Tool | Side effect | Allowed states |
|---|---|---|
| `search_vendors(category, area, budget)` | read-only DB | PLANNED |
| `get_customer_prefs(customer_id)` | read-only | any |
| `draft_vendor_message(task, vendor_id)` | creates a draft only | PLANNED |
| `draft_customer_update(task)` | creates a draft only | IN_EXECUTION and later |
| `request_approval(item)` | puts item in queue | PLANNED and later |
| `escalate_to_human(reason)` | flags task | any |

There is **no** `send_message`, `pay`, or `book` tool. Those exist only as human actions in the console.

### Prompt design rules
1. Every structured step returns JSON against a Pydantic schema. Invalid output gets one repair retry, then a human.
2. Customer and vendor text is wrapped in delimiters and labelled as untrusted data.
3. The model is told to return `null` for unknown slots and never to infer.
4. System prompts are versioned in files and hashed into the audit log.

## 2. Guardrails

| Guardrail | How | Test |
|---|---|---|
| Output schema validation | Pydantic per step | Malformed outputs in the eval set |
| No hallucinated vendors | Vendor IDs in a draft must exist in the `vendors` table and in the shortlist | Adversarial prompt asks for "a great plumber I know" |
| Prompt-injection resistance | Untrusted text delimiters, tool allowlist per state, injection scanner | Injection suite (below) |
| Human-in-the-loop on irreversible actions | No send/pay tool exists | Unit test: attempting a banned action raises |
| PII redaction | Redact before logging and before non-essential prompts | Regex tests with Indian phone, address and card patterns |
| Spend and budget caps | Per-task LLM cost cap, max tool calls, max clarification rounds (2) | Test that cap breach escalates |
| Risk routing | Health, legal, large-spend and payment tasks always require human review | Risk recall metric |
| Quality gate on drafts | Reject empty, echoing or off-brand drafts and fall back to templates | Cost Watch-style gate test |
| Audit trail | Every step logged with prompt hash, output, validator result | Completeness test |

## 3. Eval harness

### Datasets (build these yourself, version them in `eval/data/`)
| Set | Size (target) | Contents |
|---|---|---|
| `intents.jsonl` | 200+ | Realistic WhatsApp messages (English, Hinglish, terse, typo-heavy) with gold category |
| `slots.jsonl` | 120+ | Messages with gold slot values, including nulls for "not stated" |
| `clarify.jsonl` | 60+ | Cases where the right behaviour is to ask, and cases where asking is wrong |
| `risk.jsonl` | 60+ | Tasks labelled risky or not |
| `injection.jsonl` | 40+ payloads | Injections in customer text, vendor replies and vendor names |
| `vendor_trap.jsonl` | 30+ | Requests designed to bait fabricated vendors or prices |

Write the messages from your own real errands and have a friend write a different batch, so the set is not just your phrasing. State in the README that the data is synthetic.

### Metrics
- Category accuracy and a confusion matrix (top confusions go in the README)
- Slot field-level precision, recall and F1
- Unnecessary-question rate and missed-question rate
- Hallucinated-vendor count (must be 0)
- Injection pass rate (no unauthorised tool call and no schema break)
- Risk recall and precision
- Latency p50/p95 and cost per task, per step

### Rules
- Run at `temperature=0`, fixed dataset version, and write results to `results/metrics.json` with the git SHA.
- A **3-run reproducibility check** like Cost Watch.
- CI gate: PR fails if category accuracy drops more than 2 points, or hallucinated vendors or injection failures are above 0.
- Compare at least **two models** (small vs large) on the same sets and report the cost-versus-accuracy trade-off. This is a strong interview talking point.
- Keep a short `docs/failure-analysis.md` of what the system still gets wrong. Honest failure analysis is persuasive.

## 4. Human-minutes study (the business-impact number)

1. Create 30 scripted requests across 8 categories.
2. Two or three friends play ops associate. Each handles half the tasks manually (spreadsheet, search, writing messages) and half with TaskPilot.
3. Record time to "ready to send" per task.
4. Report the median reduction, the sample size and the method in the README. Do not generalise beyond it.

## 5. Observability

Per-step latency, tokens, cost, validator pass or fail. Dashboard panels: tasks by state, cost per task, escalation rate, approval edit rate (a proxy for draft quality), and margin per subscriber for Mini vs Premium.
