"""Runs the full eval 3 times and asserts the (non-timing) metrics are identical."""
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))
sys.path.insert(0, str(Path(__file__).resolve().parent))

import run_eval  # noqa: E402


def main() -> int:
    runs = [json.dumps(run_eval.stable(run_eval.run_suite("fake", None, [])), sort_keys=True) for _ in range(3)]
    same = len(set(runs)) == 1
    out = {"runs": 3, "identical": same}
    if not same:
        a, b = json.loads(runs[0]), json.loads(next(r for r in runs if r != runs[0]))
        out["differing_keys"] = [k for k in a if a[k] != b.get(k)]
    out_path = run_eval.RESULTS / "reproducibility.json"
    out_path.write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out))
    return 0 if same else 1


if __name__ == "__main__":
    raise SystemExit(main())
