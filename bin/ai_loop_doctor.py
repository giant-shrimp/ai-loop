#!/usr/bin/env python3
"""ai-loop を使う側のリポジトリの導入状態を診断する．

リポジトリのルートで実行する．項目ごとに [OK]・[NG]・[SKIP] を出し，NG には直し方を出す．
前の項目が NG で検査できない項目は SKIP と出し，NG と数える．

使い方:
    python3 <プラグインのパス>/bin/ai_loop_doctor.py [--mode {normal,local}]
        [--verify-timeout 秒] [--skip-verify]

    --mode を省くと，git check-ignore -v .claude/ai-loop.json が info/exclude の行を示せば
    local，そうでなければ normal とする．

終了コード:
    0  全項目 OK
    1  NG または SKIP が1件以上
    2  doctor 自身が動けない（git のリポジトリでない・doctor の例外）

ファイルを変えない（verify.command の実行を除く）．コミット・push・設定の自動修正はしない．
出力に URL・アカウント名・絶対パスを出さない（verify の要約の行は，リポジトリのルートを
「.」，ホームを「~」に置き換えて出す）．
"""
import argparse
import json
import os
import shlex
import shutil
import subprocess
import sys

PLUGIN_ID = "ai-loop@ai-loop"
BIN_DIR = os.path.dirname(os.path.abspath(__file__))
RECORD_KEYS = ("errors", "errors_inventory", "decisions", "trials")
VERIFY_KEYS = (("command", str), ("pass_marker", str), ("fail_marker", str),
               ("summary_markers", list), ("deny", bool))


def run(args, cwd=None, timeout=60):
    """コマンドを実行し，(終了コード, 標準出力) を返す．見つからなければ (None, "")．"""
    try:
        p = subprocess.run(args, cwd=cwd, stdout=subprocess.PIPE, stderr=subprocess.DEVNULL,
                           text=True, timeout=timeout)
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return None, ""
    return p.returncode, p.stdout


class Report:
    def __init__(self):
        self.ok = 0
        self.ng = 0

    def put(self, status, code, title, fixes=(), notes=()):
        print("[%s]%s%s %s" % (status, " " * (5 - len(status)), code, title))
        for n in notes:
            print("       %s" % n)
        for f in fixes:
            print("       直し方: %s" % f)
        if status == "OK":
            self.ok += 1
        else:
            self.ng += 1

    def skip(self, code, title, reason):
        self.put("SKIP", code, "%s（%s）" % (title, reason))


def required_deny(branch, settings_name):
    return [
        "Edit(.claude/ai-loop.json)",
        "Write(.claude/ai-loop.json)",
        "Edit(.claude/ai-loop/verify.sh)",
        "Write(.claude/ai-loop/verify.sh)",
        "Edit(.claude/%s)" % settings_name,
        "Write(.claude/%s)" % settings_name,
        "Bash(git push origin %s*)" % branch,
        "Bash(git push -f*)",
        "Bash(git push --force*)",
        "Bash(gh pr merge*)",
        "Bash(gh issue close*)",
    ]


def check_config(config):
    """必須項目と型を調べ，足りない・型の違う項目名の一覧を返す．"""
    bad = []
    for key in ("repo", "default_branch"):
        if not isinstance(config.get(key), str) or not config.get(key):
            bad.append(key)
    verify = config.get("verify")
    if not isinstance(verify, dict):
        bad.append("verify")
    else:
        for key, typ in VERIFY_KEYS:
            if not isinstance(verify.get(key), typ) or (typ in (str, list) and not verify.get(key)):
                bad.append("verify.%s" % key)
    for key in ("scanners", "extra_checks"):
        if not isinstance(config.get(key), list):
            bad.append(key)
    records = config.get("records")
    if not isinstance(records, dict):
        bad.append("records")
    else:
        for key in RECORD_KEYS:
            if not isinstance(records.get(key), str) or not records.get(key):
                bad.append("records.%s" % key)
    return bad


def origin_matches(url, repo):
    """URL の末尾が <repo> または <repo>.git と一致するか（前は / か : で区切られていること）．"""
    url = url.strip().rstrip("/")
    if url.endswith(".git"):
        url = url[:-4]
    return url == repo or url.endswith("/" + repo) or url.endswith(":" + repo)


def sanitize(line, top):
    line = line.replace(top, ".")
    home = os.path.expanduser("~")
    if home and home != "/":
        line = line.replace(home, "~")
    return line


def detect_mode(top):
    code, out = run(["git", "check-ignore", "-v", ".claude/ai-loop.json"], cwd=top)
    source = out.split(":", 1)[0] if code == 0 else ""
    return "local" if source.endswith("info/exclude") else "normal"


def load_json(path):
    try:
        with open(path, encoding="utf-8") as f:
            return json.load(f), None
    except FileNotFoundError:
        return None, "ない"
    except (ValueError, OSError):
        return None, "JSON として読めない"


def diagnose(top, args):
    r = Report()
    mode = args.mode or detect_mode(top)
    print("方式: %s%s" % (mode, "（--mode で指定）" if args.mode else "（自動判定）"))
    settings_name = "settings.local.json" if mode == "local" else "settings.json"

    # D01
    if os.path.realpath(os.getcwd()) == os.path.realpath(top):
        r.put("OK", "D01", "リポジトリのルートで実行している")
    else:
        r.put("NG", "D01", "リポジトリのルートで実行していない",
              ["リポジトリのルート（git rev-parse --show-toplevel）に移ってから実行する"])

    # D02
    code, _ = run(["gh", "auth", "status"])
    gh_ok = code == 0
    if gh_ok:
        r.put("OK", "D02", "gh が認証済み")
    elif code is None:
        r.put("NG", "D02", "gh が見つからない", ["GitHub CLI（gh）を入れ，ユーザが `! gh auth login` を実行する"])
    else:
        r.put("NG", "D02", "gh が認証されていない", ["ユーザが `! gh auth login` を実行する"])

    # D03・D04
    config, err = load_json(os.path.join(top, ".claude", "ai-loop.json"))
    config_ok = False
    if err:
        r.put("NG", "D03", ".claude/ai-loop.json が%s" % err,
              ["docs/setup.md の 1 節に従って .claude/ai-loop.json を置く"])
        r.skip("D04", "必須項目", "D03 が NG")
    elif not isinstance(config, dict):
        r.put("NG", "D03", ".claude/ai-loop.json がオブジェクトでない",
              ["docs/config.md の例に従って書き直す（人が行う）"])
        r.skip("D04", "必須項目", "D03 が NG")
    else:
        r.put("OK", "D03", ".claude/ai-loop.json を読めた")
        bad = check_config(config)
        if bad:
            r.put("NG", "D04", "必須項目がない・型が違う: %s" % "・".join(bad),
                  ["docs/config.md の表に従って足す（設定ファイルは deny の対象なので人が編集する）"])
        else:
            r.put("OK", "D04", "必須項目がそろっている")
            config_ok = True

    repo = config.get("repo") if config_ok else None
    branch = config.get("default_branch") if config_ok else None

    # D05
    if not config_ok:
        r.skip("D05", "repo を gh で参照できる", "D04 が NG")
    elif not gh_ok:
        r.skip("D05", "repo を gh で参照できる", "D02 が NG")
    elif run(["gh", "api", "repos/%s" % repo, "--silent"])[0] == 0:
        r.put("OK", "D05", "repo を gh で参照できる")
    else:
        r.put("NG", "D05", "repo を gh で参照できない",
              ["repo の値（所有者/リポジトリ名）と，gh のアカウントの権限を確かめる"])

    # D06
    if not config_ok:
        r.skip("D06", "origin が repo を指す", "D04 が NG")
    else:
        code, out = run(["git", "remote", "get-url", "origin"], cwd=top)
        if code != 0:
            r.put("NG", "D06", "origin がない", ["git remote add origin で repo のリモートを足す"])
        elif origin_matches(out, repo):
            r.put("OK", "D06", "origin が repo を指す")
        else:
            r.put("NG", "D06", "origin が repo を指していない",
                  ["origin の URL か，.claude/ai-loop.json の repo を直す"])

    # D07
    branch_ok = False
    if not config_ok:
        r.skip("D07", "origin に既定ブランチがある", "D04 が NG")
    else:
        code, _ = run(["git", "ls-remote", "--exit-code", "--heads", "origin", branch], cwd=top)
        if code == 0:
            r.put("OK", "D07", "origin に既定ブランチ %s がある" % branch)
            branch_ok = True
        else:
            r.put("NG", "D07", "origin に既定ブランチ %s がない（または origin に接続できない）" % branch,
                  ["コミットが0件なら，最初のコミットを作り，ユーザが `! git push -u origin %s` を実行する" % branch])

    # D08
    if not config_ok:
        r.skip("D08", "records の置き場所がある", "D04 が NG")
    else:
        missing = []
        for key in RECORD_KEYS:
            path = config["records"][key]
            full = os.path.join(top, path)
            exists = os.path.isdir(full) if path.endswith("/") else os.path.exists(full)
            if not exists:
                missing.append(path)
        if missing:
            r.put("NG", "D08", "records の置き場所がない: %s" % "・".join(missing),
                  ["docs/setup.md の 4 節に従って空で作る（ディレクトリには .keep を置く）"])
        else:
            r.put("OK", "D08", "records の置き場所がある")

    # D09
    if not config_ok:
        r.skip("D09", "scanners の command が見つかる", "D04 が NG")
    else:
        missing = []
        for s in config["scanners"]:
            cmd = s.get("command", "") if isinstance(s, dict) else ""
            words = shlex.split(cmd) if cmd else []
            first = words[0] if words else ""
            if not first:
                found = False
            elif "/" in first:
                found = os.path.exists(os.path.join(top, first))
            else:
                found = bool(shutil.which(first)) or os.path.exists(os.path.join(BIN_DIR, first))
            if not found:
                missing.append(first or "（command が空）")
        if missing:
            r.put("NG", "D09", "scanners の command が見つからない: %s" % "・".join(missing),
                  ["プラグインの bin にある名前か，リポジトリのルートからのパスを書く"])
        else:
            r.put("OK", "D09", "scanners の command が見つかる")

    # D10・D11
    if not config_ok:
        r.skip("D10", "verify が合格する", "D04 が NG")
        r.skip("D11", "verify が追跡済みのファイルを変えない", "D04 が NG")
    elif args.skip_verify:
        r.skip("D10", "verify が合格する", "--skip-verify")
        r.skip("D11", "verify が追跡済みのファイルを変えない", "--skip-verify")
    else:
        verify = config["verify"]
        _, before = run(["git", "status", "--porcelain"], cwd=top)
        try:
            p = subprocess.run(verify["command"], shell=True, cwd=top, stdout=subprocess.PIPE,
                               stderr=subprocess.STDOUT, text=True, timeout=args.verify_timeout)
            code, out = p.returncode, p.stdout
        except subprocess.TimeoutExpired:
            code, out = None, ""
        _, after = run(["git", "status", "--porcelain"], cwd=top)
        lines = out.splitlines()
        summary = [sanitize(l, top) for l in lines
                   if any(m in l for m in verify["summary_markers"] if isinstance(m, str))]
        problems = []
        if code is None:
            problems.append("%d 秒で終わらない" % args.verify_timeout)
        else:
            if code != 0:
                problems.append("終了コードが %d" % code)
            if verify["pass_marker"] not in out:
                problems.append("pass_marker がない")
            if verify["fail_marker"] in out:
                problems.append("fail_marker がある")
            if not summary:
                problems.append("summary_markers に合う行がない")
        notes = ["要約: %s" % s for s in summary[-5:]]
        if problems:
            r.put("NG", "D10", "verify が合格しない: %s" % "・".join(problems),
                  ["リポジトリのルートで verify.command を実行して原因を直す．"
                   "目印の条件は docs/setup.md の 2 節を見る"], notes)
        else:
            r.put("OK", "D10", "verify が合格する", notes=notes)
        if code is None:
            r.skip("D11", "verify が追跡済みのファイルを変えない", "D10 が時間切れ")
        elif before == after:
            r.put("OK", "D11", "verify の前後で git status が変わらない")
        else:
            r.put("NG", "D11", "verify の前後で git status が変わった",
                  ["verify.command が作る・変えるファイルを，作らないようにするか .gitignore で除外する"])

    # D12・D13
    settings, err = load_json(os.path.join(top, ".claude", settings_name))
    if err or not isinstance(settings, dict):
        why = err or "オブジェクトでない"
        fix = ["docs/setup.md の 3 節に従って .claude/%s を置く" % settings_name]
        r.put("NG", "D12", ".claude/%s が%s" % (settings_name, why), fix)
        r.skip("D13", "settings の deny", "D12 が NG")
    else:
        attribution = settings.get("attribution")
        if isinstance(attribution, dict) and attribution.get("commit") == "" and attribution.get("pr") == "":
            r.put("OK", "D12", ".claude/%s の attribution が空" % settings_name)
        else:
            r.put("NG", "D12", ".claude/%s の attribution の commit・pr が空でない" % settings_name,
                  ['"attribution": {"commit": "", "pr": ""} を書く（人が編集する）'])
        if not config_ok:
            r.skip("D13", "settings の deny", "D04 が NG")
        else:
            perms = settings.get("permissions")
            deny = perms.get("deny") if isinstance(perms, dict) else None
            deny = deny if isinstance(deny, list) else []
            missing = [d for d in required_deny(branch, settings_name) if d not in deny]
            if missing:
                r.put("NG", "D13", ".claude/%s の deny に足りない行がある" % settings_name,
                      ["permissions.deny に次の行を足す（人が編集する）: %s" % "・".join(missing)])
            else:
                r.put("OK", "D13", ".claude/%s の deny がそろっている" % settings_name)

    # D14
    if mode != "local":
        r.put("OK", "D14", "除外の確認（normal のため対象外）")
    else:
        problems = []
        fixes = []
        _, path = run(["git", "rev-parse", "--git-path", "info/exclude"], cwd=top)
        path = path.strip()
        try:
            with open(os.path.join(top, path), encoding="utf-8") as f:
                has_line = "/.claude/" in [l.strip() for l in f]
        except OSError:
            has_line = False
        if not has_line:
            problems.append("info/exclude に /.claude/ の行がない")
            fixes.append("`.git/info/exclude` に /.claude/ の1行を足す（.gitignore には書かない）")
        if detect_mode(top) != "local":
            problems.append("git check-ignore が .claude/ai-loop.json の除外に info/exclude を示さない")
            if has_line:
                fixes.append("git check-ignore -v .claude/ai-loop.json で，除外を打ち消している行（! で始まる行など）を探して直す")
        _, tracked = run(["git", "ls-files", ".claude"], cwd=top)
        if tracked.strip():
            problems.append(".claude/ の下に追跡済みのファイルがある")
            fixes.append("git ls-files .claude で追跡済みのファイルを確かめ，追跡から外すか normal 方式にする")
        if problems:
            r.put("NG", "D14", "除外が効いていない: %s" % "・".join(problems), fixes)
        else:
            r.put("OK", "D14", ".claude/ が info/exclude で除外されている")

    # D15
    if mode != "normal":
        r.put("OK", "D15", "既定ブランチへの反映（local のため対象外）")
    elif not config_ok:
        r.skip("D15", "設定が既定ブランチに入っている", "D04 が NG")
    elif not branch_ok:
        r.skip("D15", "設定が既定ブランチに入っている", "D07 が NG")
    else:
        paths = [".claude/ai-loop.json", ".claude/settings.json"]
        paths += [w for w in shlex.split(config["verify"]["command"])
                  if os.path.isfile(os.path.join(top, w))]
        paths += [config["records"][k].rstrip("/") for k in RECORD_KEYS]
        missing = [p for p in paths
                   if run(["git", "cat-file", "-e", "origin/%s:%s" % (branch, p)], cwd=top)[0] != 0]
        if missing:
            r.put("NG", "D15", "origin/%s に入っていない: %s" % (branch, "・".join(missing)),
                  ["ブランチでコミットして PR を作り，ユーザがマージする．マージ後に git fetch origin を実行する"])
        else:
            r.put("OK", "D15", "設定が origin/%s に入っている" % branch)

    # D16
    code, out = run(["claude", "plugin", "list", "--json"])
    try:
        entries = json.loads(out) if code == 0 else None
    except ValueError:
        entries = None
    if entries is None:
        r.put("NG", "D16", "claude plugin list --json を読めない", ["Claude Code（claude）が PATH にあるか確かめる"])
    else:
        real_top = os.path.realpath(top)
        enabled = [e for e in entries if isinstance(e, dict) and e.get("id") == PLUGIN_ID and e.get("enabled")
                   and (e.get("scope") == "user"
                        or os.path.realpath(e.get("projectPath") or "/nonexistent") == real_top)]
        if enabled:
            r.put("OK", "D16", "%s が有効" % PLUGIN_ID)
        else:
            r.put("NG", "D16", "%s が有効でない" % PLUGIN_ID,
                  ["claude plugin install %s --scope user を実行する" % PLUGIN_ID])

    print("注意: このセッションにスキルが読み込まれたかは doctor では分からない．"
          "導入・有効化の後に未実行なら /reload-plugins を実行する")
    print("結果: OK %d件 / NG %d件" % (r.ok, r.ng))
    return 0 if r.ng == 0 else 1


def main():
    parser = argparse.ArgumentParser(description="ai-loop の導入状態を診断する")
    parser.add_argument("--mode", choices=("normal", "local"))
    parser.add_argument("--verify-timeout", type=int, default=600)
    parser.add_argument("--skip-verify", action="store_true")
    args = parser.parse_args()
    # origin に接続できないとき，git が認証を求めて止まらないようにする
    os.environ["GIT_TERMINAL_PROMPT"] = "0"
    try:
        code, out = run(["git", "rev-parse", "--show-toplevel"])
        if code != 0:
            print("git のリポジトリの中で実行する")
            return 2
        return diagnose(out.strip(), args)
    except Exception as e:  # doctor 自身の不具合
        print("doctor の内部エラー: %s" % type(e).__name__)
        return 2


if __name__ == "__main__":
    sys.exit(main())
