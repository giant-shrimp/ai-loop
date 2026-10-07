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

シェルからは `claude plugin marketplace add giant-shrimp/ai-loop` と `claude plugin install ai-loop@ai-loop` でも同じことができます．非公開のリポジトリなので，手元の git の認証（`gh auth login` など）で clone できる必要があります．

## 設定

使う側のリポジトリに `.claude/ai-loop.json` を置きます．リポジトリ名・既定ブランチ・検証コマンド・走査器などを書きます．項目と例は [docs/config.md](docs/config.md) にあります．ファイルや必要な項目がない場合，スキルは推測で補わずに止まります．

コミット・PR に帰属行が付かないように，使う側のリポジトリの `.claude/settings.json` で Claude Code の `attribution` 設定を空にしておくことを勧めます．

## 使い方

1. 使う側のリポジトリで `claude --model opus` を起動し，`/ai-loop:commander` と入力します．
2. 案を伝えます．司令塔が Issue の一覧と本文の案を示すので，承認します．
3. 司令塔が実装役を起動し，PR ができるまで進めます．完了後，司令塔が差分・本文・CI・review を確かめて報告します．
4. ユーザが GitHub でマージします．
5. `/ai-loop:post-merge-cleanup <PR番号>` で後始末をします．

各スキルは単独でも使えます（例：`/ai-loop:pre-push-check`）．

## 更新

```text
claude plugin marketplace update ai-loop
claude plugin update ai-loop@ai-loop
```

`--scope` を省くと，インストールされているスコープの一方だけが更新されます．user スコープと project スコープの両方に入れている場合は，project スコープも別に更新します．

```text
claude plugin update ai-loop@ai-loop --scope project
```

`claude plugin list` で，スコープごとの版を確かめられます．

更新後，開いているセッションでは `/reload-plugins` を実行すると反映されます．版は `.claude-plugin/plugin.json` の `version` で管理しています．
