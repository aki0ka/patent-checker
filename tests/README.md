# meisai-checker テスト

リファクタリング時のリグレッション検出を目的としたスナップショットテスト。

## 構造

```
tests/
  fixtures/    ← 入力サンプル明細書 (gitignore。ローカルにのみ配置)
  snapshots/   ← analyze() の正解出力 JSON (リポジトリで追跡)
  conftest.py
  test_snapshot_analyze.py     ← analyze() 全体のスナップショット
  test_snapshot_check_funcs.py ← 個別 check_* 関数のスナップショット
```

## 使い方

### 初回セットアップ

`tests/fixtures/` に入力ファイルを配置する。命名規則:

```
tests/fixtures/
  gansho_filing_01.txt   # 出願形式 (【書類名】特許願 から始まる本物の出願書類)
  koukai_01.txt          # 公開公報 (J-PlatPat ブラウザコピー、UTF-8)
  koukai_02.txt          # 公開公報 (J-PlatPat ブラウザコピー、UTF-8)
  koukai_03_sjis.txt     # 公開公報 (J-PlatPat ブラウザコピー、Shift-JIS)
```

最低 1 ファイルあれば動作する。複数あれば各ファイルに対してテストが走る。
file_reader が UTF-8 / UTF-8-SIG / CP932 / Shift-JIS を順に試すので、
J-PlatPat ブラウザコピーの Shift-JIS テキストもそのまま投入できる。

### スナップショットのベースライン作成

```bash
pytest tests/ --update-snapshots
```

`tests/snapshots/` に各 fixture に対応した JSON が生成される。これを git にコミットして「正解」として固定する。

### 通常のテスト実行

```bash
pytest tests/
```

`tests/snapshots/` の JSON と現状の出力が一致するか確認する。リファクタリング中はこれが常に緑であることを目指す。

### 差分確認

スナップショットが壊れた場合、pytest は `actual` と `expected` の差分を出力する。意図的な変更なら `--update-snapshots` で更新し直す。
