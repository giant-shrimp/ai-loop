#!/usr/bin/env python3
"""ai-loop を使う側のリポジトリに，設定・検証コマンド・settings・records の雛形を作る．

リポジトリのルートで実行する．既存のファイルは上書きしない（SKIPPED と出す）．
コミット・push・PR の作成はしない．作った後は，同じ bin の ai_loop_doctor.py で診断する．

使い方:
    python3 <プラグインのパス>/bin/ai_loop_init.py --mode {normal,local}
        (--test-command "<コマンド>" | --no-tests)
        [--default-branch <名前>] [--show-titles]
        [--deny-secret <パス> ...] [--dry-run]

    --dry-run では何も書かず，作るファイルの全文を出す．人はこの出力を確かめて承認する．

前提の検査（どれかが NG なら何も書かずに終了コード 2）:
    カレントディレクトリがリポジトリのルート・gh repo view が成功する・
    origin の URL の末尾が <repo> または <repo>.git と一致する・default_branch が決まる・
    local のとき .claude/ の下に追跡済みのファイルがない

終了コード:
    0  前提の検査を通り，書くべきものを書いた（SKIPPED があっても 0）
    1  書き込みに失敗した
    2  前提の検査が NG

出力に URL・アカウント名・絶対パスを出さない（--dry-run で示す .claude/ai-loop.json の
repo の値を除く）．
"""
import argparse
import json
import os
import subprocess
import sys

RECORD_FILES = (".claude/ai-loop/ERRORS.md", ".claude/ai-loop/errors_inventory.md",
                ".claude/ai-loop/decisions/.keep", ".claude/ai-loop/trials/.keep")
VERIFY_PATH = ".claude/ai-loop/verify.sh"

VERIFY_TESTS = """#!/usr/bin/env bash
# ai-loop の検証コマンド（ai_loop_init.py が生成）
# カレントディレクトリのリポジトリを検査する（$0 を基準にしない．commander の worktree での検証のため）
cd "$(git rev-parse --show-toplevel)" || { echo "verify: not a git repository, 1 failed"; echo "VERIFY FAILED"; exit 1; }
if {
  %s
}; then
  echo "verify: test command exit 0, 0 failed"
  echo "VERIFY PASSED"; exit 0
else
  rc=$?
  echo "verify: test command exit $rc, 1 failed"
  echo "VERIFY FAILED"; exit 1
fi
"""

VERIFY_NO_TESTS = """#!/usr/bin/env bash
# ai-loop の検証コマンド（ai_loop_init.py が生成．テストなし：形の検査のみ）
cd "$(git rev-parse --show-toplevel)" || { echo "verify: not a git repository, 1 failed"; echo "VERIFY FAILED"; exit 1; }
echo "verify: no tests; syntax checks only"
fail=0; n=0
while IFS= read -r -d '' f; do
  n=$((n+1))
  case "$f" in
    *.py)   python3 -c 'import ast,sys; ast.parse(open(sys.argv[1], encoding="utf-8").read())' "$f" || { echo "NG python: $f"; fail=$((fail+1)); } ;;
    *.sh)   bash -n "$f" || { echo "NG bash: $f"; fail=$((fail+1)); } ;;
    *.json) python3 -m json.tool "$f" > /dev/null || { echo "NG json: $f"; fail=$((fail+1)); } ;;
  esac
done < <(git ls-files -z -- '*.py' '*.sh' '*.json')
echo "verify: checked $n files, $fail failed"
if [ "$fail" -eq 0 ]; then echo "VERIFY PASSED"; exit 0; else echo "VERIFY FAILED"; exit 1; fi
"""


def run(args, cwd=None):
    """コマンドを実行し，(終了コード, 標準出力) を返す．見つからなければ (None, "")．"""
    try:
        p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=60)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, ""
    return p.returncode, p.stdout


def origin_matches(url, repo):
    """URL の末尾が <repo> または <repo>.git と一致するか（前は / か : で区切られていること）．"""
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url == repo or url.endswith("/" + repo) or url.endswith(":" + repo)


def make_config(repo, branch, show_titles):
    config = {
        "repo": repo,
        "default_branch": branch,
        "python": "python3",
        "verify": {
            "command": "bash %s" % VERIFY_PATH,
            "pass_marker": "VERIFY PASSED",
            "fail_marker": "VERIFY FAILED",
            "summary_markers": [" failed", "VERIFY "],
            "deny": True,
        },
        "scanners": [
            {"name": "個人情報走査", "command": "check_no_personal_info.py", "added_lines_only": False},
        ],
        "extra_checks": [],
        "report": {"show_titles": show_titles},
        "records": {
            "errors": ".claude/ai-loop/ERRORS.md",
            "errors_inventory": ".claude/ai-loop/errors_inventory.md",
            "decisions": ".claude/ai-loop/decisions/",
            "trials": ".claude/ai-loop/trials/",
        },
    }
    return json.dumps(config, ensure_ascii=False, indent=2) + "\n"


def deny_lines(branch, settings_name, secrets):
    lines = [
        "Edit(.claude/ai-loop.json)",
        "Write(.claude/ai-loop.json)",
        "Edit(%s)" % VERIFY_PATH,
        "Write(%s)" % VERIFY_PATH,
        "Edit(.claude/%s)" % settings_name,
        "Write(.claude/%s)" % settings_name,
        "Bash(git push origin %s*)" % branch,
        "Bash(git push -f*)",
        "Bash(git push --force*)",
        "Bash(gh pr merge*)",
        "Bash(gh issue close*)",
    ]
    for s in secrets:
        s = s[2:] if s.startswith("./") else s
        lines += ["Read(./%s)" % s, "Edit(./%s)" % s]
    return lines


def make_settings(deny):
    settings = {"attribution": {"commit": "", "pr": ""}, "permissions": {"deny": deny, "ask": []}}
    return json.dumps(settings, ensure_ascii=False, indent=2) + "\n"


def missing_settings(path, deny):
    """既存の settings に足りないもの（attribution・deny の各行）の一覧を返す．読めなければ None．"""
    try:
        with open(path, encoding="utf-8") as f:
            settings = json.load(f)
    except (ValueError, OSError):
        return None
    if not isinstance(settings, dict):
        return None
    missing = []
    attribution = settings.get("attribution")
    if not (isinstance(attribution, dict) and attribution.get("commit") == "" and attribution.get("pr") == ""):
        missing.append('attribution（{"commit": "", "pr": ""}）')
    perms = settings.get("permissions")
    have = perms.get("deny") if isinstance(perms, dict) else None
    have = have if isinstance(have, list) else []
    missing += ["permissions.deny: %s" % d for d in deny if d not in have]
    return missing


def precheck(args):
    """前提を検査し，(repo, default_branch) を返す．NG なら理由の一覧を返す．"""
    code, out = run(["git", "rev-parse", "--show-toplevel"])
    if code != 0:
        return None, ["git のリポジトリの中で実行する"]
    top = out.strip()
    errors = []
    if os.path.realpath(os.getcwd()) != os.path.realpath(top):
        errors.append("リポジトリのルートで実行していない（git rev-parse --show-toplevel に移ってから実行する）")
    code, out = run(["gh", "repo", "view", "--json", "nameWithOwner,defaultBranchRef"], cwd=top)
    try:
        info = json.loads(out) if code == 0 else None
    except ValueError:
        info = None
    if not isinstance(info, dict) or not info.get("nameWithOwner"):
        errors.append("gh repo view が失敗した（gh の認証と，リポジトリの GitHub 上の所在を確かめる）")
        return None, errors
    repo = info["nameWithOwner"]
    code, url = run(["git", "remote", "get-url", "origin"], cwd=top)
    if code != 0:
        errors.append("origin がない（git remote add origin で GitHub のリポジトリを足す）")
    elif not origin_matches(url, repo):
        errors.append("origin の URL の末尾が gh repo view のリポジトリと一致しない（origin か gh の既定のリポジトリを直す）")
    ref = info.get("defaultBranchRef") or {}
    branch = args.default_branch or ref.get("name") or ""
    if not branch:
        errors.append("既定ブランチを GitHub から取得できない（--default-branch で指定する）")
    if args.mode == "local":
        _, tracked = run(["git", "ls-files", ".claude"], cwd=top)
        if tracked.strip():
            errors.append(".claude/ の下に追跡済みのファイルがあり，除外が効かない（追跡から外すか normal 方式にする）")
    if errors:
        return None, errors
    return (repo, branch), []


def main():
    parser = argparse.ArgumentParser(description="ai-loop の設定の雛形を作る")
    parser.add_argument("--mode", choices=("normal", "local"), required=True)
    tests = parser.add_mutually_exclusive_group(required=True)
    tests.add_argument("--test-command")
    tests.add_argument("--no-tests", action="store_true")
    parser.add_argument("--default-branch")
    parser.add_argument("--show-titles", action="store_true")
    parser.add_argument("--deny-secret", action="append", default=[])
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args()

    result, errors = precheck(args)
    if errors:
        for e in errors:
            print("NG: %s" % e)
        print("前提の検査が NG のため，何も書いていない")
        return 2
    repo, branch = result

    settings_name = "settings.local.json" if args.mode == "local" else "settings.json"
    settings_path = ".claude/%s" % settings_name
    deny = deny_lines(branch, settings_name, args.deny_secret)
    verify = VERIFY_NO_TESTS if args.no_tests else VERIFY_TESTS % args.test_command
    files = [(".claude/ai-loop.json", make_config(repo, branch, args.show_titles)),
             (VERIFY_PATH, verify),
             (settings_path, make_settings(deny))]
    files += [(p, "") for p in RECORD_FILES]

    print("方式: %s / 既定ブランチ: %s%s" % (args.mode, branch, " / --dry-run（何も書かない）" if args.dry_run else ""))
    try:
        for path, content in files:
            if os.path.exists(path):
                print("SKIPPED %s（既存のため変更しない）" % path)
                if path == settings_path:
                    missing = missing_settings(path, deny)
                    if missing is None:
                        print("  JSON として読めないため，足りないものを判定できない")
                    for m in missing or []:
                        print("  足りない: %s" % m)
                continue
            if args.dry_run:
                print("WOULD CREATE %s" % path)
                if content:
                    print("----- %s -----" % path)
                    print(content, end="")
                    print("----- ここまで -----")
                continue
            os.makedirs(os.path.dirname(path), exist_ok=True)
            with open(path, "w", encoding="utf-8") as f:
                f.write(content)
            if path == VERIFY_PATH:
                os.chmod(path, 0o755)
            print("CREATED %s" % path)
        if args.mode == "local":
            _, git_path = run(["git", "rev-parse", "--git-path", "info/exclude"])
            exclude = git_path.strip()
            try:
                with open(exclude, encoding="utf-8") as f:
                    has_line = "/.claude/" in [l.strip() for l in f]
            except FileNotFoundError:
                has_line = False
            if has_line:
                print("SKIPPED .git/info/exclude の /.claude/（同じ行がある）")
            elif args.dry_run:
                print("WOULD APPEND .git/info/exclude に /.claude/")
            else:
                os.makedirs(os.path.dirname(exclude), exist_ok=True)
                with open(exclude, "a+", encoding="utf-8") as f:
                    f.seek(0)
                    text = f.read()
                    f.write(("" if text.endswith("\n") or not text else "\n") + "/.claude/\n")
                print("APPENDED .git/info/exclude に /.claude/")
    except OSError as e:
        print("書き込みに失敗した: %s" % type(e).__name__)
        return 1

    if args.no_tests:
        print("テストがないため，検証は形の検査だけになる．1件目の案として「テストの追加」を勧める")
    if not args.dry_run:
        print("次: 同じ bin の ai_loop_doctor.py を実行する%s" % ("（--mode local を付ける）" if args.mode == "local" else ""))
    return 0


if __name__ == "__main__":
    sys.exit(main())
