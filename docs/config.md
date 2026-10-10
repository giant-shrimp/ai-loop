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
| `records` | オブジェクト | 記録の置き場所．`errors`（失敗記録）・`errors_inventory`（その棚卸し）・`decisions`（ADR）・`trials`（試走の記録）．指すファイルとディレクトリは，導入時に空で作っておく（[setup.md](setup.md) の 4 節） | `errors`：diagnose-failure・commander・implementer．`errors_inventory`：diagnose-failure．`decisions`・`trials`：なし（今は使うスキルがない．予約） |

注：pre-push-check は，`added_lines_only` が false の走査器に対象のパスを付けず，`command` の末尾に `--diff-base origin/<default_branch>` を付けて実行する．この形に対応していない走査器は，`added_lines_only` を true にする．

## 例

```json
{
  "repo": "example-owner/example-repo",
  "default_branch": "main",
  "python": ".venv/bin/python",
  "verify": {
    "command": "./scripts/verify.sh",
    "pass_marker": "VERIFY PASSED",
    "fail_marker": "VERIFY FAILED",
    "summary_markers": [" passed", " failed", "VERIFY "],
    "deny": true
  },
  "scanners": [
    {"name": "走査器", "command": "check_no_personal_info.py", "added_lines_only": false}
  ],
  "extra_checks": [],
  "records": {
    "errors": "ERRORS.md",
    "errors_inventory": "docs/errors_md_inventory.md",
    "decisions": "docs/decisions/",
    "trials": "docs/ai_loop_state/"
  }
}
```

`check_no_personal_info.py` はこのプラグインの `bin/` にあり，Bash の PATH に載る．`--diff-base` の形に対応している．
