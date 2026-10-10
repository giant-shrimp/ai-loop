# 導入から1件目の Issue まで

ai-loop を使う側のリポジトリを整え，1件目の Issue を PR のマージと後始末まで通す手順．プラグインの導入（`/plugin install`）は README の「導入」の節で済んでいるものとする．

この文書は，置くファイルを `.claude/` の下にまとめ，設定を `.claude/settings.json` に書いてコミットする通常の導入を主に書く．リポジトリにファイルを残さない導入は，末尾の「ローカル専用で導入する場合」を参照．

## 1. 置くファイル

| ファイル | 必須か | 内容 |
|---|---|---|
| `.claude/ai-loop.json` | 必須 | 設定．項目は [config.md](config.md) を参照 |
| `.claude/ai-loop/verify.sh` | 必須 | 検証コマンド（2 節） |
| `.claude/settings.json` | 勧める | 権限の deny・ask と `attribution`（3 節） |
| `.claude/ai-loop/ERRORS.md` など | 必須 | records の置き場所（4 節） |
| `CLAUDE.md` | 任意 | 司令塔と実装役が従う手順・読む文書（5 節） |
| CI と review のワークフロー | 任意 | 6 節 |

これらのファイルは人が作り，既定ブランチに入れる．`.claude/ai-loop.json`・検証コマンド・settings は deny の対象にするので，Claude Code には編集させない．

`.claude/ai-loop.json` の `verify.command` と `records` は，次のようにこの文書の置き場所を指す．

```json
{
  "verify": {
    "command": "bash .claude/ai-loop/verify.sh",
    "pass_marker": "VERIFY PASSED",
    "fail_marker": "VERIFY FAILED",
    "summary_markers": [" passed", " failed", "VERIFY "],
    "deny": true
  },
  "records": {
    "errors": ".claude/ai-loop/ERRORS.md",
    "errors_inventory": ".claude/ai-loop/errors_inventory.md",
    "decisions": ".claude/ai-loop/decisions/",
    "trials": ".claude/ai-loop/trials/"
  }
}
```

ほかの項目（`repo`・`default_branch`・`scanners` など）は config.md の例に従う．

`.claude/ai-loop.json` を置くと，このプラグインのフックが，1回の応答で2つ以上のツール呼び出しを止める．無効にするには `"one_tool_guard": false` を足す（[config.md](config.md)）．確認した版は Claude Code 2.1.296 の `claude -p` で，対話セッションでは確認していない．

## 2. 検証コマンド

`verify.command` は，実装役が push の前に，post-merge-cleanup がマージの後に実行する．合否の最終根拠はこのコマンドと CI の終了コードである．スキルの記述から，検証コマンドは次を満たす必要がある．

- 成功したときは終了コード 0 で終わり，出力に `verify.pass_marker` を含める
- 失敗したときは 0 以外で終わり，出力に `verify.fail_marker` を含める
- 結果の要約の行（テストの件数や失敗の件数など）を，`verify.summary_markers` のどれかを含む形で出力する．diagnose-failure と post-merge-cleanup は，この目印で要約の行を取り出す
- 追跡済みのファイルを変えない．diagnose-failure は手元で検証コマンドを実行し，pre-push-check は直前の結果を使い回すことがあるため

最小の例（`<テストのコマンド>` はリポジトリのテストに置き換える）：

```bash
#!/usr/bin/env bash
# リポジトリのテストを実行し，結果に応じて目印を出す
if <テストのコマンド>; then
  echo "VERIFY PASSED"; exit 0
else
  echo "VERIFY FAILED"; exit 1
fi
```

テストのコマンドが件数の行（例：`3 passed`・`1 failed`）を出さない場合は，`summary_markers` に合う要約の行を検証コマンドが自分で出す．

`verify.deny` を true にした場合，検証コマンドとゲート値の変更は人が行う．検証コマンドを 3 節の deny に入れる．

## 3. settings の deny・ask・attribution

`.claude/settings.json` の例．`main` は `default_branch` の値に置き換える．

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
- 秘密のファイル（`.env` など）：`Read(./.env)`・`Edit(./.env)` を deny に入れる．Read の deny は Bash のコマンド（`cat .env` など）までは防げないので，指示の決まり（CLAUDE.md など）にも「読まない・開かない・変えない（コマンドも含む）」と書く
- `ask`：変更のたびに人が承認したいファイルを入れる．進め方は commander の 4 節に従う

## 4. records の初期状態

`records` の4つの置き場所は，導入時に空で作っておく．

```text
mkdir -p .claude/ai-loop/decisions .claude/ai-loop/trials
touch .claude/ai-loop/ERRORS.md .claude/ai-loop/errors_inventory.md
touch .claude/ai-loop/decisions/.keep .claude/ai-loop/trials/.keep
```

ディレクトリは，git が空のディレクトリを記録しないため `.keep` を置く．

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

1. 1〜4 節のファイルを置き，既定ブランチに入れる．
2. `bash .claude/ai-loop/verify.sh` を実行し，終了コード 0 と `VERIFY PASSED` を確かめる．
3. 使う側のリポジトリで `claude --model opus` を起動し，`/ai-loop:commander` と入力して，案を伝える．
4. 司令塔が Issue の一覧と本文の案を示す．承認すると，司令塔が Issue を作る．
5. 司令塔が実装役を起動する．実装役はブランチ作成・実装・検証・pre-push-check・push・PR 作成までを行う．
6. 司令塔が差分・本文・CI・review を確かめ，マージを依頼する．
7. GitHub で PR をマージする．
8. `/ai-loop:post-merge-cleanup <PR番号>` で後始末をする．Issue は PR 本文の `Closes #<番号>` で自動でクローズされる．反映が遅れても手動でクローズしない．ただし，PR を GitHub の既定ブランチ以外へマージした場合は，閉じるキーワードで Issue は自動でクローズされない．post-merge-cleanup がそのことを報告するので，GitHub の Web でクローズする．

## ローカル専用で導入する場合

ai-loop の設定・検証コマンド・記録をコミットしない導入では，次の点だけが違う．手順は README の「ローカル専用で導入する」の節を参照．

- 置き場所：ファイルは上と同じく `.claude/` の下に置き，`.git/info/exclude` に `/.claude/` を足して除外する
- settings：3 節の内容を `.claude/settings.local.json` に書く．deny の `.claude/settings.json` の2行は `.claude/settings.local.json` にする
- 除外の確認：`git status --porcelain --ignored` に `!! .claude/` が出て，`git check-ignore -v .claude/ai-loop.json` が `.git/info/exclude` の行を示すことを確かめる
