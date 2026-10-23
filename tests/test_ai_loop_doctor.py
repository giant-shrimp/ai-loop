"""bin/ai_loop_doctor.py の D13 の判定（deny の同じ意味の書き方・検証コマンドの置き場所）を確かめる．

実行: python3 -B -m unittest discover -s tests -v （リポジトリのルートで．-B で __pycache__ を作らない）
"""
import importlib.util
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    "ai_loop_doctor", os.path.join(HERE, "..", "bin", "ai_loop_doctor.py"))
doctor = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(doctor)

sat = doctor.deny_satisfies


class EditRule(unittest.TestCase):
    def test_exact(self):
        self.assertTrue(sat("Edit(a/b.sh)", ["Edit(a/b.sh)"]))

    def test_dot_slash(self):
        self.assertTrue(sat("Edit(a/b.sh)", ["Edit(./a/b.sh)"]))

    def test_leading_slash_not_accepted(self):
        self.assertFalse(sat("Edit(a/b.sh)", ["Edit(/a/b.sh)"]))

    def test_other_path(self):
        self.assertFalse(sat("Edit(a/b.sh)", ["Edit(a/c.sh)"]))


class BashRule(unittest.TestCase):
    def test_exact_star(self):
        self.assertTrue(sat("Bash(gh pr merge*)", ["Bash(gh pr merge*)"]))

    def test_two_lines(self):
        self.assertTrue(sat("Bash(gh pr merge*)", ["Bash(gh pr merge)", "Bash(gh pr merge *)"]))

    def test_one_line_only(self):
        self.assertFalse(sat("Bash(gh pr merge*)", ["Bash(gh pr merge)"]))
        self.assertFalse(sat("Bash(gh pr merge*)", ["Bash(gh pr merge *)"]))

    def test_push_main_middle_star(self):
        deny = ["Bash(git push * main)", "Bash(git push * main *)"]
        self.assertTrue(sat("Bash(git push origin main*)", deny))

    def test_force_needs_bare_form(self):
        self.assertFalse(sat("Bash(git push -f*)", ["Bash(git push -f *)"]))

    def test_colon_star(self):
        self.assertTrue(sat("Bash(gh pr merge*)", ["Bash(gh pr merge:*)"]))

    def test_non_string_ignored(self):
        self.assertFalse(sat("Bash(gh pr merge*)", [None, 3]))


class VerifyPaths(unittest.TestCase):
    def test_paths(self):
        with tempfile.TemporaryDirectory() as top:
            for rel in (".claude/ai-loop/verify.sh", "scripts/verify.sh"):
                path = os.path.join(top, rel)
                os.makedirs(os.path.dirname(path), exist_ok=True)
                open(path, "w").close()
            self.assertEqual(
                doctor.verify_paths(top, "bash .claude/ai-loop/verify.sh"),
                [".claude/ai-loop/verify.sh"])
            self.assertEqual(doctor.verify_paths(top, "./scripts/verify.sh"), ["scripts/verify.sh"])
            self.assertEqual(doctor.verify_paths(top, "pytest -q"), [])


class RequiredDeny(unittest.TestCase):
    def test_edit_lines_from_verify_files(self):
        req = doctor.required_deny("main", "settings.json", ["scripts/verify.sh"])
        self.assertIn("Edit(scripts/verify.sh)", req)
        self.assertNotIn("Edit(.claude/ai-loop/verify.sh)", req)
        self.assertNotIn("Edit(scripts/verify.sh)", doctor.required_deny("main", "settings.json"))


if __name__ == "__main__":
    unittest.main()
