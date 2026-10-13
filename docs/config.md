# .claude/ai-loop.json の形式

ai-loop のスキル・エージェントは，使う側のリポジトリの `.claude/ai-loop.json` から，リポジトリごとの値を読む．ファイルがない，または必要な項目がない場合，スキルは止めて報告する（値を推測で補わない）．

## 項目

| 項目 | 型 | 内容 | 使うスキル・エージェント |
|---|---|---|---|
| `repo` | 文字列 | `所有者/リポジトリ名`．gh api のパスに使う | publish-github・post-merge-cleanup・commander・implementer |
| `default_branch` | 文字列 | 既定ブランチ名．PR を向けるブランチ．GitHub の既定ブランチと違ってよい（その場合，閉じるキーワードで Issue は自動で閉じない．post-merge-cleanup がそのことを報告する） | pre-push-check・post-merge-cleanup・commander・implementer |
| `python` | 文字列 | Python の実行ファイル（例 `.venv/bin/python`） | なし（今は使うスキルがない．予約） |
| `verify.command` | 文字列 | 検証コマンド | pre-push-check・post-merge-cleanup・diagnose-failure・commander・implementer |
| `verify.pass_marker` | 文字列 | 成功を示す出力の目印 | pre-push-check・diagnose-failure |
| `verify.fail_marker` | 文字列 | 失敗を示す出力の目印 | diagnose-failure |
| `verify.summary_markers` | 文字列の配列 | 結果の要約として取り出す行の目印 | post-merge-cleanup・diagnose-failure |
| `verify.deny` | 真偽値 | 検証コマンドとゲート値の変更を人が行うか | diagnose-failure |
| `scanners` | 配列 | 走査器．各要素は `name`（報告に書く名前）・`command`（末尾に対象のパスを付けて実行する．例外は下の注を参照）・`added_lines_only`（真偽値．true なら追加した行だけに使う） | report-self-check・replace-doc-range・pre-push-check |
| `extra_checks` | 配列 | push 前に追加で行う検査．各要素は `command` と，任意の `when_changed`（パスの配列．そのどれかを変えたときだけ実行する） | pre-push-check |
| `report.show_titles` | 真偽値 | 任意（ない場合は false）．true なら，司令塔が報告に Issue と PR のタイトル・コミットの件名を書く．承認のためにファイルを開けない環境（スマートフォンからの遠隔操作など）で使う．タイトルに書いてはいけない名前が入りうるリポジトリでは false のままにする | commander |
| `one_tool_guard` | 真偽値 | 任意（ない場合は有効）．false なら，1回の応答で2つ以上のツール呼び出しを止めるフック（`hooks/hooks.json`・`bin/one_tool_guard.py`）を無効にする．フックは `.claude/ai-loop.json` があるときだけ働く．確認した版は Claude Code 2.1.296 で，`claude -p` と対話セッションの両方で確かめている | フック（one_tool_guard.py） |
| `records` | オブジェクト | 記録の置き場所．`errors`（失敗記録）・`errors_inventory`（その棚卸し）・`decisions`（ADR）・`trials`（試走の記録）．指すファイルとディレクトリは，導入時に空で作っておく（[setup.md](setup.md) の 4 節） | `errors`：diagnose-failure・commander・implementer．`errors_inventory`：diagnose-failure．`decisions`・`trials`：なし（今は使うスキルがない．予約） |

注：pre-push-check は，`added_lines_only` が false の走査器に対象のパスを付けず，`command` の末尾に `--diff-base origin/<default_branch>` を付けて実行する．この形に対応していない走査器は，`added_lines_only` を true にする．

## 例

init（`bin/ai_loop_init.py`）が作る `.claude/ai-loop.json` の例（例の値は `example-owner/example-repo` と `main`）．README・[setup.md](setup.md) の例と同じである．

```json
{
  "repo": "example-owner/example-repo",
  "default_branch": "main",
  "python": "python3",
  "verify": {
    "command": "bash .claude/ai-loop/verify.sh",
    "pass_marker": "VERIFY PASSED",
    "fail_marker": "VERIFY FAILED",
    "summary_markers": [
      " failed",
      "VERIFY "
    ],
    "deny": true
  },
  "scanners": [
    {
      "name": "個人情報走査",
      "command": "check_no_personal_info.py",
      "added_lines_only": false
    }
  ],
  "extra_checks": [],
  "report": {
    "show_titles": false
  },
  "records": {
    "errors": ".claude/ai-loop/ERRORS.md",
    "errors_inventory": ".claude/ai-loop/errors_inventory.md",
    "decisions": ".claude/ai-loop/decisions/",
    "trials": ".claude/ai-loop/trials/"
  }
}
```

init が作らない任意の項目（`one_tool_guard`・`extra_checks` の要素など）は，上の表を見て人が足す．`verify.command`・`records`・`python` は，リポジトリに合わせて別の値にしてもよい（例：`"python": ".venv/bin/python"`，`"command": "./scripts/verify.sh"`，`"errors": "ERRORS.md"`）．その場合も，setup.md の 2 節の条件と 4 節の置き場所を満たす．

`check_no_personal_info.py` はこのプラグインの `bin/` にあり，Bash の PATH に載る．`--diff-base` の形に対応している．
