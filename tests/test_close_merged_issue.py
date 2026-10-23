"""bin/close_merged_issue.py の判定を，gh api の応答を差し替えて確かめる．

実行: python3 -B -m unittest discover -s tests -v （リポジトリのルートで．-B で __pycache__ を作らない）
gh・git・.claude/ai-loop.json は使わない（gh_api と load_config を差し替える）．
"""
import contextlib
import importlib.util
import io
import os
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))
SPEC = importlib.util.spec_from_file_location(
    "close_merged_issue", os.path.join(HERE, "..", "bin", "close_merged_issue.py"))
cmi = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(cmi)

REPO = "example-owner/example-repo"


class Fake:
    """gh api の応答を返し，呼び出しを記録する．"""

    def __init__(self, pr, issues=None, github_default="main"):
        self.pr = pr
        self.issues = issues or {}
        self.github_default = github_default
        self.calls = []

    def __call__(self, args, what):
        self.calls.append(args)
        if args[0] == "-X" and args[1] == "POST":
            return {"id": 1}
        if args[0] == "-X" and args[1] == "PATCH":
            n = int(args[2].rsplit("/", 1)[1])
            self.issues[n] = dict(self.issues[n], state="closed", state_reason="completed")
            return {}
        path = args[0]
        if path == "repos/%s" % REPO:
            return {"default_branch": self.github_default}
        if path.startswith("repos/%s/pulls/" % REPO):
            return self.pr
        if path.startswith("repos/%s/issues/" % REPO):
            return self.issues[int(path.rsplit("/", 1)[1])]
        raise AssertionError("想定外の呼び出し: %r" % (args,))

    def writes(self):
        return [c for c in self.calls if c[0] == "-X"]


def pr(base="develop", body="Closes #7", merged=True):
    return {"base": {"ref": base}, "body": body, "merged_at": "2026-10-23T00:00:00Z" if merged else None}


OPEN7 = {7: {"state": "open", "state_reason": None}}


class CloseMergedIssueTest(unittest.TestCase):
    def run_main(self, fake, argv, enabled=True, allowed=("main", "develop")):
        cmi.gh_api = fake
        cmi.load_config = lambda: (REPO, "main", enabled, list(allowed))
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cmi.main(argv)
        print("\n--- %s ---\n%s" % (" ".join(argv), out.getvalue().rstrip()))
        return code, out.getvalue()

    def assert_not_closed(self, fake, code, out, ng):
        self.assertEqual(code, 1)
        self.assertIn("判定: 閉じない", out)
        self.assertIn("[NG] %s" % ng, out)
        self.assertEqual(fake.writes(), [])

    def test_all_satisfied_closes_without_approval(self):
        fake = Fake(pr(), dict(OPEN7))
        code, out = self.run_main(fake, ["5"])
        self.assertEqual(code, 0)
        self.assertIn("判定: 閉じる", out)
        self.assertEqual(fake.writes(), [
            ["-X", "POST", "repos/%s/issues/7/comments" % REPO, "-f", "body=PR #5（base：develop）のマージで完了"],
            ["-X", "PATCH", "repos/%s/issues/7" % REPO, "-f", "state=closed", "-f", "state_reason=completed"],
        ])
        self.assertIn("クローズ: #7 の state=closed，state_reason=completed", out)

    def test_dry_run_does_not_write(self):
        fake = Fake(pr(), dict(OPEN7))
        code, out = self.run_main(fake, ["5", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("判定: 閉じる（--dry-run のため，コメントもクローズもしない）", out)
        self.assertEqual(fake.writes(), [])

    def test_dry_run_reports_ng(self):
        fake = Fake(pr(base="main"), dict(OPEN7))
        code, out = self.run_main(fake, ["5", "--dry-run"])
        self.assertEqual(code, 1)
        self.assertIn("判定: 閉じない（--dry-run", out)
        self.assertEqual(fake.writes(), [])

    def test_setting_false(self):
        fake = Fake(pr(), dict(OPEN7))
        self.assert_not_closed(fake, *self.run_main(fake, ["5"], enabled=False), ng="C1")

    def test_not_merged(self):
        fake = Fake(pr(merged=False), dict(OPEN7))
        self.assert_not_closed(fake, *self.run_main(fake, ["5"]), ng="C2")

    def test_default_branch_merge(self):
        fake = Fake(pr(base="main"), dict(OPEN7))
        self.assert_not_closed(fake, *self.run_main(fake, ["5"]), ng="C3")

    def test_base_not_allowed(self):
        fake = Fake(pr(base="feature-x"), dict(OPEN7))
        self.assert_not_closed(fake, *self.run_main(fake, ["5"]), ng="C4")

    def test_no_keyword(self):
        fake = Fake(pr(body="変更の説明だけ"), dict(OPEN7))
        self.assert_not_closed(fake, *self.run_main(fake, ["5"]), ng="C5")

    def test_refs_only(self):
        fake = Fake(pr(body="Refs #7"), dict(OPEN7))
        self.assert_not_closed(fake, *self.run_main(fake, ["5"]), ng="C5")

    def test_multiple_keywords(self):
        fake = Fake(pr(body="Closes #7\nFixes #8"), {7: OPEN7[7], 8: OPEN7[7]})
        self.assert_not_closed(fake, *self.run_main(fake, ["5"]), ng="C5")

    def test_keyword_and_refs_closes_keyword_one(self):
        fake = Fake(pr(body="resolved #7（Refs #3）"), dict(OPEN7))
        code, out = self.run_main(fake, ["5", "--dry-run"])
        self.assertEqual(code, 0)
        self.assertIn("抽出：#7）", out)

    def test_issue_option_mismatch(self):
        fake = Fake(pr(), dict(OPEN7))
        self.assert_not_closed(fake, *self.run_main(fake, ["5", "--issue", "9"]), ng="C5")

    def test_issue_option_match(self):
        fake = Fake(pr(), dict(OPEN7))
        code, _ = self.run_main(fake, ["5", "--issue", "7", "--dry-run"])
        self.assertEqual(code, 0)

    def test_issue_already_closed(self):
        fake = Fake(pr(), {7: {"state": "closed", "state_reason": "completed"}})
        self.assert_not_closed(fake, *self.run_main(fake, ["5"]), ng="C6")

    def test_number_is_pr(self):
        fake = Fake(pr(), {7: {"state": "open", "pull_request": {}}})
        self.assert_not_closed(fake, *self.run_main(fake, ["5"]), ng="C6")

    def test_gh_failure_stops(self):
        def failing(args, what):
            raise cmi.Stop("%s：gh api が終了コード 1 で失敗した" % what)
        cmi.gh_api = failing
        cmi.load_config = lambda: (REPO, "main", True, ["main", "develop"])
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = cmi.main(["5"])
        self.assertEqual(code, 2)
        self.assertIn("停止: PR の取得", out.getvalue())


if __name__ == "__main__":
    unittest.main()
