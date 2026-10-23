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

    def test_same_pattern_as_close_merged_issue(self):
        self.assertEqual(ckk.KEYWORD_PATTERN.pattern, cmi.KEYWORD_PATTERN.pattern)
        self.assertEqual(ckk.KEYWORD_PATTERN.flags, cmi.KEYWORD_PATTERN.flags)

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
