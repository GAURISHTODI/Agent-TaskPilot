#!/bin/sh
# Real-model eval on local Ollama (free), hand-written rows only, TIME-BOXED (about 17-30 min on a CPU laptop).
#   ollama pull qwen2.5:1.5b && ollama pull qwen2.5:3b
#   sh eval/run_ollama_eval.sh          # stages A + B
#   sh eval/run_ollama_eval.sh e2e      # stage B only (re-uses stage A's file)
# Output: results/metrics_real_ollama.json, results/failures_real_ollama.json
# Raise --limit for a bigger (hours-long) run; sample sizes are recorded in the JSON (every suite has "n").
export OLLAMA_MODEL_SMALL=${OLLAMA_MODEL_SMALL:-qwen2.5:1.5b} OLLAMA_MODEL_LARGE=${OLLAMA_MODEL_LARGE:-qwen2.5:3b}
cd "$(dirname "$0")/.."
if [ "$1" != "e2e" ]; then
  # A: classification-style suites (normal routing: small model for classify/extract/risk)
  python eval/run_eval.py --provider ollama --subset handwritten --limit 30 --suites intents,slots,risk --out results/metrics_real_ollama.json || exit 1
fi
# B: end-to-end guardrail sample (plan + draft use the large model, so these are slow)
python eval/run_eval.py --provider ollama --subset handwritten --limit 6 --suites trap,injection --out results/metrics_real_ollama_e2e.json || exit 1
python - <<'EOF'
import json
a = json.load(open("results/metrics_real_ollama.json", encoding="utf-8"))
b = json.load(open("results/metrics_real_ollama_e2e.json", encoding="utf-8"))
for k in ("vendor_trap", "injection", "cost"):
    if k in b:
        a[k] = b[k]
a["meta"]["suites"] = "intents,slots,risk (limit 30) + trap,injection (limit 6)"
a["meta"]["limit_per_dataset"] = "30 for intents/slots/risk (slots has 15 hand-written rows), 6 for trap/injection"
a["meta"]["e2e_run_timestamp_utc"] = b["meta"]["run_timestamp_utc"]
fa = [x for x in json.load(open("results/failures_real_ollama.json", encoding="utf-8")) if x["suite"] not in ("injection", "vendor_trap")]
fb = json.load(open("results/failures_real_ollama_e2e.json", encoding="utf-8"))
json.dump(a, open("results/metrics_real_ollama.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
json.dump(fa + fb, open("results/failures_real_ollama.json", "w", encoding="utf-8"), indent=2, ensure_ascii=False)
print("merged e2e sample into results/metrics_real_ollama.json")
EOF
