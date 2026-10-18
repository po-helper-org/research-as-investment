"""Knowledge base of research atoms: knowledge/facts.jsonl, one fact per line.

Criterion codes are validated against scoring/rubric.json when it exists.

Usage:
    python knowledge/kb.py check               # validate facts.jsonl
    python knowledge/kb.py find b2c G          # facts matching ALL terms (tag, criterion or text)
    python knowledge/kb.py stale [days]        # facts last checked more than N days ago (default 180)
    python knowledge/kb.py check --facts examples/deepstash-ru/facts.jsonl   # any other facts file

Fact format is described in knowledge/README.md.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

FACTS = Path(__file__).with_name("facts.jsonl")
REQUIRED = ("fact_id", "claim", "as_of", "checked", "source", "evidence", "criteria", "tags", "used_by")
EVIDENCE = {f"E{i}" for i in range(7)}
RUBRIC = Path(__file__).resolve().parent.parent / "scoring" / "rubric.json"
FACT_ID = re.compile(r"^F-\d{4}-\d{2}-\d{2}-\d{3}$")
SOURCE = re.compile(r"\[.+\]\(https?://.+\)")


def load(path: Path = FACTS) -> list[dict]:
    with path.open(encoding="utf-8") as f:
        return [json.loads(line) for line in f if line.strip()]


def rubric_codes() -> set[str]:
    """Criterion and stop-criterion codes from scoring/rubric.json; empty set disables the check."""
    if not RUBRIC.exists():
        return set()
    rubric = json.loads(RUBRIC.read_text(encoding="utf-8"))
    return set(rubric.get("criteria", {})) | set(rubric.get("stop_criteria", {}))


def check(facts: list[dict]) -> list[str]:
    errors, seen, criteria = [], set(), rubric_codes()
    for n, fact in enumerate(facts, 1):
        where = f"line {n} ({fact.get('fact_id', '?')})"
        errors += [f"{where}: missing {k}" for k in REQUIRED if k not in fact]
        fid = fact.get("fact_id", "")
        if not FACT_ID.match(fid):
            errors.append(f"{where}: fact_id must look like F-YYYY-MM-DD-NNN")
        if fid in seen:
            errors.append(f"{where}: duplicate fact_id")
        seen.add(fid)
        if fact.get("evidence") not in EVIDENCE:
            errors.append(f"{where}: evidence must be E0..E6")
        if fact.get("evidence") != "E0" and not SOURCE.search(fact.get("source", "")):
            errors.append(f"{where}: source must be a markdown link [title](url)")
        unknown = set(fact.get("criteria", [])) - criteria
        if criteria and unknown:
            errors.append(f"{where}: unknown criteria {sorted(unknown)}")
        try:
            dt.date.fromisoformat(fact.get("checked", ""))
        except ValueError:
            errors.append(f"{where}: checked must be YYYY-MM-DD")
    return errors


def matches(fact: dict, term: str) -> bool:
    term = term.lower()
    if term in (t.lower() for t in fact.get("tags", [])) or term in (c.lower() for c in fact.get("criteria", [])):
        return True
    return term in fact.get("claim", "").lower()


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    path = FACTS
    if "--facts" in argv:
        i = argv.index("--facts")
        path, argv = Path(argv[i + 1]), argv[:i] + argv[i + 2:]
    facts = load(path)
    if argv[1] == "check":
        errors = check(facts)
        print("\n".join(errors) if errors else f"ok: {len(facts)} facts")
        return 1 if errors else 0
    if argv[1] == "find":
        for fact in facts:
            if all(matches(fact, t) for t in argv[2:]):
                print(json.dumps(fact, ensure_ascii=False))
        return 0
    if argv[1] == "stale":
        days = int(argv[2]) if len(argv) > 2 else 180
        cutoff = dt.date.today() - dt.timedelta(days=days)
        for fact in facts:
            if dt.date.fromisoformat(fact["checked"]) < cutoff:
                print(f"{fact['fact_id']}  checked {fact['checked']}  {fact['claim']}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
