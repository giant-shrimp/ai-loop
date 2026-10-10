#!/usr/bin/env python3
"""1回の応答で2つ以上のツール呼び出しを止めるフック．

PreToolUse で呼び出しを数え，同じ応答の2つ目以降を deny する．
PostToolBatch と UserPromptSubmit で数を0に戻す．
数は session_id と agent_id の組ごとの状態ファイルに持つ．

使う側のリポジトリ（CLAUDE_PROJECT_DIR，なければ入力の cwd）の
.claude/ai-loop.json があり，JSON として読めて，one_tool_guard が false でないときだけ働く．
それ以外は何もせず終了コード 0 で終わる．
例外はすべて捕まえ，拒否せず終了コード 0 で終わる（fail-open）．
"""
import fcntl
import json
import os
import re
import sys

REASON = "1回の応答で出すツール呼び出しは1つだけ。この呼び出しは実行していない。必要なら次の応答で、1つだけ出し直すこと。"


def enabled(data):
    project = os.environ.get("CLAUDE_PROJECT_DIR") or data.get("cwd")
    if not project:
        return False
    path = os.path.join(project, ".claude", "ai-loop.json")
    if not os.path.isfile(path):
        return False
    with open(path, encoding="utf-8") as f:
        config = json.load(f)
    return isinstance(config, dict) and config.get("one_tool_guard") is not False


def state_path(data):
    base = os.environ.get("CLAUDE_PLUGIN_DATA")
    state_dir = os.path.join(base, "one_tool_guard") if base else "/tmp/ai-loop-one-tool-guard"
    os.makedirs(state_dir, exist_ok=True)
    agent = data.get("agent_id") or "main"
    key = "%s_%s" % (data.get("session_id") or "nosession", agent)
    return os.path.join(state_dir, re.sub(r"[^A-Za-z0-9_.-]", "_", key))


def main():
    try:
        data = json.load(sys.stdin)
        if not isinstance(data, dict) or not enabled(data):
            return 0
        event = data.get("hook_event_name", "")
        path = state_path(data)
        deny = False
        with open(path + ".lock", "a") as lk:
            fcntl.flock(lk, fcntl.LOCK_EX)
            try:
                with open(path) as f:
                    count = int(f.read().strip() or "0")
            except (FileNotFoundError, ValueError):
                count = 0
            if event in ("PostToolBatch", "UserPromptSubmit"):
                count = 0
            elif event == "PreToolUse":
                if count >= 1:
                    deny = True
                count += 1
            with open(path, "w") as f:
                f.write(str(count))
        if deny:
            print(json.dumps({"hookSpecificOutput": {
                "hookEventName": "PreToolUse",
                "permissionDecision": "deny",
                "permissionDecisionReason": REASON}}, ensure_ascii=False))
    except Exception:
        return 0
    return 0


if __name__ == "__main__":
    sys.exit(main())
