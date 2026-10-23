#!/usr/bin/env python3
"""PR 本文のファイルで，閉じるキーワードが先頭の1行だけにあることを確かめる．

publish-github が PR を作る前に，commander が PR 本文を確定するときと Web で作られた PR を照合するときに使う．
閉じるキーワード（close・fix・resolve 系とその活用形）の直後の次の形を取り出す．GitHub はどの形でも自動で閉じる．

    #N                                        close_merged_issue.py の C5 と同じ規則
    owner/repo#N                              別のリポジトリの Issue
    https://github.com/owner/repo/issues/N    Issue の URL

次のどれかに当たれば検出とする．

    - 2行目以降に，閉じるキーワードとどれかの形がある（記録や引用で，キーワードの直後に置いた場合を含む）
    - 1行目に，閉じるキーワードと #N が2つ以上ある
    - 1行目に，閉じるキーワードと owner/repo#N または URL の形がある（1行目に許すのは Closes #<Issue番号> だけ）

1行目に閉じるキーワードがないことは検出としない（出力の「1行目:」の行で確かめる）．

使い方:
    check_closing_keywords.py 本文のファイル

終了コード:
    0  検出なし
    1  検出あり
    2  動けない（ファイルを読めない）
"""
import re
import sys

# 閉じるキーワードと直後の空白．close_merged_issue.py の KEYWORD_PATTERN の先頭と同じ（テストで確かめる）
KEYWORD_PREFIX = r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+"
KEYWORD_PATTERN = re.compile(KEYWORD_PREFIX + r"#([0-9]+)")
REPO = r"([A-Za-z0-9-]+/[A-Za-z0-9._-]+)"
CROSS_PATTERN = re.compile(KEYWORD_PREFIX + REPO + r"#([0-9]+)")
URL_PATTERN = re.compile(KEYWORD_PREFIX + r"https?://github\.com/" + REPO + r"/issues/([0-9]+)")


def find(line):
    """(#N の一覧, owner/repo#N と URL の形の一覧) を返す．後者は表示用の文字列．"""
    local = ["#" + n for n in KEYWORD_PATTERN.findall(line)]
    other = ["%s#%s" % m for m in CROSS_PATTERN.findall(line)]
    other += ["URL %s#%s" % m for m in URL_PATTERN.findall(line)]
    return local, other


def check(text):
    """(1行目の #N の一覧, 1行目のその他の形の一覧, [(行番号, 形の一覧)]) を返す．最後は2行目以降で検出した行．"""
    lines = text.splitlines()
    first, first_other = find(lines[0]) if lines else ([], [])
    others = []
    for i, line in enumerate(lines[1:], start=2):
        local, other = find(line)
        if local or other:
            others.append((i, local + other))
    return first, first_other, others


def main(argv):
    if len(argv) != 2:
        print("使い方: check_closing_keywords.py 本文のファイル")
        return 2
    try:
        with open(argv[1], encoding="utf-8") as f:
            text = f.read()
    except (OSError, UnicodeDecodeError):
        print("停止: 本文のファイルを読めない")
        return 2
    first, first_other, others = check(text)
    print("1行目: %s" % ("・".join(first + first_other) or "閉じるキーワードなし"))
    detected = False
    if len(first) > 1:
        print("[NG] 1行目に閉じるキーワードと番号が %d 個ある" % len(first))
        detected = True
    if first_other:
        print("[NG] 1行目に閉じるキーワードと owner/repo#N または URL の形がある（%s）" % "・".join(first_other))
        detected = True
    for i, found in others:
        print("[NG] %d行目に閉じるキーワードと番号がある（%s）" % (i, "・".join(found)))
        detected = True
    print("判定: %s" % ("検出あり" if detected else "検出なし"))
    return 1 if detected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
