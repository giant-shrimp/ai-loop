"""bin/check_closing_keywords.py の判定を，作業用ディレクトリに書いた本文で確かめる．

実行: python3 -B -m unittest discover -s tests -v （リポジトリのルートで．-B で __pycache__ を作らない）
"""
import contextlib
import importlib.util
import io
import os
import tempfile
import unittest

HERE = os.path.dirname(os.path.abspath(__file__))


def load(name):
    spec = importlib.util.spec_from_file_location(name, os.path.join(HERE, "..", "bin", name + ".py"))
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


ckk = load("check_closing_keywords")
cmi = load("close_merged_issue")


class CheckClosingKeywordsTest(unittest.TestCase):
    def setUp(self):
        self.tmp = tempfile.TemporaryDirectory()
        self.addCleanup(self.tmp.cleanup)

    def run_main(self, body):
        path = os.path.join(self.tmp.name, "body.md")
        with open(path, "w", encoding="utf-8") as f:
            f.write(body)
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ckk.main(["check_closing_keywords.py", path])
        return code, out.getvalue()

    def test_same_keyword_part_as_close_merged_issue(self):
        # 閉じるキーワードの部分（KEYWORD_PREFIX）と #N の形は close_merged_issue.py と同じ．
        # owner/repo#N と URL の形はこのスクリプトだけが取り出す（close_merged_issue.py の規則は変えない）
        self.assertTrue(cmi.KEYWORD_PATTERN.pattern.startswith(ckk.KEYWORD_PREFIX))
        self.assertEqual(ckk.KEYWORD_PATTERN.pattern, cmi.KEYWORD_PATTERN.pattern)
        self.assertEqual(ckk.KEYWORD_PATTERN.flags, cmi.KEYWORD_PATTERN.flags)
        for pattern in (ckk.CROSS_PATTERN, ckk.URL_PATTERN):
            self.assertTrue(pattern.pattern.startswith(ckk.KEYWORD_PREFIX))
            self.assertEqual(pattern.flags, cmi.KEYWORD_PATTERN.flags)

    def test_first_line_only(self):
        code, out = self.run_main("Closes #12\n\n## 変更\n- #3 で決めた動作を変える\n")
        self.assertEqual(code, 0)
        self.assertIn("1行目: #12", out)
        self.assertIn("判定: 検出なし", out)

    def test_keyword_in_record(self):
        code, out = self.run_main("Closes #12\n\n## 記録\n| PR #5 | 本文は Closes #4 |\n")
        self.assertEqual(code, 1)
        self.assertIn("[NG] 4行目に閉じるキーワードと番号がある（#4）", out)
        self.assertIn("判定: 検出あり", out)

    def test_variants_and_case(self):
        code, out = self.run_main("Closes #12\nfixed #3\nRESOLVES #4 と resolve  #5\n")
        self.assertEqual(code, 1)
        self.assertIn("[NG] 2行目に閉じるキーワードと番号がある（#3）", out)
        self.assertIn("[NG] 3行目に閉じるキーワードと番号がある（#4・#5）", out)

    def test_two_on_first_line(self):
        code, out = self.run_main("Closes #12, closes #13\n")
        self.assertEqual(code, 1)
        self.assertIn("[NG] 1行目に閉じるキーワードと番号が 2 個ある", out)

    def test_reference_without_keyword(self):
        code, out = self.run_main("Closes #12\n\n- Refs #4\n- 本文の閉じるキーワードは #4 を指す\n- Closes #<番号>\n")
        self.assertEqual(code, 0)
        self.assertIn("判定: 検出なし", out)

    def test_cross_repo_in_record(self):
        code, out = self.run_main("Closes #12\n\n- 本文は fixes example-owner/example.repo#4\n")
        self.assertEqual(code, 1)
        self.assertIn("[NG] 3行目に閉じるキーワードと番号がある（example-owner/example.repo#4）", out)

    def test_url_in_record(self):
        code, out = self.run_main(
            "Closes #12\n\n- Resolved https://github.com/example-owner/example-repo/issues/4\n"
            "- closes http://github.com/example-owner/example-repo/issues/5\n")
        self.assertEqual(code, 1)
        self.assertIn("[NG] 3行目に閉じるキーワードと番号がある（URL example-owner/example-repo#4）", out)
        self.assertIn("[NG] 4行目に閉じるキーワードと番号がある（URL example-owner/example-repo#5）", out)

    def test_cross_repo_on_first_line(self):
        code, out = self.run_main("Closes example-owner/example-repo#12\n")
        self.assertEqual(code, 1)
        self.assertIn("1行目: example-owner/example-repo#12", out)
        self.assertIn("[NG] 1行目に閉じるキーワードと owner/repo#N または URL の形がある"
                      "（example-owner/example-repo#12）", out)

    def test_url_on_first_line_with_local(self):
        code, out = self.run_main("Closes #12 closes https://github.com/example-owner/example-repo/issues/13\n")
        self.assertEqual(code, 1)
        self.assertIn("1行目: #12・URL example-owner/example-repo#13", out)
        self.assertNotIn("個ある", out)
        self.assertIn("[NG] 1行目に閉じるキーワードと owner/repo#N または URL の形がある"
                      "（URL example-owner/example-repo#13）", out)

    def test_cross_repo_and_url_without_keyword(self):
        code, out = self.run_main(
            "Closes #12\n\n- example-owner/example-repo#4 を参照\n"
            "- https://github.com/example-owner/example-repo/issues/5\n"
            "- Refs example-owner/example-repo#6\n")
        self.assertEqual(code, 0)
        self.assertIn("1行目: #12", out)
        self.assertIn("判定: 検出なし", out)

    def test_no_keyword(self):
        code, out = self.run_main("## 変更\n- 文書だけ\n")
        self.assertEqual(code, 0)
        self.assertIn("1行目: 閉じるキーワードなし", out)

    def test_empty_body(self):
        code, out = self.run_main("")
        self.assertEqual(code, 0)
        self.assertIn("判定: 検出なし", out)

    def test_unreadable_file(self):
        out = io.StringIO()
        with contextlib.redirect_stdout(out):
            code = ckk.main(["check_closing_keywords.py", os.path.join(self.tmp.name, "none.md")])
        self.assertEqual(code, 2)
        self.assertIn("停止:", out.getvalue())


if __name__ == "__main__":
    unittest.main()
