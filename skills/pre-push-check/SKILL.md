---
name: pre-push-check
description: コミットした後，push する前に使う．.claude/ai-loop.json の verify・scanners・extra_checks に従って，検証・差分の走査・追加行の照合・追加の検査をまとめて実行する．
---

# push 前の検証

## 前提

- 変更はコミット済みであること（`--diff-base` は `origin/<default_branch>...HEAD` の差分を見る）．
- `git fetch origin` を実行してから始める．
- 最初に `.claude/ai-loop.json` を Read する．ファイルがない，または `default_branch`・`verify`・`scanners` がない場合は，ここで止めて報告する（推測で補わない）．以下の `<default_branch>` はその値に置き換える．
- 同じ会話ですでに `.claude/ai-loop.json` を Read していて，その後このファイルを変えていない場合は，読み直さなくてよい（Read ツールが「変化なし」と返した場合も読んだものとみなす）．

## コマンドの実行と判定

- 下の各コードブロックの1行を，1回の Bash 呼び出しで実行する．`&&`・`;` でつながず，1回の応答で複数のツール呼び出しを出さない．
- パイプは読み取り専用の確認と /tmp への書き出しに限る．
- 合否は，Bash ツールの結果がエラー（`Exit code N`）として返ったかどうかで判断する．`; echo "exit=$?"` は付けない．
- `grep -c` は一致が0件のとき終了コード1を返す．Bash ツールがこれをエラーとして返すかどうかに関わらず，件数の値で判断する．

## 手順1: 変更範囲とコミットの確認

```bash
git diff --stat origin/<default_branch>...HEAD
git log origin/<default_branch>..HEAD --format=%B | grep -c -i -E 'co-authored-by|claude-session|generated with'
```

- 変更ファイルが指示の範囲だけであることを確認する．
- 2行目の値が 0 であることを確認する．0 でなければコミットに
  トレーラが付いているので，push せずに報告する．

## 手順2: 追加行の書き出し

```bash
git diff --no-color -U0 origin/<default_branch>...HEAD | grep '^+' | grep -v '^+++' | cut -c2- > /tmp/prepush_added.txt
wc -l < /tmp/prepush_added.txt
```

## 手順3: 検証の実行

次を1つずつ実行する．

1. `verify.command`
2. `scanners` のうち `added_lines_only` が false の走査器：`command` の末尾に `--diff-base origin/<default_branch>` を付ける（bin の `check_no_personal_info.py` はこの形に対応している）
3. `scanners` のうち `added_lines_only` が true の走査器：`command` の末尾に `/tmp/prepush_added.txt` を付ける
4. `extra_checks` のうち `when_changed` がないもの：`command`

- `verify.command` は出力に `verify.pass_marker` があり，エラーとして返らないことを確認する．出力をパイプで `tail` などに渡さない（終了コードが失われる）．
- 同じ HEAD で直前に `verify.command` が成功し，その後に追跡済みのファイルを変えていない（`git status --short --untracked-files=no` が空）場合に限り，再実行せずその結果を使ってよい．未追跡のファイルが検証の結果を変えうるリポジトリ（テストが新しいファイルを拾う等）では，この省略をしない．

`extra_checks` のうち `when_changed` があるものは，差分（`git diff --name-only origin/<default_branch>...HEAD`）にそのどれかのパスが含まれるときだけ `command` を実行する．

- `added_lines_only` が true の走査器は既存文書の全文には使わない（追加した行だけを照合する）．
- 走査器が警告を出した行は，書いてはいけない名前の一部として書かれていないかを
  目で確認する．

## 手順4: 判定

- 1つでも失敗したら push しない．
- 指示の範囲で直せるものは直してコミットし，手順1からやり直す．
- 直せないもの，または直すと指示の範囲を超えるものは，停止して事実だけを報告する．

## しないこと

- 失敗を `|| true` 等で隠さない．
- 走査器の検出行の本文・パターン定義を報告に書き写さない．
