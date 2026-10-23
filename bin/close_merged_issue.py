#!/usr/bin/env python3
"""既定ブランチ以外へマージした PR の対応 Issue を，条件を確かめてから閉じる．

post-merge-cleanup が呼ぶ．リポジトリのルートで実行する．次をすべて満たすときだけ，
Issue に「PR #M（base：<ブランチ名>）のマージで完了」とコメントし，state_reason=completed で閉じる．
1つでも満たさなければ閉じない（コメントもしない）．

    C1  .claude/ai-loop.json の close_issue_on_non_default_merge が true（真偽値）
    C2  PR の merged_at が null でない
    C3  PR の base が GitHub の既定ブランチと違う
    C4  PR の base が allowed_base_branches（省略時は [default_branch]）に含まれる
    C5  PR 本文の閉じるキーワード（close・fix・resolve 系とその活用形）の直後の #N から，
        Issue 番号がちょうど1件に決まる（--issue を指定した場合は，その番号と一致する）．
        Refs などの参照だけの番号は数えない
    C6  その番号が PR でなく Issue で，state が open

使い方:
    close_merged_issue.py PR番号 [--issue Issue番号] [--dry-run]

    --dry-run  各条件の判定と，閉じるかどうかだけを出す．コメントもクローズもしない

終了コード:
    0  閉じた（--dry-run では，条件をすべて満たした）
    1  条件を満たさないので閉じなかった
    2  動けない（.claude/ai-loop.json を読めない・gh api の失敗・クローズの結果が違う）

設定ファイルの場所を変える引数は持たない（設定値の確認を引数で外せないようにするため）．
出力に URL・アカウント名を出さない．
"""
import argparse
import json
import os
import re
import subprocess
import sys

KEYWORD_PATTERN = re.compile(r"(?i)\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\s+#([0-9]+)")
SETTING_KEY = "close_issue_on_non_default_merge"


class Stop(Exception):
    """動けないときに投げる．メッセージをそのまま出して終了コード 2 で終わる．"""


def gh_api(args, what):
    """gh api を実行し，JSON を返す．失敗したら Stop（gh の標準エラー出力は出さない）．"""
    try:
        p = subprocess.run(["gh", "api"] + args, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        raise Stop("%s：gh を実行できない" % what)
    if p.returncode != 0:
        raise Stop("%s：gh api が終了コード %d で失敗した" % (what, p.returncode))
    try:
        return json.loads(p.stdout) if p.stdout.strip() else None
    except ValueError:
        raise Stop("%s：gh api の出力が JSON でない" % what)


def load_config():
    """リポジトリのルートの .claude/ai-loop.json を読み，(repo, default_branch, 設定値, 許可する base) を返す．"""
    try:
        top = subprocess.run(["git", "rev-parse", "--show-toplevel"], stdout=subprocess.PIPE,
                             stderr=subprocess.DEVNULL, text=True).stdout.strip()
    except FileNotFoundError:
        top = ""
    if not top:
        raise Stop("git のリポジトリの中で実行していない")
    try:
        with open(os.path.join(top, ".claude", "ai-loop.json"), encoding="utf-8") as f:
            config = json.load(f)
    except (OSError, ValueError):
        raise Stop(".claude/ai-loop.json を読めない")
    if not isinstance(config, dict):
        raise Stop(".claude/ai-loop.json がオブジェクトでない")
    repo, branch = config.get("repo"), config.get("default_branch")
    if not isinstance(repo, str) or not repo or not isinstance(branch, str) or not branch:
        raise Stop(".claude/ai-loop.json の repo・default_branch がない")
    allowed = config.get("allowed_base_branches", [branch])
    if (not isinstance(allowed, list) or not allowed
            or not all(isinstance(b, str) and b for b in allowed)):
        raise Stop(".claude/ai-loop.json の allowed_base_branches が空でない文字列の配列でない")
    return repo, branch, config.get(SETTING_KEY) is True, allowed


def judge(args):
    """条件を確かめ，(結果の一覧, PR の base, 対象の Issue 番号) を返す．結果は (記号, 真偽, 説明)．"""
    repo, _, enabled, allowed = load_config()
    pr = gh_api(["repos/%s/pulls/%d" % (repo, args.pr)], "PR の取得")
    github_default = gh_api(["repos/%s" % repo], "リポジトリの取得").get("default_branch")
    base = (pr.get("base") or {}).get("ref") or ""
    found = sorted({int(n) for n in KEYWORD_PATTERN.findall(pr.get("body") or "")})

    results = [
        ("C1", enabled, "%s が true（設定の値：%s）" % (SETTING_KEY, "true" if enabled else "true でない")),
        ("C2", pr.get("merged_at") is not None,
         "PR #%d の merged_at が null でない" % args.pr),
        ("C3", bool(base) and base != github_default,
         "PR の base（%s）が GitHub の既定ブランチ（%s）と違う" % (base, github_default)),
        ("C4", base in allowed,
         "PR の base（%s）が allowed_base_branches（%s）に含まれる" % (base, "・".join(allowed))),
    ]
    found_text = "・".join("#%d" % n for n in found) or "なし"
    if args.issue is None:
        ok5 = len(found) == 1
        text5 = "閉じるキーワードの Issue がちょうど1件（抽出：%s）" % found_text
    else:
        ok5 = found == [args.issue]
        text5 = "閉じるキーワードの Issue がちょうど1件で，指定の #%d と一致（抽出：%s）" % (args.issue, found_text)
    results.append(("C5", ok5, text5))

    target = found[0] if ok5 else None
    if target is None:
        results.append(("C6", False, "対象の Issue が open（C5 が NG のため確かめない）"))
    else:
        issue = gh_api(["repos/%s/issues/%d" % (repo, target)], "Issue の取得")
        is_pr = "pull_request" in issue
        state = issue.get("state")
        results.append(("C6", not is_pr and state == "open",
                        "#%d が Issue で state が open（種類：%s，state：%s）"
                        % (target, "PR" if is_pr else "Issue", state)))
    return repo, results, base, target


def close_issue(repo, pr_number, base, target):
    """コメントを付けて閉じ，取得し直して結果を確かめる．"""
    body = "PR #%d（base：%s）のマージで完了" % (pr_number, base)
    comment = gh_api(["-X", "POST", "repos/%s/issues/%d/comments" % (repo, target), "-f", "body=" + body],
                     "コメントの投稿")
    print("コメント: #%d に投稿した（id %s）：%s" % (target, (comment or {}).get("id"), body))
    gh_api(["-X", "PATCH", "repos/%s/issues/%d" % (repo, target),
            "-f", "state=closed", "-f", "state_reason=completed"],
           "クローズ（コメントは投稿済み）")
    issue = gh_api(["repos/%s/issues/%d" % (repo, target)], "クローズ後の取得")
    state, reason = issue.get("state"), issue.get("state_reason")
    print("クローズ: #%d の state=%s，state_reason=%s" % (target, state, reason))
    if state != "closed" or reason != "completed":
        raise Stop("クローズの結果が state=closed，state_reason=completed でない")


def main(argv=None):
    parser = argparse.ArgumentParser(description="既定ブランチ以外へマージした PR の対応 Issue を，条件を確かめてから閉じる")
    parser.add_argument("pr", type=int, help="マージした PR の番号")
    parser.add_argument("--issue", type=int, help="対応 Issue の番号（指定すると，抽出した番号と一致することも確かめる）")
    parser.add_argument("--dry-run", action="store_true", help="判定だけを出し，コメントもクローズもしない")
    args = parser.parse_args(argv)
    try:
        repo, results, base, target = judge(args)
        for code, ok, text in results:
            print("[%s] %s %s" % ("OK" if ok else "NG", code, text))
        all_ok = all(ok for _, ok, _ in results)
        if args.dry_run:
            print("判定: %s（--dry-run のため，コメントもクローズもしない）" % ("閉じる" if all_ok else "閉じない"))
            return 0 if all_ok else 1
        if not all_ok:
            print("判定: 閉じない（NG の条件がある）")
            return 1
        print("判定: 閉じる")
        close_issue(repo, args.pr, base, target)
        return 0
    except Stop as e:
        print("停止: %s" % e)
        return 2


if __name__ == "__main__":
    sys.exit(main())
