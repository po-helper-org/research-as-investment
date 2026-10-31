"""Run: python -m unittest discover tests"""

import json
import sys
import unittest
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "scoring"), str(ROOT / "knowledge")]

import kb  # noqa: E402
from score import load_rubric, score_idea  # noqa: E402
from sensitivity import analyse  # noqa: E402

RUBRIC = load_rubric()
EXAMPLE = json.loads((ROOT / "examples/deepstash-ru/idea.jsonl").read_text(encoding="utf-8"))


def idea(sourced=True, **scores):
    """Idea with every criterion at 3 and, by default, a source for every criterion."""
    codes = RUBRIC["criteria"]
    sources = {code: "[s](https://example.com)" for code in codes} if sourced else {}
    return {"idea_id": "t", "scores": {**{c: 3 for c in codes}, **scores}, "sources": sources}


class ScoreTest(unittest.TestCase):
    def test_unsourced_criteria_are_capped(self):
        result = score_idea(idea(sourced=False, G=5, W=2), RUBRIC)
        self.assertEqual(result["capped_without_source"], ["G"])

    def test_source_lifts_the_cap(self):
        self.assertNotIn("capped_without_source", score_idea(idea(G=5, W=5), RUBRIC))

    def test_stop_criterion_kills(self):
        killed = {**idea(), "kill": {"K1": True}}
        self.assertEqual(score_idea(killed, RUBRIC)["killed_by"], ["K1"])

    def test_one_weak_criterion_blocks_pass(self):
        self.assertFalse(score_idea(idea(B=1), RUBRIC)["passes"])


class SensitivityTest(unittest.TestCase):
    def test_example_is_killed(self):
        self.assertEqual(analyse(EXAMPLE, RUBRIC)["verdict"], "kill")

    def test_go_when_worst_case_passes(self):
        strong = {**idea(P=4, U=4, D=4, S=4, F=4), "ranges": {"P": [4, 5]}}
        self.assertEqual(analyse(strong, RUBRIC)["verdict"], "go")

    def test_research_when_range_crosses_threshold(self):
        open_question = {**idea(F=1), "ranges": {"F": [1, 4]}}
        result = analyse(open_question, RUBRIC)
        self.assertEqual(result["verdict"], "research")
        self.assertTrue(result["swings"][0]["crosses_threshold"])


class KnowledgeBaseTest(unittest.TestCase):
    def test_example_facts_are_valid(self):
        facts = kb.load(ROOT / "examples/deepstash-ru/facts.jsonl")
        self.assertEqual(kb.check(facts), [])

    def test_missing_source_is_an_error(self):
        bad = {"fact_id": "F-2026-01-01-001", "claim": "x", "as_of": "2026", "checked": "2026-01-01",
               "source": "no link", "evidence": "E1", "criteria": [], "tags": [], "used_by": []}
        self.assertTrue(any("source" in e for e in kb.check([bad])))

    def good(self, **fields):
        return {"fact_id": "F-2026-01-01-001", "claim": "x", "as_of": "2026", "checked": "2026-01-01",
                "source": "[s](https://example.com)", "evidence": "E1", "criteria": ["P"], "tags": ["t"],
                "used_by": ["i"], **fields}

    def test_wrong_types_are_line_errors_not_crashes(self):
        bad = self.good(evidence=["E1: item", "E2: item"], source=["s", "https://example.com"],
                        criteria="P,B", tags="t", used_by="i", checked=20260101)
        errors = kb.check([self.good(fact_id="F-2026-01-01-000"), bad])
        for field in ("evidence", "source", "criteria", "tags", "used_by", "checked"):
            self.assertTrue(any(e.startswith("line 2 ") and field in e for e in errors), field)
        self.assertTrue(any("evidence" in e and "got dict" in e for e in kb.check([self.good(evidence={"E1": "x"})])))

    def test_broken_lines_report_file_line_numbers(self):
        import tempfile
        with tempfile.TemporaryDirectory() as tmp:
            path = Path(tmp) / "facts.jsonl"
            path.write_text(json.dumps(self.good()) + "\n\nnot json\n[1, 2]\n", encoding="utf-8")
            rows = kb.read(path)
            errors = kb.check([fact for _, fact in rows], [n for n, _ in rows])
            self.assertEqual(len(kb.load(path)), 1)
        self.assertTrue(any(e.startswith("line 3 (?): not valid JSON") for e in errors))
        self.assertTrue(any(e.startswith("line 4 (?): atom must be a JSON object") for e in errors))

    def test_legacy_ids_are_accepted_only_from_the_list(self):
        old = self.good(fact_id="F-2025-01-01-07-001-2")
        self.assertTrue(any("fact_id" in e for e in kb.check([old], legacy=frozenset())))
        self.assertEqual(kb.check([old], legacy=frozenset({"F-2025-01-01-07-001-2"})), [])

    def test_find_tolerates_malformed_atoms(self):
        self.assertTrue(kb.matches(self.good(criteria="P", tags="t"), "p"))
        self.assertFalse(kb.matches({"claim": None, "tags": 1}, "p"))


if __name__ == "__main__":
    unittest.main()
