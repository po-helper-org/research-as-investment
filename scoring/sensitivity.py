"""Value-of-information check: which criteria can move Score across the threshold.

Usage:
    python scoring/sensitivity.py idea.jsonl [--rubric scoring/rubric.json]

Each line is an idea in the score.py format plus "ranges": the plausible
[worst, best] value of every criterion that is still uncertain, e.g.
    "ranges": {"G": [2, 4], "B": [1, 3]}
Criteria without a range keep their current value. Ceilings for unsourced
criteria apply to the best case too: research must find a source to lift them.

Verdict (METHODOLOGY.md, step 4):
    kill      even the best case does not pass: stop researching
    go        even the worst case passes: go to the buyer, not to the desk
    research  research the criteria whose swing crosses the threshold, largest first
"""

from __future__ import annotations

import json
import sys

from score import load_rubric, parse_args, score_idea


def with_values(idea: dict, values: dict[str, int], sourced: bool = False) -> dict:
    variant = {**idea, "scores": {**idea["scores"], **values}}
    if sourced:
        # best case assumes research finds sources for the criteria it explores
        variant["sources"] = {**idea.get("sources", {}), **{k: "assumed" for k in values}}
    return variant


def analyse(idea: dict, rubric: dict) -> dict:
    ranges = idea.get("ranges", {})
    base = score_idea(idea, rubric)
    if "killed_by" in base:
        return {"idea_id": idea.get("idea_id"), "killed_by": base["killed_by"], "verdict": "kill"}

    worst = score_idea(with_values(idea, {k: lo for k, (lo, hi) in ranges.items()}), rubric)
    best = score_idea(with_values(idea, {k: hi for k, (lo, hi) in ranges.items()}, sourced=True), rubric)
    threshold = rubric["threshold"]

    swings = []
    for k, (lo, hi) in ranges.items():
        low = score_idea(with_values(idea, {k: lo}), rubric)["score"]
        high = score_idea(with_values(idea, {k: hi}, sourced=True), rubric)["score"]
        swings.append({"criterion": k, "range": [lo, hi], "score_low": low, "score_high": high,
                       "swing": round(high - low, 2), "crosses_threshold": low < threshold <= high})
    swings.sort(key=lambda s: s["swing"], reverse=True)

    if not best["passes"]:
        verdict = "kill"
    elif worst["passes"]:
        verdict = "go"
    else:
        verdict = "research"
    return {"idea_id": idea.get("idea_id"), "score": base["score"], "worst": worst["score"],
            "best": best["score"], "threshold": threshold, "verdict": verdict, "swings": swings}


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    path, rubric_path = parse_args(argv)
    rubric = load_rubric(rubric_path)
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                print(json.dumps(analyse(json.loads(line), rubric), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
