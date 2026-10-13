# 導入から1件目の Issue まで

ai-loop を使う側のリポジトリを整え，1件目の Issue を PR のマージと後始末まで通す手順．プラグインの導入（`/plugin install`）は README の「導入」の節で済んでいるものとする．

この文書は，置くファイルを `.claude/` の下にまとめ，設定を `.claude/settings.json` に書いてコミットする通常の導入を主に書く．リポジトリにファイルを残さない導入は，末尾の「ローカル専用で導入する場合」を参照．

## 1. 置くファイルと init スクリプト

| ファイル | 必須か | 内容 | init が作るか |
|---|---|---|---|
| `.claude/ai-loop.json` | 必須 | 設定．項目は [config.md](config.md) を参照 | 作る |
| `.claude/ai-loop/verify.sh` | 必須 | 検証コマンド（2 節） | 作る |
| `.claude/settings.json` | 勧める | 権限の deny・ask と `attribution`（3 節） | 作る |
| `.claude/ai-loop/ERRORS.md` など | 必須 | records の置き場所（4 節） | 作る |
| `CLAUDE.md` | 任意 | 司令塔と実装役が従う手順・読む文書（5 節） | 作らない |
| CI と review のワークフロー | 任意 | 6 節 | 作らない |

これらのファイルのうち init が作るものは，init スクリプト（`bin/ai_loop_init.py`）が作り，人が内容を承認する（`--dry-run` の出力を確かめる）．通常の導入では，その後に既定ブランチに入れる．`.claude/ai-loop.json`・検証コマンド・settings は deny の対象にするので，作った後は Claude Code に編集させない．

init は，使う側のリポジトリのルートで実行する．プラグインのパスは `claude plugin list --json` の `installPath` で分かる．

```text
python3 <プラグインのパス>/bin/ai_loop_init.py --mode {normal,local}
    (--test-command "<コマンド>" | --no-tests)
    [--default-branch <名前>] [--show-titles]
    [--deny-secret <パス> ...] [--dry-run]
```

- `--mode`：`normal` は settings を `.claude/settings.json` に書く（コミットする）．`local` は `.claude/settings.local.json` に書き，`.git/info/exclude` に `/.claude/` を足す（末尾の「ローカル専用で導入する場合」）
- `--test-command`・`--no-tests`：検証コマンドの中身（2 節）
- `--default-branch`：GitHub の既定ブランチと違うブランチに PR を向ける場合や，コミットが0件で既定ブランチを取得できない場合に指定する
- `--show-titles`：`report.show_titles` を true にする
- `--deny-secret`：秘密のファイル（`.env` など）を deny に足す（3 節）
- `--dry-run`：何も書かず，作るファイルの全文を出す

手順は次のとおり．

1. `--dry-run` を付けて実行し，出力（作るファイルの全文）を人が確かめて承認する．
2. 同じ引数で `--dry-run` を外して実行する．
3. `python3 <プラグインのパス>/bin/ai_loop_doctor.py` で診断する（7 節の手順2）．

init は，前提（リポジトリのルートで実行している・`gh repo view` が成功する・origin の URL の末尾が `<repo>` または `<repo>.git` と一致する・既定ブランチが決まる・`local` のとき `.claude/` の下に追跡済みのファイルがない）の検査が NG なら，何も書かずに終了コード 2 で終わる．既存のファイルは上書きせず SKIPPED と出す．既存の settings では，足りないもの（`attribution` と deny の各行）を一覧で出すので，人が足す．コミット・push・PR の作成はしない．

init が作る `.claude/ai-loop.json` は次の形である（例の値は `example-owner/example-repo` と `main`）．`repo` と `default_branch` は `gh repo view` から取る．

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

`.claude/ai-loop.json` を置くと，このプラグインのフックが，1回の応答で2つ以上のツール呼び出しを止める．無効にするには `"one_tool_guard": false` を足す（[config.md](config.md)）．確認した版は Claude Code 2.1.296 で，`claude -p` と対話セッションの両方で確かめている．

## 2. 検証コマンド

`verify.command` は，実装役が push の前に，post-merge-cleanup がマージの後に実行する．合否の最終根拠はこのコマンドと CI の終了コードである．スキルの記述から，検証コマンドは次を満たす必要がある．

- 成功したときは終了コード 0 で終わり，出力に `verify.pass_marker` を含める
- 失敗したときは 0 以外で終わり，出力に `verify.fail_marker` を含める
- 結果の要約の行（テストの件数や失敗の件数など）を，`verify.summary_markers` のどれかを含む形で出力する．diagnose-failure と post-merge-cleanup は，この目印で要約の行を取り出す
- 追跡済みのファイルを変えない．diagnose-failure は手元で検証コマンドを実行し，pre-push-check は直前の結果を使い回すことがあるため
- カレントディレクトリ（または `git rev-parse --show-toplevel`）のリポジトリを検査する．スクリプト自身の置き場所（`$0` など）を基準にしない．司令塔は CI のない PR を worktree で検証するため

init は `--test-command` のとき，次の検証コマンドを作る（`<テストのコマンド>` に引数の値が入る）．

```bash
#!/usr/bin/env bash
# ai-loop の検証コマンド（ai_loop_init.py が生成）
# カレントディレクトリのリポジトリを検査する（$0 を基準にしない．commander の worktree での検証のため）
cd "$(git rev-parse --show-toplevel)" || { echo "verify: not a git repository, 1 failed"; echo "VERIFY FAILED"; exit 1; }
if {
  <テストのコマンド>
}; then
  echo "verify: test command exit 0, 0 failed"
  echo "VERIFY PASSED"; exit 0
else
  rc=$?
  echo "verify: test command exit $rc, 1 failed"
  echo "VERIFY FAILED"; exit 1
fi
```

テストのないリポジトリでは `--no-tests` を使う．init は，追跡済みの `*.py`・`*.sh`・`*.json` の構文だけを検査する検証コマンドを作り，完了時に「1件目の案としてテストの追加を勧める」と出す．検証コマンドは `verify: no tests; syntax checks only` の行を必ず出すので，テストがないことが司令塔の報告と post-merge-cleanup の要約に残る．何も検査しない検証コマンド（常に合格）は作らない．

`verify.deny` を true にした場合，検証コマンドとゲート値の変更は人が行う．init は検証コマンドを 3 節の deny に入れる．

## 3. settings の deny・ask・attribution

init が作る settings は次の形である（`main` は既定ブランチに置き換わる）．`--mode local` では `.claude/settings.local.json` に書き，deny の `.claude/settings.json` の2行は `.claude/settings.local.json` になる．

```json
{
  "attribution": {"commit": "", "pr": ""},
  "permissions": {
    "deny": [
      "Edit(.claude/ai-loop.json)",
      "Write(.claude/ai-loop.json)",
      "Edit(.claude/ai-loop/verify.sh)",
      "Write(.claude/ai-loop/verify.sh)",
      "Edit(.claude/settings.json)",
      "Write(.claude/settings.json)",
      "Bash(git push origin main*)",
      "Bash(git push -f*)",
      "Bash(git push --force*)",
      "Bash(gh pr merge*)",
      "Bash(gh issue close*)"
    ],
    "ask": []
  }
}
```

`attribution` と `permissions` の書式は Claude Code の仕様である．詳しくは Claude Code の設定の文書を見る．

- `attribution`：空にすると，コミットと PR に帰属行が付かない．実装役はコミットのトレーラや PR 本文の帰属フッタを付けない
- `deny`：ai-loop で人が行う操作を入れる．マージ，Issue のクローズ，既定ブランチへの push，force push，検証コマンドと設定ファイルの編集である．deny の対象のファイルは，司令塔も実装役も編集しない．変えるときは commander の 4 節の方式（人が GitHub の Web で編集する）で進める
- 秘密のファイル（`.env` など）：init に `--deny-secret .env` を付けると，`Read(./.env)`・`Edit(./.env)` を deny に入れる．Read の deny は Bash のコマンド（`cat .env` など）までは防げないので，指示の決まり（CLAUDE.md など）にも「読まない・開かない・変えない（コマンドも含む）」と書く
- `ask`：変更のたびに人が承認したいファイルを入れる．init は空で作る．進め方は commander の 4 節に従う

settings が既にある場合，init は上書きせず，足りないもの（`attribution` と deny の各行）を一覧で出す．人がその一覧を見て足す．

## 4. records の初期状態

`records` の4つの置き場所は，init が空で作る（`.claude/ai-loop/ERRORS.md`・`.claude/ai-loop/errors_inventory.md`・`.claude/ai-loop/decisions/.keep`・`.claude/ai-loop/trials/.keep`）．ディレクトリは，git が空のディレクトリを記録しないため `.keep` を置く．

- `errors`（失敗記録）：司令塔が Issue を作るときと，diagnose-failure が関連する記録を探すときに grep で読む．空でよい
- `errors_inventory`（失敗記録の棚卸し）：diagnose-failure が読む．空でよい
- `decisions`（ADR）・`trials`（試走の記録）：今は使うスキルがない（予約）

diagnose-failure は `.claude/ai-loop.json` に `records` がないと止まる．`records` は省かない．

## 5. CLAUDE.md

設定として必須なのは `.claude/ai-loop.json` だけで，CLAUDE.md は必須ではない．置いた場合，司令塔と実装役は次のように扱う．

- 司令塔は，案を Issue に分けるとき，CLAUDE.md が挙げる文書のうち案に関係するものだけを読む
- CLAUDE.md が実装の前に必要な手順（測定スクリプトや事前登録のコミットなど）を定めていれば，司令塔はその手順を Issue に含める．実装役は，その手順が済んだと依頼文で示されていない変更をしない
- CLAUDE.md が決まった局面でだけ使うデータを定めていれば，司令塔はその扱いを依頼文に書く．実装役は，その局面の外でそのデータを開かない

## 6. CI と review

CI と review のワークフローはこのプラグインに含まれない．

- CI：司令塔は PR の head のコミットの check-runs がすべて success であることを確かめる．check-runs が0件（CI がない）の場合は「CI：該当なし」とし，検証コマンドの結果を根拠にする
- review：PR に自動の review（bot のコメント）がある場合，司令塔はそのコメントを読み，指摘をブロッカー・軽微・提案に分けて採否を決める．review がない場合は，この確認を省く
- check-run の名前は `verify`・`review` にそろえることを勧める．diagnose-failure が対象にする名前と合わせるためである

bin の `check_review_comment.sh`・`select_review_comment.sh` は，claude-code-action の review のコメントを特定・判定する補助である．

## 7. 1件目の Issue を通す

1. 1〜4 節の手順で init を実行してファイルを作る（`--dry-run` の出力を確かめてから実行する）．通常の導入では，作ったファイルをブランチでコミットして PR を作り，マージして既定ブランチに入れる．ローカル専用の導入では，コミットしない．
2. リポジトリのルートで `python3 <プラグインのパス>/bin/ai_loop_doctor.py` を実行し，全項目 OK・終了コード 0 を確かめる．プラグインのパスは `claude plugin list --json` の `installPath` で分かる．doctor は設定・gh の認証・リモート・records・settings・除外を確かめ，検証コマンドも実行する（終了コード 0・`pass_marker`・要約の行）．NG の項目には直し方が出る．ローカル専用で導入した場合は，`--mode local` を付けると除外の確認を必ず行う．
3. 使う側のリポジトリで `claude --model opus` を起動し，`/ai-loop:commander` と入力して，案を伝える．
4. 司令塔が Issue の一覧と本文の案を示す．承認すると，司令塔が Issue を作る．
5. 司令塔が実装役を起動する．実装役はブランチ作成・実装・検証・pre-push-check・push・PR 作成までを行う．
6. 司令塔が差分・本文・CI・review を確かめ，マージを依頼する．
7. GitHub で PR をマージする．
8. `/ai-loop:post-merge-cleanup <PR番号>` で後始末をする．Issue は PR 本文の `Closes #<番号>` で自動でクローズされる．反映が遅れても手動でクローズしない．ただし，PR を GitHub の既定ブランチ以外へマージした場合は，閉じるキーワードで Issue は自動でクローズされない．post-merge-cleanup がそのことを報告するので，GitHub の Web でクローズする．

## ローカル専用で導入する場合

ai-loop の設定・検証コマンド・記録をコミットしない導入では，init に `--mode local` を付ける．通常の導入との違いは次のとおり（README の「ローカル専用で導入する」の節も参照）．

- 置き場所：init は上と同じく `.claude/` の下にファイルを作り，`.git/info/exclude` に `/.claude/` の1行を足して除外する（同じ行があれば足さない）
- settings：init は 3 節の内容を `.claude/settings.local.json` に書く．deny の `.claude/settings.json` の2行は `.claude/settings.local.json` になる
- 前提：`.claude/` の下に追跡済みのファイルがあると除外が効かないので，init は何も書かずに終了コード 2 で止まる
- 既定ブランチへの反映：しない．doctor の D15 は対象外になる
- 除外の確認：`python3 <プラグインのパス>/bin/ai_loop_doctor.py --mode local` の D14 で確かめる（`.git/info/exclude` の行・`git check-ignore -v .claude/ai-loop.json` が `.git/info/exclude` を示すこと・`.claude/` の下に追跡済みのファイルがないこと）
