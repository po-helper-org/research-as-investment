"""Knowledge base of research atoms: knowledge/facts.jsonl, one fact per line.

Criterion codes are validated against scoring/rubric.json when it exists.

Usage:
    python knowledge/kb.py check               # validate facts.jsonl
    python knowledge/kb.py find b2c G          # facts matching ALL terms (tag, criterion or text)
    python knowledge/kb.py stale [days]        # facts last checked more than N days ago (default 180)
    python knowledge/kb.py check --facts examples/deepstash-ru/facts.jsonl   # any other facts file

Fact format is described in knowledge/README.md. `check` reports every problem as
`line N (fact_id): ...` and never stops on a malformed atom: wrong types, broken JSON
and missing fields are errors of that line, not a crash of the tool.

Atoms written before the fact_id format was enforced keep their ids: they are listed,
one per line, in legacy-fact-ids.txt next to this file (optional). The list is frozen:
every new atom uses F-YYYY-MM-DD-NNN.
"""

from __future__ import annotations

import datetime as dt
import json
import re
import sys
from pathlib import Path

FACTS = Path(__file__).with_name("facts.jsonl")
LEGACY_IDS = Path(__file__).with_name("legacy-fact-ids.txt")
REQUIRED = ("fact_id", "claim", "as_of", "checked", "source", "evidence", "criteria", "tags", "used_by")
EVIDENCE = {f"E{i}" for i in range(7)}
RUBRIC = Path(__file__).resolve().parent.parent / "scoring" / "rubric.json"
FACT_ID = re.compile(r"^F-\d{4}-\d{2}-\d{2}-\d{3}$")
SOURCE = re.compile(r"\[.+\]\(https?://.+\)")


def read(path: Path = FACTS) -> list[tuple[int, object]]:
    """(line number, parsed atom) for every non-empty line; a broken line comes as JSONDecodeError."""
    rows: list[tuple[int, object]] = []
    for n, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            rows.append((n, json.loads(line)))
        except json.JSONDecodeError as e:
            rows.append((n, e))
    return rows


def load(path: Path = FACTS) -> list[dict]:
    """Atoms that parse as JSON objects; broken lines are left to `check`."""
    return [fact for _, fact in read(path) if isinstance(fact, dict)]


def legacy_ids(path: Path = LEGACY_IDS) -> frozenset[str]:
    if not path.exists():
        return frozenset()
    lines = (line.strip() for line in path.read_text(encoding="utf-8").splitlines())
    return frozenset(line for line in lines if line and not line.startswith("#"))


def rubric_codes() -> set[str]:
    """Criterion and stop-criterion codes from scoring/rubric.json; empty set disables the check."""
    if not RUBRIC.exists():
        return set()
    rubric = json.loads(RUBRIC.read_text(encoding="utf-8"))
    return set(rubric.get("criteria", {})) | set(rubric.get("stop_criteria", {}))


def shown(value: object) -> str:
    """Short description of a wrong value for an error message."""
    if isinstance(value, str):
        return repr(value if len(value) <= 30 else value[:30] + "…")
    return type(value).__name__


def is_str_list(value: object) -> bool:
    return isinstance(value, list) and all(isinstance(x, str) for x in value)


def problems(fact: object, legacy: frozenset[str] = frozenset(), criteria: set[str] | None = None) -> list[str]:
    """Format problems of one atom, without its location. Never raises on wrong types."""
    criteria = rubric_codes() if criteria is None else criteria
    if isinstance(fact, json.JSONDecodeError):
        return [f"not valid JSON: {fact.msg} at column {fact.colno}"]
    if not isinstance(fact, dict):
        return [f"atom must be a JSON object, got {shown(fact)}"]
    errors = [f"missing {k}" for k in REQUIRED if k not in fact]
    has = fact.__contains__

    fid = fact.get("fact_id")
    if has("fact_id"):
        if not isinstance(fid, str):
            errors.append(f"fact_id must be a string, got {shown(fid)}")
        elif not FACT_ID.match(fid) and fid not in legacy:
            errors.append("fact_id must look like F-YYYY-MM-DD-NNN")
    if has("claim") and not (isinstance(fact["claim"], str) and fact["claim"].strip()):
        errors.append(f"claim must be a non-empty string, got {shown(fact['claim'])}")
    if has("as_of") and not isinstance(fact["as_of"], str):
        errors.append(f"as_of must be a string, got {shown(fact['as_of'])}")

    evidence = fact.get("evidence")
    if has("evidence") and not (isinstance(evidence, str) and evidence in EVIDENCE):
        errors.append(f"evidence must be one of E0..E6, got {shown(evidence)}")
    source = fact.get("source")
    if has("source"):
        if not isinstance(source, str):
            errors.append(f"source must be a string, got {shown(source)}")
        elif evidence != "E0" and not SOURCE.search(source):
            errors.append("source must be a markdown link [title](url)")

    for key in ("criteria", "tags", "used_by"):
        if has(key) and not is_str_list(fact[key]):
            errors.append(f"{key} must be a list of strings, got {shown(fact[key])}")
    if criteria and is_str_list(fact.get("criteria")):
        unknown = set(fact["criteria"]) - criteria
        if unknown:
            errors.append(f"unknown criteria {sorted(unknown)}")

    checked = fact.get("checked")
    if has("checked"):
        try:
            if not isinstance(checked, str):
                raise ValueError
            dt.date.fromisoformat(checked)
        except ValueError:
            errors.append(f"checked must be YYYY-MM-DD, got {shown(checked)}")
    if fact.get("caveat") is not None and not isinstance(fact["caveat"], str):
        errors.append(f"caveat must be a string, got {shown(fact['caveat'])}")
    return errors


def check(facts: list, lines: list[int] | None = None, legacy: frozenset[str] | None = None) -> list[str]:
    """All problems of a list of atoms as `line N (fact_id): ...`; `lines` are file line numbers."""
    legacy = legacy_ids() if legacy is None else legacy
    lines = lines or list(range(1, len(facts) + 1))
    errors, seen, criteria = [], set(), rubric_codes()
    for n, fact in zip(lines, facts):
        fid = fact.get("fact_id") if isinstance(fact, dict) else None
        where = f"line {n} ({fid if isinstance(fid, str) else '?'})"
        errors += [f"{where}: {p}" for p in problems(fact, legacy, criteria)]
        if isinstance(fid, str):
            if fid in seen:
                errors.append(f"{where}: duplicate fact_id")
            seen.add(fid)
    return errors


def strings(value: object) -> list[str]:
    if isinstance(value, str):
        return [value]
    return [x for x in value if isinstance(x, str)] if isinstance(value, list) else []


def matches(fact: dict, term: str) -> bool:
    term = term.lower()
    if term in (t.lower() for t in strings(fact.get("tags"))) or term in (c.lower() for c in strings(fact.get("criteria"))):
        return True
    claim = fact.get("claim")
    return isinstance(claim, str) and term in claim.lower()


def main(argv: list[str]) -> int:
    if len(argv) < 2 or argv[1] in ("-h", "--help"):
        print(__doc__)
        return 0
    path = FACTS
    if "--facts" in argv:
        i = argv.index("--facts")
        path, argv = Path(argv[i + 1]), argv[:i] + argv[i + 2:]
    if argv[1] == "check":
        rows = read(path)
        errors = check([fact for _, fact in rows], [n for n, _ in rows])
        print("\n".join(errors) if errors else f"ok: {len(rows)} facts")
        return 1 if errors else 0
    facts = load(path)
    if argv[1] == "find":
        for fact in facts:
            if all(matches(fact, t) for t in argv[2:]):
                print(json.dumps(fact, ensure_ascii=False))
        return 0
    if argv[1] == "stale":
        days = int(argv[2]) if len(argv) > 2 else 180
        cutoff = dt.date.today() - dt.timedelta(days=days)
        for fact in facts:
            try:
                checked = dt.date.fromisoformat(fact["checked"])
            except (KeyError, TypeError, ValueError):
                print(f"skipped {fact.get('fact_id', '?')}: checked is not YYYY-MM-DD", file=sys.stderr)
                continue
            if checked < cutoff:
                print(f"{fact['fact_id']}  checked {fact['checked']}  {fact['claim']}")
        return 0
    print(__doc__)
    return 1


if __name__ == "__main__":
    sys.exit(main(sys.argv))
