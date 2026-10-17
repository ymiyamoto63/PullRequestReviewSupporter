import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))

import generate_pr_summary as g  # noqa: E402

RULES = g.load_rules(g.DEFAULT_RULES)


def file(name, patch="", additions=1, deletions=0):
    return {"filename": name, "status": "modified", "additions": additions, "deletions": deletions, "patch": patch}


class DetectSensitiveTest(unittest.TestCase):
    def rule_ids(self, files):
        return [h["rule"]["id"] for h in g.detect_sensitive(files, RULES)]

    def test_matches_by_path(self):
        self.assertEqual(self.rule_ids([file("src/auth/login.py")]), ["auth"])
        self.assertEqual(self.rule_ids([file("db/migrations/0001_init.sql")]), ["database"])
        self.assertEqual(self.rule_ids([file(".github/workflows/ci.yml")]), ["infra"])

    def test_matches_by_keyword_in_changed_lines_only(self):
        added = file("src/app.py", "@@ -1 +1 @@\n+cur.execute('ALTER TABLE users ADD COLUMN x int')")
        context = file("src/app.py", "@@ -1 +1 @@\n ALTER TABLE users")
        self.assertEqual(self.rule_ids([added]), ["database"])
        self.assertEqual(self.rule_ids([context]), [])

    def test_keywords_are_ignored_in_tests_docs_and_ci_config(self):
        self.assertEqual(self.rule_ids([file("tests/test_db.py", "@@ -1 +1 @@\n+sql = 'ALTER TABLE users'")]), [])
        self.assertEqual(self.rule_ids([file("docs/setup.md", "@@ -1 +1 @@\n+Set the password here")]), [])
        self.assertEqual(self.rule_ids([file(".github/workflows/ci.yml", "@@ -1 +1 @@\n+permissions:")]), ["infra"])
        # パスによる検出はテストでも行う
        self.assertEqual(self.rule_ids([file("tests/migrations/0001.sql")]), ["database"])

    def test_high_severity_rules_come_first(self):
        ids = self.rule_ids([file("package.json"), file("src/api/users.py")])
        self.assertEqual(ids, ["api", "dependencies"])

    def test_unrelated_change_has_no_hits(self):
        self.assertEqual(self.rule_ids([file("docs/guide.md", "@@ -1 +1 @@\n+typo fix")]), [])


class ParseJsonContentTest(unittest.TestCase):
    def test_reads_fenced_json(self):
        self.assertEqual(g.parse_json_content('結果です\n```json\n{"a": 1}\n```'), {"a": 1})

    def test_rejects_text_without_json(self):
        with self.assertRaises(ValueError):
            g.parse_json_content("OK")


class NormalizeAiTest(unittest.TestCase):
    def test_drops_malformed_items_and_unknown_risk(self):
        ai = g.normalize_ai({
            "risk": "critical",
            "changes": [{"title": "A", "files": ["x.py", 1]}, {"before": "no title"}, "bad"],
            "diagram": {"nodes": [{"id": "n", "label": "N"}, {"label": "no id"}]},
            "approve_checklist": ["ok", "", 3],
        })
        self.assertIsNone(ai["risk"])
        self.assertEqual([c["title"] for c in ai["changes"]], ["A"])
        self.assertEqual(ai["changes"][0]["files"], ["x.py"])
        self.assertEqual([n["id"] for n in ai["nodes"]], ["n"])
        self.assertEqual(ai["checklist"], ["ok"])


class OverallRiskTest(unittest.TestCase):
    def test_takes_the_higher_of_rules_and_ai(self):
        hits = g.detect_sensitive([file("package.json")], RULES)
        self.assertEqual(g.overall_risk({"risk": "low"}, hits), "medium")
        self.assertEqual(g.overall_risk({"risk": "high"}, hits), "high")
        self.assertEqual(g.overall_risk(None, []), "low")


class MermaidTest(unittest.TestCase):
    def test_escapes_labels_and_skips_unknown_edges(self):
        text = g.build_mermaid(
            [{"id": "a", "label": 'Login "<script>"', "changed": True}, {"id": "b", "label": "DB", "changed": False}],
            [{"from": "a", "to": "b", "label": "書き込み"}, {"from": "a", "to": "zzz", "label": ""}],
        )
        self.assertNotIn("<script>", text)
        self.assertIn('n0 -- "書き込み" --> n1', text)
        self.assertNotIn("zzz", text)
        self.assertIn("class n0 changed", text)


if __name__ == "__main__":
    unittest.main()
