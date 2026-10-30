"""Summarise the human-minutes study.

Input : results/human_minutes_study.csv  with columns  request_id,participant,mode,minutes
        mode is `manual` or `copilot`. One row per (request, participant) timing to "ready to send".
Output: results/human_minutes_study.json  (n, medians, median reduction, per-participant medians)

Until real timings exist this script refuses to invent a number.
"""
import csv
import json
import statistics
import sys
from pathlib import Path

RESULTS = Path(__file__).resolve().parent.parent / "results"


def main() -> int:
    src = RESULTS / "human_minutes_study.csv"
    if not src.exists():
        print("No timings yet. See docs/human-minutes-study.md; no human-minutes claim can be made.")
        return 2
    rows = list(csv.DictReader(src.open(encoding="utf-8")))
    by = {"manual": [], "copilot": []}
    per: dict[str, dict[str, list[float]]] = {}
    for r in rows:
        v = float(r["minutes"])
        by[r["mode"]].append(v)
        per.setdefault(r["participant"], {"manual": [], "copilot": []})[r["mode"]].append(v)
    if not by["manual"] or not by["copilot"]:
        print("Need both manual and copilot rows.")
        return 2
    mm, mc = statistics.median(by["manual"]), statistics.median(by["copilot"])
    out = {"n_manual": len(by["manual"]), "n_copilot": len(by["copilot"]), "participants": len(per),
           "median_minutes_manual": mm, "median_minutes_copilot": mc,
           "median_reduction_pct": round(100 * (mm - mc) / mm, 1),
           "per_participant_median": {p: {k: statistics.median(v) if v else None for k, v in d.items()} for p, d in per.items()},
           "caveat": "Small sample, scripted requests, friends as ops. Do not generalise."}
    (RESULTS / "human_minutes_study.json").write_text(json.dumps(out, indent=2) + "\n")
    print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
