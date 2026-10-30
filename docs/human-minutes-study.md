# Human-minutes study protocol

The dashboard's ops minutes are **modelled**. This study is how to replace them with a measured number. Until it has been run, make no time-saved claim.

## Setup
1. Requests: `eval/data/study_requests.jsonl` (30 scripted requests over 8 categories; regenerate with `python eval/build_datasets.py`).
2. Participants: 2-3 friends acting as ops associates. None of them should have seen the requests.
3. Split: each participant handles half the requests **manually** (spreadsheet/web search/writing the vendor message themselves, using the same vendor list as `/vendors`) and half **with TaskPilot** (read the task, edit/approve the draft). Alternate which half is which per participant, to cancel out request difficulty.
4. Clock: from "request shown" to "outreach message ready to send". Use a stopwatch; do not time the vendor's reply.
5. Record to `results/human_minutes_study.csv`:

```
request_id,participant,mode,minutes
1,A,manual,14.5
1,B,copilot,3.0
```

## Analyse
```
python eval/analyze_study.py
```
Writes `results/human_minutes_study.json` with sample sizes, medians and the median reduction. The script exits without a number if the CSV is missing.

## Reporting rules
- State n, the number of participants, that requests were scripted, and that participants were friends, not trained ops staff.
- Report the median, not the mean; report per-participant medians too.
- Do not generalise beyond this setup. The PRD target (>= 50% median reduction) is a target, not a result.
