#!/usr/bin/env python3
"""PR 本文のファイルで，閉じるキーワードが先頭の1行だけにあることを確かめる．

publish-github が PR を作る前に，commander が PR 本文を確定するときと Web で作られた PR を照合するときに使う．
閉じるキーワード（close・fix・resolve 系とその活用形）の直後の #N を，close_merged_issue.py の C5 と
同じ規則で取り出す．次のどちらかに当たれば検出とする．

    - 2行目以降に閉じるキーワードと番号がある（記録や引用で，キーワードの直後に #N を置いた場合を含む）
    - 1行目に閉じるキーワードと番号が2つ以上ある

1行目に閉じるキーワードがないことは検出としない（出力の「1行目」の行で確かめる）．

使い方:
    check_closing_keywords.py 本文のファイル

終了コード:
    0  検出なし
    1  検出あり
    2  動けない（ファイルを読めない）
"""
import re
import sys

KEYWORD_PATTERN = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#([0-9]+)")


def check(text):
    """(1行目の番号の一覧, [(行番号, 番号の一覧)]) を返す．後者は2行目以降で検出した行．"""
    lines = text.splitlines()
    first = KEYWORD_PATTERN.findall(lines[0]) if lines else []
    others = []
    for i, line in enumerate(lines[1:], start=2):
        found = KEYWORD_PATTERN.findall(line)
        if found:
            others.append((i, found))
    return first, others


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
    first, others = check(text)
    print("1行目: %s" % ("・".join("#" + n for n in first) or "閉じるキーワードなし"))
    detected = False
    if len(first) > 1:
        print("[NG] 1行目に閉じるキーワードと番号が %d 個ある" % len(first))
        detected = True
    for i, found in others:
        print("[NG] %d行目に閉じるキーワードと番号がある（%s）" % (i, "・".join("#" + n for n in found)))
        detected = True
    print("判定: %s" % ("検出あり" if detected else "検出なし"))
    return 1 if detected else 0


if __name__ == "__main__":
    sys.exit(main(sys.argv))
