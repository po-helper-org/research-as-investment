"""Score ideas against a rubric: weighted geometric mean of 1-5 scores.

Usage:
    python scoring/score.py ideas.jsonl [--rubric scoring/rubric.json]

Each line is an idea:
    {"idea_id": "...", "idea": "...", "kill": {"K1": false, ...},
     "scores": {"P": 3, "B": 2, ...}, "sources": {"B": "[title](url)", ...}}

A criterion with "ceiling_without_source" in the rubric is capped at that ceiling
when the idea has no source for it: an unsourced guess cannot score high.
"""

from __future__ import annotations

import json
import math
import sys
from pathlib import Path

DEFAULT_RUBRIC = Path(__file__).with_name("rubric.json")


def load_rubric(path: Path = DEFAULT_RUBRIC) -> dict:
    with open(path, encoding="utf-8") as f:
        return json.load(f)


def effective_scores(idea: dict, rubric: dict) -> tuple[dict[str, int], list[str]]:
    """Apply ceilings for unsourced criteria. Returns scores and the list of capped criteria."""
    scores, capped = dict(idea["scores"]), []
    sources = idea.get("sources", {})
    for code, spec in rubric["criteria"].items():
        ceiling = spec.get("ceiling_without_source")
        if ceiling and not sources.get(code) and scores.get(code, 0) > ceiling:
            scores[code] = ceiling
            capped.append(code)
    return scores, capped


def weighted_geomean(scores: dict[str, int], rubric: dict) -> float:
    criteria = rubric["criteria"]
    missing = set(criteria) - set(scores)
    if missing:
        raise ValueError(f"missing criteria: {sorted(missing)}")
    total = sum(spec["weight"] for spec in criteria.values())
    log_sum = sum(spec["weight"] * math.log(scores[code]) for code, spec in criteria.items())
    return math.exp(log_sum / total)


def score_idea(idea: dict, rubric: dict) -> dict:
    killed = [k for k, v in idea.get("kill", {}).items() if v]
    if killed:
        return {"idea_id": idea.get("idea_id"), "killed_by": killed, "passes": False}
    scores, capped = effective_scores(idea, rubric)
    score = weighted_geomean(scores, rubric)
    passes = score >= rubric["threshold"] and min(scores.values()) >= rubric["min_criterion"]
    result = {"idea_id": idea.get("idea_id"), "score": round(score, 2), "passes": passes}
    if capped:
        result["capped_without_source"] = capped
    return result


def parse_args(argv: list[str]) -> tuple[Path, Path]:
    rubric = DEFAULT_RUBRIC
    if "--rubric" in argv:
        i = argv.index("--rubric")
        rubric = Path(argv[i + 1])
        argv = argv[:i] + argv[i + 2:]
    return Path(argv[1]), rubric


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    path, rubric_path = parse_args(argv)
    rubric = load_rubric(rubric_path)
    with open(path, encoding="utf-8") as f:
        for line in f:
            if line.strip():
                print(json.dumps(score_idea(json.loads(line), rubric), ensure_ascii=False))
    return 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
