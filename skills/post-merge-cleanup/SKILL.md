---
name: post-merge-cleanup
description: Use this skill whenever the user reports that they merged a PR via the GitHub GUI (e.g. "mergeは終えた", "マージ完了", "PRをマージした", "merge done"). Directly performs the standard post-merge housekeeping: reads .claude/ai-loop.json, pulls the default branch, confirms via the GitHub REST API (gh api) that the PR landed as merged, checks whether the linked Issue was auto-closed and, if it is still open, reports that without proposing a close command (auto-close can lag behind the merge), runs the verify command, and safely deletes the now-merged feature branch (local delete after ancestor check, remote via fetch --prune only). Never merges PRs, closes issues, or pushes to the default branch itself — the human always merges via GUI first; this skill only runs the cleanup steps afterward, and still stops for explicit confirmation before anything outside its fixed read-only/cleanup scope.
---

# Post-Merge Cleanup

PRのマージは常に人間がGitHub GUIで行う．このスキルは，マージ**後**の定型後始末を実行する．
最初に `.claude/ai-loop.json` を Read する．ファイルがない，または `repo`・`default_branch`・`verify` がない場合は，ここで止めて報告する（推測で補わない）．
同じ会話ですでに Read していて，その後このファイルを変えていない場合は，読み直さなくてよい（Read ツールが「変化なし」と返した場合も読んだものとみなす）．
以下の `<repo>` は `repo` の値，`<所有者>` はその `/` より前の部分，`<default_branch>` は `default_branch` の値に置き換える．

## いつ使うか

ユーザーが「mergeは終えた」「マージ完了」のように，GUIでのマージ完了を
報告してきたとき．対象PR番号・ブランチ名が会話中に判明していない場合は，
1点だけ確認してから進める．

## GitHub への問い合わせ方法

クラウドセッション（claude.ai/code）では，GraphQL を使う `gh pr list`・`gh pr view`・
`gh issue view` が HTTP 403 になる．このスキルでは，ローカル・クラウドの両方で動く
REST API（`gh api`）だけを使う．`gh pr ...`・`gh issue view` に置き換えない．

## コマンドの実行と判定

- コマンドは1回の Bash 呼び出しに1つだけ実行する．`&&`・`;` でつながない．
- パイプは読み取り専用の確認と /tmp への書き出しに限る．
- 合否は Bash ツールの結果がエラーかどうかで判断する．
- 例外：`git merge-base --is-ancestor` は祖先でないとき終了コード1を返す．これはエラーではなく NO として扱う．手順5の最初の確認（`<branch>` と `<default_branch>`）での NO は squash マージの確認に進み，条件(b)での NO は条件の不成立として停止する．終了コード1以外のエラーは想定外として止める．

## 実行内容（このスキルが直接行う）

1. **`<default_branch>` を最新化**
```
   git switch <default_branch>
   git pull
```

2. **マージ結果の確認**（推測せず`gh api`出力で確認する原則）
```
   git log -3 --format=%h
   gh api repos/<repo>/pulls/<PR番号> --jq '{number, state, merged_at, merge_commit_sha, head_ref: .head.ref}'
```
   `merged_at` が null でないことを出力で確認する（null なら未マージ）．
   未マージならここで停止し，状況を報告する．
   `head_ref` を手順5の対象ブランチ名として使う．

3. **対応Issueの状態確認**（Fixes/Closesキーワードの入れ忘れ対策。PRマージ後も
   IssueがOPENのまま残ることがあるため。失敗記録の対象外
   ―― コードの正誤ではなくGitHub側の状態管理のため）
```
   gh api repos/<repo>/pulls/<N> --jq '[(.body // "") | scan("(?i)\\b(?:close[sd]?|fix(?:e[sd])?|resolve[sd]?)\\s+(#[0-9]+)") | .[0]] | unique'
```
   本文から，閉じるキーワード（Closes・Fixes・Resolves とその活用形．大文字小文字を区別しない）の直後の `#N` の番号だけを取り出して出力する．キーワードのない番号（過去の Issue・PR への言及）は取り出さない．
   呼び出し時に対応 Issue の番号が指定された場合は，その番号を使い，抽出した番号に含まれるかを報告する．
   - **番号が指定された場合，または指定がなく1件だけ見つかった場合**:
     `gh api repos/<repo>/issues/<N> --jq '{state, state_reason}'`
     で `state` が `open` のままでも，クローズのコマンド案は提示しない．
     `Closes #N` による自動クローズはマージから遅れて反映されることがあるため，
     open のままである旨だけを報告し，時間をおいて再確認するよう案内する
     （`gh issue close` は `.claude/settings.json` または `.claude/settings.local.json` の deny 対象）．
   - **番号の指定がなく，抽出した番号が0件，または異なる複数の番号だった場合**: 自動判定は行わず，
     「対応Issueを特定できなかった」旨を報告するに留める（無関係なIssueを
     誤ってクローズ候補として提示しないため）．

4. **検証**
```
   <verify.command> > /tmp/verify_pm<PR番号>.txt 2>&1
```
   パイプを付けずに，出力を /tmp のファイルに保存して実行する（終了コードを隠さないため）．
   合否は Bash ツールの結果がエラーかどうかで判断する．
   続けて別の Bash 呼び出しで次を実行し，`verify.summary_markers` の各目印を含む行を取り出す（検証を別に実行しない）．
```
   grep -e '<summary_markers[0]>' -e '<summary_markers[1]>' ... /tmp/verify_pm<PR番号>.txt
```
   取り出した行を書き写す．出力の末尾だけを切り出して書き写さない（末尾に要約の行が入るとは限らない）．
   既知のゲート値があれば，変化していないか明記する．
   呼び出し元はこの結果を使い，同じ HEAD で verify を重ねて実行しない．
   検証が落ちたらここで停止し，diffを提示して指示を仰ぐ
   （このスキルの範囲外の対応が必要なため）．

5. **ブランチの後始末**
   対象ブランチがローカルに存在しない場合（GitHub の Web 画面で作成したブランチ等）は，
   ローカル削除は不要とし，リモートの確認（下記の `git fetch --prune`）だけを行う．

   ローカルに存在する場合:
```
   git merge-base --is-ancestor <branch> <default_branch>
```

   YESの場合は `git branch -d <branch>` でローカル削除．
   NOの場合（squash マージ等）は，次を実行する．

```
   gh api "repos/<repo>/pulls?state=all&head=<所有者>:<branch>" --jq '[.[] | {number, merged_at, merge_commit_sha, head_sha: .head.sha}]'
```

   次の3条件をすべて確認する．
   (a) 該当 PR がちょうど1件で，`merged_at` が null でない．
   (b) `git merge-base --is-ancestor <merge_commit_sha> <default_branch>` が YES．
   (c) `git rev-parse <branch>` が `head_sha` と一致．
   3条件をすべて満たす場合だけ `git branch -D <branch>` でローカル削除．
   1つでも満たさない場合は削除せず停止し，満たさなかった条件と `git log --format=%h <default_branch>..<branch>` を報告する．
   リモートは `git fetch --prune` で状態確認のみ行う．
   GitHub の自動削除により，リモートは通常すでに `[deleted]` になっている．
   既に `[deleted]` なら追加操作は不要．そうでない場合も
   `git push origin --delete` は実行せず，状況を報告して指示を待つ
   （リモートブランチの明示的削除はこのスキルの自動実行範囲に含めない）．

## このスキルが行わないこと（常に停止して人間の指示を待つ）

- PRのマージ・クローズ・コメント追加
- Issueのクローズ実行とコマンド案の提示（自動クローズの反映を待つ．deny対象でもある）
- リモートブランチの明示的削除（`push origin --delete`）
- 新しいブランチの作成
- 次のIssue／タスクへの着手
- commit / push を伴う一切の変更（後始末はread-only操作とローカルブランチ削除のみ）

## 出力フォーマット

- 箇条書きで（罫線表は使わない）
- 各コマンドの出力を報告する．ただし pull・fetch の出力のうち取得元の行（`From`・`To` で始まる行など，リモートの所在を含む行）は書き写さない
- ブランチ削除の可否と実行結果を明記する
- 完了したら停止し，次の指示を待つ

## 注意

- 途中のいずれかのステップで想定外の状態（PRが未マージ，検証の失敗，
  手順5の3条件の不成立，`gh api` の失敗）に遭遇したら，そこで止めて報告し，
  以降のステップには進まない．
