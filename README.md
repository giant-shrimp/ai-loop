# ai-loop

Claude Code で「案 → Issue → 実装 → PR → 確認」を回す AI ループのプラグインです．このリポジトリはプラグイン本体と，それを配布するマーケットプレイスを兼ねています．

## Claude Code 向けセットアップ手順

ユーザから「この README を見てセットアップを完了して」と頼まれた Claude Code は，この節を上から順に実行する．各手順の「完了条件」を満たさなければ先へ進まず，止めてユーザに報告する．ここに書いていない値は推測で補わない．ユーザに聞くのは S3 の質問と，S4・S5 の確認だけにする．コマンドは使う側のリポジトリのルートで，1つずつ実行する．

**S0. 原文を読む**．この README を要約で読んだ場合は，`curl -fsSL https://raw.githubusercontent.com/giant-shrimp/ai-loop/main/README.md` で原文を取得してから，この節に従う（認証は要らない）．gh は S1 で認証を確かめた後でだけ使う．

**S1. 前提を確かめる**．`git rev-parse --show-toplevel`・`gh auth status`・`python3 --version`・`claude --version` を1つずつ実行する．
- 完了条件：すべて終了コード 0．`git rev-parse --show-toplevel` の出力がカレントディレクトリと同じ
- gh が未認証なら，ユーザに `! gh auth login` の実行を依頼する（ユーザ操作）

**S2. プラグインを入れる（user scope）**．`claude plugin list --json` を実行し，`"id": "ai-loop@ai-loop"` かつ `"scope": "user"` の行を探す．
- その行がない場合：`claude plugin marketplace add giant-shrimp/ai-loop`（`claude plugin marketplace list` に `ai-loop` があれば省く）と `claude plugin install ai-loop@ai-loop --scope user` を実行する
- その行がある場合：`claude plugin marketplace update ai-loop` と `claude plugin update ai-loop@ai-loop --scope user` を実行する
- 実行後にもう一度 `claude plugin list --json` を実行し，`"scope": "user"` の行の `installPath` を控える（以下 `<P>`）．行が複数あっても，`"scope": "user"` の行だけを使う
- 完了条件：`test -f <P>/bin/ai_loop_init.py` と `test -f <P>/bin/ai_loop_doctor.py` がどちらも終了コード 0
- このセッションではまだプラグインのスキルが使えない（S7 で読み込む）．S7 まではスキルを使わず，`<P>/bin` のスクリプトを `python3` で直接実行する

**S3. ユーザに確認する**（1回の質問にまとめる）．
- Q1 導入方式：通常（`--mode normal`．設定をコミットする）／ローカル専用（`--mode local`．`.claude/` を手元だけで除外し，設定をコミットしない）
- Q2 検証コマンド：リポジトリの設定ファイル（`package.json` の scripts・`pyproject.toml`・`Makefile` など）から推定したテストのコマンドの候補を示し，選んでもらう（`--test-command "<コマンド>"`）．テストがなければ「形の検査のみ」（`--no-tests`）を示す
- Q3 秘密のファイル：検出した候補（`.env` など）を deny に入れるか（入れるものごとに `--deny-secret <パス>`）
- 完了条件：Q1〜Q3 の答えがそろった

**S4. 雛形を確かめる**．`python3 <P>/bin/ai_loop_init.py --mode <Q1> <Q2 の引数> <Q3 の引数> --dry-run` を実行する．
- 出力の `WOULD CREATE <パス>` には，作るファイルの全文が続く．`SKIPPED <パス>（既存のため変更しない）` は既存のファイルで，変更しない．既存の settings に足りないものは `  足りない: ...` の行で出る
- 終了コード 2（`NG: ...` の行と「前提の検査が NG のため，何も書いていない」）なら，NG の行の括弧内の直し方に従って直してから，もう一度実行する．「既定ブランチを GitHub から取得できない」（コミットが0件のリポジトリ）なら，ユーザに既定ブランチ名を聞き，`--default-branch <名前>` を足す
- 完了条件：終了コード 0 で，出力をユーザに示し，ユーザが内容を承認した（ユーザに確認する箇所）

**S5. 雛形を作る**．S4 と同じ引数で `--dry-run` を外して実行する．
- 出力は，作ったファイルが `CREATED <パス>`，既存のファイルが `SKIPPED <パス>（既存のため変更しない）`，local の除外が `APPENDED .git/info/exclude に /.claude/` になる
- 完了条件：終了コード 0．`SKIPPED` や `  足りない: ...` の行があれば，その一覧をユーザに示し，扱いを確認する（ユーザに確認する箇所）．足りないものは人が settings に足す．Claude Code は settings を編集しない

**S6. 診断する**．通常導入では `python3 <P>/bin/ai_loop_doctor.py`，ローカル専用では `python3 <P>/bin/ai_loop_doctor.py --mode local` を実行する．
- 出力は項目ごとの `[OK]`・`[NG]`・`[SKIP]` と，NG に付く `直し方: ...` の行，末尾の `結果: OK n件 / NG m件` である
- NG があれば，`直し方:` に従う．直し方がユーザ操作（push・マージ・settings の編集など）なら，ユーザに依頼する．`.claude/ai-loop.json`・検証コマンド・settings を Edit・Write で直さない（deny の対象）
- 通常導入では，作ったファイルが既定ブランチに入るまで D15 が NG になる．ブランチ `ai-loop-setup` を作り，init が作ったファイルを1つずつ `git add` してコミットし（帰属行を付けない），push して PR を作り，ユーザにマージを依頼する．マージ後に `git fetch origin` を実行し，`git switch <既定ブランチ>` と `git pull` で手元を既定ブランチに戻してから doctor をもう一度実行する
- コミットが0件のリポジトリでは D07 が NG になる．手元のブランチ名（`git branch --show-current`）が既定ブランチと違う場合（`init.defaultBranch` が未設定の環境では `master` になる）は，先に `git checkout -b <既定ブランチ>` でそろえる（コミットが0件のブランチは，古い git では `git branch -m` で改名できない）．そのうえで，ユーザに最初のコミットと push を依頼する（例：`! git commit --allow-empty -m "initial commit"` と `! git push -u origin <既定ブランチ>`．通常導入では，最初のコミットに init が作ったファイルを入れてよい）
- 完了条件：終了コード 0（`NG 0件`）

**S7. スキルを読み込む**．ユーザに `/reload-plugins` の実行を依頼する（ユーザ操作）．
- 完了条件：ユーザが実行したと答えた後，S6 と同じ doctor のコマンドが終了コード 0（`NG 0件`）

完了したら，ユーザに次を伝える．
- 使い方：使う側のリポジトリで `claude --model opus` を起動し，`/ai-loop:commander` と入力して案を伝える
- `--no-tests` で導入した場合：検証は形の検査だけなので，1件目の案として「テストの追加」を勧める

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
| スキル | `post-merge-cleanup` | マージ後の後始末（pull・マージの確認・検証・worktree とブランチの削除） |
| スキル | `report-self-check` | 報告を送る前の走査器による自己点検 |
| スキル | `replace-doc-range` | 文書の行範囲を確定した本文に置き換える |
| スキル | `diagnose-failure` | CI・review・試走の失敗の診断（読み取り専用） |
| エージェント | `implementer` | 実装役（司令塔から依頼されたときだけ動く） |
| エージェント | `investigator` | 材料を列挙する調査役（読み取り専用） |
| エージェント | `auditor` | 報告や変更を記載規則に照らす監査役（読み取り専用） |
| bin | `check_no_personal_info.py` | 個人情報・絶対パス・OS のユーザ名の走査器（ユーザ名にヒットした行は内容を出さず `[os-user]` と出す） |
| bin | `ai_loop_init.py` | 使う側のリポジトリに設定・検証コマンド・settings・records の雛形を作る（既存のファイルは上書きしない．`--dry-run` で中身を示す） |
| bin | `ai_loop_doctor.py` | 使う側のリポジトリの導入状態の診断（項目ごとに OK／NG と直し方を出し，終了コードで合否を示す） |
| bin | `check_review_comment.sh`・`select_review_comment.sh` | review のコメントの特定と判定の補助 |
| フック | `hooks/hooks.json`・`bin/one_tool_guard.py` | 1回の応答で2つ以上のツール呼び出しを止める |

## 前提

- Claude Code
- git と，認証済みの GitHub CLI（`gh`）．Issue・PR の作成と確認は `gh api` で行います．
- Python 3（走査器の実行に使います）

## 導入

使う側のリポジトリで Claude Code を起動し，「https://github.com/giant-shrimp/ai-loop の README を見てセットアップを完了して」と頼むと，Claude Code が冒頭の「Claude Code 向けセットアップ手順」に従って進めます．

手で導入する場合は，シェルで次を実行してプラグインを入れます（scope は user にそろえます）．

```text
claude plugin marketplace add giant-shrimp/ai-loop
claude plugin install ai-loop@ai-loop --scope user
```

続けて，使う側のリポジトリのルートで init（`bin/ai_loop_init.py`）を `--dry-run` 付きで実行して中身を確かめ，`--dry-run` を外して実行してから，doctor（`bin/ai_loop_doctor.py`）で診断します．`bin/` の場所は `claude plugin list --json` の `"scope": "user"` の行の `installPath` です．引数と手順は [docs/setup.md](docs/setup.md) の 1 節にあります．開いているセッションでは，`/reload-plugins` を実行するとスキルが読み込まれます．

## 設定

init は使う側のリポジトリに次を作ります．既存のファイルは上書きしません．

- `.claude/ai-loop.json`：設定（下の例）．項目の説明と，init が作らない任意の項目（`one_tool_guard` など）は [docs/config.md](docs/config.md) にあります．ファイルや必要な項目がない場合，スキルは推測で補わずに止まります
- `.claude/ai-loop/verify.sh`：検証コマンド．`--test-command` ならそのコマンドを，`--no-tests` なら構文の検査だけを実行します
- `.claude/settings.json`（ローカル専用では `.claude/settings.local.json`）：コミット・PR に帰属行が付かないように `attribution` を空にする設定と，権限の deny（マージ・Issue のクローズ・既定ブランチへの push・設定と検証コマンドの編集など）
- records の置き場所（`.claude/ai-loop/ERRORS.md` など）

init が作る `.claude/ai-loop.json` の例（`repo` と `default_branch` は `gh repo view` から取ります）：

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

導入から1件目の Issue を通すまでの手順は [docs/setup.md](docs/setup.md) にあります．

司令塔は既定では，Issue のタイトルを報告に書かず，作業用ディレクトリのファイルで示します．スマートフォンからの遠隔操作などでファイルを開けない場合は，init に `--show-titles` を付ける（作った後なら `.claude/ai-loop.json` の `report.show_titles` を true にする）と，タイトルも報告に書きます．

## ツール呼び出しを1つに制限するフック

このプラグインは，1回の応答で2つ以上のツール呼び出しを出すことを止めるフック（`hooks/hooks.json`・`bin/one_tool_guard.py`）を含みます．PreToolUse で呼び出しを数え，同じ応答の2つ目以降を実行前に拒否します．拒否の理由はモデルに返り，次の応答で1つずつ出し直させます．数は，ツールの一括実行の後（PostToolBatch）とユーザの入力（UserPromptSubmit）で0に戻します．メインのセッションとサブエージェントは別に数えます．

フックが働くのは，使う側のリポジトリに `.claude/ai-loop.json` があるときだけです．無効にするには，`.claude/ai-loop.json` に `"one_tool_guard": false` を足します．フック自体の不具合で失敗した場合は，拒否せずに通します．

確認した版は Claude Code 2.1.296 です．`claude -p` と対話セッションの両方で，メインのセッションとサブエージェントの両方について確かめています（拒否を確かめたツールは Read と Bash）．

## ローカル専用で導入する（リポジトリにファイルを残さない）

研究用のリポジトリなど，ai-loop の設定・検証コマンド・記録を一切コミットしたくない場合の導入方法です．ai-loop 関係のファイルをすべて `.claude/` の下に置き，git の手元だけの除外リスト（`.git/info/exclude`）で除外します．ループで作ったコードや文書は，通常どおり PR で push されます．

init に `--mode local` を付けて実行します．init は次を行います．

- ファイルを `.claude/` の下に作る．settings は，コミットされる前提の `.claude/settings.json` ではなく `.claude/settings.local.json` に書く
- `.git/info/exclude` に `/.claude/` の1行を足す（同じ行があれば足さない）．このファイル自体は push されない．`.gitignore` に書くとその行がコミットされるので，使わない
- `.claude/` の下に追跡済みのファイルがある場合は，除外が効かないので，何も書かずに終了コード 2 で止まる

確かめるときは `python3 <installPath>/bin/ai_loop_doctor.py --mode local` を実行します．D14 が除外を確かめます（`.git/info/exclude` の行・`git check-ignore`・追跡済みのファイルがないこと）．

除外したファイルは `git add` しても追加されない（`-f` を付けない限り）ので，実装役が誤ってコミットすることはありません．なお，Issue と PR は git ではなく GitHub に残ります．

## 使い方

1. 使う側のリポジトリで `claude --model opus` を起動し，`/ai-loop:commander` と入力します．
2. 案を伝えます．司令塔が Issue の一覧と本文の案を示すので，承認します．
3. 司令塔が実装役を起動し，PR ができるまで進めます．完了後，司令塔が差分・本文・CI・review を確かめて報告します．
4. ユーザが GitHub でマージします．
5. `/ai-loop:post-merge-cleanup <PR番号>` で後始末をします．

各スキルは単独でも使えます（例：`/ai-loop:pre-push-check`）．

司令塔はタスクごとに作業用ディレクトリ（`mktemp -d` で作る）を1つ作り，確定した本文（変更後の全文・コミット件名・PR 本文など）をその下に置きます．実装役は依頼文に書かれたフルパスでそれを使います．作業用ディレクトリは，タスクの最後に司令塔が消します．途中で PC を再起動すると作業用ディレクトリが消え，実装役は確定版が見つからずに止まります．再開するときは，司令塔に新しい作業用ディレクトリで確定版を前回と同じ内容で作り直させ，sha256 が前回の値（計算方法も同じもの）と一致することを確かめてから続けさせます．

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
