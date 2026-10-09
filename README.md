# ai-loop

Claude Code で「案 → Issue → 実装 → PR → 確認」を回す AI ループのプラグインです．このリポジトリはプラグイン本体と，それを配布するマーケットプレイスを兼ねています．

## 何ができるか

- **司令塔**（`claude --model opus` の対話セッション）が，ユーザの案を Issue に分解し，承認を得てから作成します．
- **実装役**（サブエージェント．sonnet）が，Issue 1件ごとにブランチ作成・実装・検証・push・PR 作成までを行います．
- 司令塔が CI と review の結果を読み，採否を決めてユーザにマージを依頼します．マージ後の後始末もスキルで行います．
- 報告の前には走査器で個人情報などの漏洩を機械的に検査します．コミット・PR に帰属行（Co-Authored-By など）は付けません．

マージ，Issue のクローズ，保護されたファイルの編集は常に人が行います．合否の最終根拠は，AI の承認ではなく検証コマンドと CI の終了コードです．

## 中身

| 種類 | 名前 | 役割 |
|---|---|---|
| スキル | `commander` | 司令塔の手順（`/ai-loop:commander` で呼んだときだけ使う） |
| スキル | `pre-push-check` | push 前の検証・差分の走査・追加の検査 |
| スキル | `publish-github` | 確定した本文で Issue・PR を作り，本文の一致を確かめる |
| スキル | `post-merge-cleanup` | マージ後の後始末（pull・マージの確認・検証・ブランチの削除） |
| スキル | `report-self-check` | 報告を送る前の走査器による自己点検 |
| スキル | `replace-doc-range` | 文書の行範囲を確定した本文に置き換える |
| スキル | `diagnose-failure` | CI・review・試走の失敗の診断（読み取り専用） |
| エージェント | `implementer` | 実装役（司令塔から依頼されたときだけ動く） |
| エージェント | `investigator` | 材料を列挙する調査役（読み取り専用） |
| エージェント | `auditor` | 報告や変更を記載規則に照らす監査役（読み取り専用） |
| bin | `check_no_personal_info.py` | 個人情報・絶対パスの走査器 |
| bin | `check_review_comment.sh`・`select_review_comment.sh` | review のコメントの特定と判定の補助 |

## 前提

- Claude Code
- git と，認証済みの GitHub CLI（`gh`）．Issue・PR の作成と確認は `gh api` で行います．
- Python 3（走査器の実行に使います）

## 導入

Claude Code のセッションで次を実行します．

```text
/plugin marketplace add giant-shrimp/ai-loop
/plugin install ai-loop@ai-loop
```

シェルからは `claude plugin marketplace add giant-shrimp/ai-loop` と `claude plugin install ai-loop@ai-loop` でも同じことができます．

## 設定

使う側のリポジトリに `.claude/ai-loop.json` を置きます．リポジトリ名・既定ブランチ・検証コマンド・走査器などを書きます．項目と例は [docs/config.md](docs/config.md) にあります．ファイルや必要な項目がない場合，スキルは推測で補わずに止まります．

導入から1件目の Issue を通すまでの手順（検証コマンド・settings・records の用意を含む）は [docs/setup.md](docs/setup.md) にあります．

コミット・PR に帰属行が付かないように，使う側のリポジトリの `.claude/settings.json`（ローカル専用で導入する場合は `.claude/settings.local.json`）で Claude Code の `attribution` 設定を空にしておくことを勧めます．

司令塔は既定では，Issue のタイトルを報告に書かず，/tmp のファイルで示します．スマートフォンからの遠隔操作などでファイルを開けない場合は，`.claude/ai-loop.json` に `"report": {"show_titles": true}` を足すと，タイトルも報告に書きます．

## ローカル専用で導入する（リポジトリにファイルを残さない）

研究用のリポジトリなど，ai-loop の設定・検証コマンド・記録を一切コミットしたくない場合の導入方法です．ai-loop 関係のファイルをすべて `.claude/` の下に置き，git の手元だけの除外リストで除外します．ループで作ったコードや文書は，通常どおり PR で push されます．

**1. 除外する**．手元だけの除外リスト `.git/info/exclude` に次の1行を足します．このファイル自体は push されません．`.gitignore` に書くと，その行がコミットされるので使いません．

```text
/.claude/
```

**2. 3つのファイルを置く**．

| ファイル | 中身 |
|---|---|
| `.claude/ai-loop.json` | 設定．`verify.command` と `records` は `.claude/ai-loop/` の下を指す（下の例） |
| `.claude/ai-loop/verify.sh` | 検証コマンド．リポジトリのテストを実行し，結果に応じて `VERIFY PASSED` か `VERIFY FAILED` を出す |
| `.claude/settings.local.json` | `attribution` を空にする設定と，権限の deny（検証コマンドと設定ファイルの編集，既定ブランチへの push，マージなど） |

権限と `attribution` は，コミットされる前提の `.claude/settings.json` ではなく `.claude/settings.local.json` に書きます．

**3. 確かめる**．`git status --porcelain --ignored` に `!! .claude/` が出て，`git check-ignore -v .claude/ai-loop.json` が `.git/info/exclude` の行を示せば，除外できています．

除外したファイルは `git add` しても追加されない（`-f` を付けない限り）ので，実装役が誤ってコミットすることはありません．なお，Issue と PR は git ではなく GitHub に残ります．

`.claude/ai-loop.json` の例：

```json
{
  "repo": "example-owner/example-repo",
  "default_branch": "main",
  "python": "python3",
  "verify": {
    "command": "bash .claude/ai-loop/verify.sh",
    "pass_marker": "VERIFY PASSED",
    "fail_marker": "VERIFY FAILED",
    "summary_markers": [" passed", " failed", "VERIFY "],
    "deny": true
  },
  "scanners": [
    {"name": "個人情報走査", "command": "check_no_personal_info.py", "added_lines_only": false}
  ],
  "extra_checks": [],
  "records": {
    "errors": ".claude/ai-loop/ERRORS.md",
    "errors_inventory": ".claude/ai-loop/errors_inventory.md",
    "decisions": ".claude/ai-loop/decisions/",
    "trials": ".claude/ai-loop/trials/"
  }
}
```

## 使い方

1. 使う側のリポジトリで `claude --model opus` を起動し，`/ai-loop:commander` と入力します．
2. 案を伝えます．司令塔が Issue の一覧と本文の案を示すので，承認します．
3. 司令塔が実装役を起動し，PR ができるまで進めます．完了後，司令塔が差分・本文・CI・review を確かめて報告します．
4. ユーザが GitHub でマージします．
5. `/ai-loop:post-merge-cleanup <PR番号>` で後始末をします．

各スキルは単独でも使えます（例：`/ai-loop:pre-push-check`）．

司令塔は確定した本文（変更後の全文・コミット件名・PR 本文など）を /tmp に置き，実装役はそれを使います．途中で PC を再起動すると /tmp が空になり，実装役は確定版が見つからずに止まります．再開するときは，司令塔に確定版を前回と同じ内容で作り直させ，sha256 が前回の値（計算方法も同じもの）と一致することを確かめてから続けさせます．

## 更新

```text
claude plugin marketplace update ai-loop
claude plugin update ai-loop@ai-loop --scope user
```

`--scope` は必ず明示します．省くと，インストールされているスコープの一方だけが更新され，user スコープが古い版のまま残ることがあります．project スコープにも入れている場合は，導入したリポジトリのセッションで次を実行します．

```text
claude plugin update ai-loop@ai-loop --scope project
```

project スコープの導入はリポジトリごとに別です．導入していないリポジトリで `--scope project` を実行すると，別のリポジトリの導入が更新されることがあります．project スコープの更新は，導入したリポジトリごとに行います．

`claude plugin list` で，スコープごとの版を確かめられます．

更新後，開いているセッションでは `/reload-plugins` を実行すると反映されます．版は `.claude-plugin/plugin.json` の `version` で管理しています．
