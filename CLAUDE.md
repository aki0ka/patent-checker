# meisai-checker — Claude Code 引き継ぎファイル

## プロジェクト概要

日本語特許明細書・特許願の方式要件を自動チェックするツール。
**完全ローカル動作・無料・OSS（MIT）**

- GitHub: https://github.com/aki0ka/meisai-checker
- 作者: 岡田 晃久（弁理士 登録番号14374）
- リリース名: meisai-checker（旧称 patent-checker、2026-04に改名）

---

## 現在の実装状況

### パッケージ構成

```
meisai_checker/        ← Pythonパッケージ（旧 patent_checker/）
  __init__.py
  analyzer.py          ← メインロジック（2200行超、要分割）
  cli.py               ← CLIエントリポイント
  config.py            ← 設定管理
  file_reader.py       ← txt/docx/pdf読み込み
  gui.py               ← PyWebViewベースのGUI
  html_template.html   ← GUIフロントエンド
  m7_ambiguity.py      ← M7: 係り受け曖昧性チェック
  m8_docfields.py      ← M8: 明細書記録項目チェック（fc1〜fc12）
  m9_gansho.py         ← M9: 特許願記録項目チェック（ga1〜ga12）
  mcp_server.py        ← MCPサーバー（FastMCP）
  parser.py            ← セクション分割・請求項パース・M2依存関係
  preprocessor.py      ← 書式検出・正規化（J-PlatPat/出願書類）
  tokenizer.py         ← fugashi（MeCab）形態素解析
  viewer.py            ← 結果表示ヘルパー
main.py                ← GUI起動エントリポイント
DESIGN.md              ← アーキテクチャ設計書（2026-04策定）
README.md              ← ユーザー向けドキュメント
```

### 実装済みチェック

| ID | 関数 | 場所 | 内容 |
|----|------|------|------|
| M2 | check_dependency | parser.py | 自己引用・前方引用・マルチマルチクレーム |
| M3 | check_zenshou | analyzer.py | 前記・当該の照応詞チェック（MeCab使用） |
| M4 | check_fugo | analyzer.py | 符号・変数記号と要素名の対応 |
| M5 | check_structure, check_para_nums, check_kuten, check_abstract, check_midashi_numbers, check_title | analyzer.py | JIS Z 8301準拠・段落番号・句読点・見出し |
| M6 | check_support | analyzer.py | サポート要件（請求項の用語が詳細説明にあるか） |
| M7 | check_ambiguity | m7_ambiguity.py | 係り受け曖昧性（AまたはBのC等） |
| M8 | check_docfields | m8_docfields.py | 明細書記録項目・様式第29 |
| M9 | check_gansho | m9_gansho.py | 願書記録項目・様式第26 |
| JIS | check_jis | analyzer.py | JIS-X0208-1997・禁止文字チェック |

---

## リファクタリング Phase 1 進捗（2026-04-11 時点）

### テスト基盤（Phase 0）: ✅ 完了

- `tests/` 以下にスナップショットテスト整備済み
- fixture: `tests/fixtures/` (gitignore) に 4 件
  - `gansho_filing_01.txt` — **出願形式**（ハンドスキャナ事例、UTF-8）
  - `koukai_01.txt` — J-PlatPat 公報（UTF-8）
  - `koukai_02.txt` — J-PlatPat 公報（UTF-8）
  - `koukai_03_sjis.txt` — J-PlatPat 公報（Shift-JIS）
- snapshot: `tests/snapshots/` (git 追跡対象) に 44 件の golden JSON

**テスト実行コマンド:**
```bash
# 使用する Python インタープリタ
/Users/akihisa/Desktop/meisai-checker/.venv/bin/python

# 通常実行（緑を死守）
/Users/akihisa/Desktop/meisai-checker/.venv/bin/python -m pytest tests/ -q

# ベースライン再作成（挙動を意図的に変えた後）
/Users/akihisa/Desktop/meisai-checker/.venv/bin/python -m pytest tests/ --update-snapshots
```

**既知の非決定性バグ（テスト側で吸収済み）:**
`structure/docfields.py`（旧 m8_docfields.py）の `_NEEDS_PARA = {...}` が **set** のため、
PYTHONHASHSEED 依存で issue の並び順が変わる。`test_snapshot_analyze.py` の
`_sort_issue_lists()` でソートして回避済み。Phase 2 以降で `set → tuple` に直す。

### analyzer.py 分割状況（Phase 1 完了）

`analyzer.py` は 2261行 → **208行** に縮小済み（analyze() + 再エクスポートシムのみ）。

| ステップ | 移動先 | 状態 |
|---------|--------|------|
| Phase 1-1 | `textcheck/kuten.py` ← check_kuten | ✅ 完了・テスト緑 |
| Phase 1-2 | `textcheck/charset.py` ← check_jis | ✅ 完了・テスト緑 |
| Phase 1-3 | `structure/abstract.py` ← check_abstract | ✅ 完了・テスト緑 |
| Phase 1-4 | `patent/title.py` ← check_title | ✅ 完了・テスト緑 |
| Phase 1-5 | `structure/sections.py` ← check_structure 等 | ✅ 完了・テスト緑 |
| Phase 1-6 | `patent/support.py` ← check_support | ✅ 完了・テスト緑 |
| Phase 1-7 | `patent/anaphora.py` ← check_zenshou, build_noun_groups | ✅ 完了・テスト緑 |
| Phase 1-8 | `patent/fugo.py` ← check_fugo（〜600行） | ✅ 完了・テスト緑 |
| Phase 1-9 | m7→`patent/ambiguity.py`, m8→`structure/docfields.py`, m9→`structure/gansho.py` | ✅ 完了・テスト緑 |
| Phase 1-10 | `blocks.py` ← build_blocks, _highlight_* | ✅ 完了・テスト緑 |
| Phase 1-11 | `analyzer.py` を再エクスポートシムに縮小 | ✅ 完了（208行） |

**Phase 1 完了。次は git commit してから Phase 2 へ。**

**次の作業:** `git commit` で変更を保存すること（未コミット状態）。

### 現在のパッケージ構造

```
meisai_checker/
  analyzer.py          ← 208行（analyze() + 再エクスポートシム）
  blocks.py            ← build_blocks / _highlight_* （ビューア用）
  textcheck/
    kuten.py           ← check_kuten
    charset.py         ← check_jis
  structure/
    abstract.py        ← check_abstract
    sections.py        ← check_structure, check_para_nums, check_midashi_numbers
    docfields.py       ← check_docfields（旧 m8_docfields.py）
    gansho.py          ← check_gansho（旧 m9_gansho.py）
  patent/
    anaphora.py        ← check_zenshou, build_noun_groups
    fugo.py            ← check_fugo, classify_fugo, FUGO_EXCLUDE_LIST 等
    title.py           ← check_title
    support.py         ← check_support
    ambiguity.py       ← check_ambiguity（旧 m7_ambiguity.py）
```

---

## 次にやること（設計方針）

**DESIGN.md に詳細な設計書あり。必ず参照すること。**

### 基本方針
- シーンで分ける（書式正規化 / 文章形式 / 書類構造 / 特許法的 / 文法）
- 固定アルゴリズム優先、LLM不使用、MeCabも必要な層だけ
- CUIで独立呼び出し可能（`meisai check-text`, `meisai check-patent` 等）

### Phase 1: analyzer.py の分割（機能追加なし、リファクタリングのみ）

analyzer.py（2200行）を以下に分割する：

| 移動先 | 対象関数 |
|--------|---------|
| `textcheck/kuten.py` | check_kuten |
| `textcheck/charset.py` | check_jis, _jis_char_status |
| `structure/sections.py` | check_structure, check_para_nums, check_midashi_numbers |
| `structure/abstract.py` | check_abstract |
| `patent/anaphora.py` | check_zenshou, get_all_ancestors, extract_noun_phrase_after, extract_defined_nouns |
| `patent/fugo.py` | check_fugo, classify_fugo, _collect_fugo_suffix, _extract_elements_tokens, check_fugo_setsumeisho |
| `patent/title.py` | check_title |
| `patent/support.py` | check_support, extract_nouns_for_support |
| `analyze.py` | analyze(), build_blocks(), _highlight_* （GUI表示ロジック） |

### Phase 2: Layer 2 新規チェック追加（MeCab不要）

```
textcheck/brackets.py    # 括弧対応（「（」に対応する「）」がないなど）
textcheck/repetition.py  # 前記前記・。。・、、などの繰り返し
textcheck/style.py       # 常体/敬体の整合性（です・ます体を検出）
textcheck/length.py      # 一文の文字数制限（デフォルト120字）
```

### Phase 3: Layer 1 書式正規化の完成

preprocessor.py を `normalize/` に分割・拡充。
PCT形式（「請求の範囲」「要約書」の差異）対応。

---

## 技術的な注意事項

### MeCab / fugashi
- `tokenizer.py` の `Tokenizer` クラスを使うこと
- 直接 fugashi を呼ばない

### pywebview（GUI）
- `window.width` が `None` を返すバグあり → config保存時は `isinstance(w, int) and w > 0` で確認済み
- D&DはFileReader APIベース（file.pathは使えない）

### FUGO_EXCLUDE_LIST
- `analyzer.py` の先頭付近にある除外リスト
- 誤検出防止のために単語を追加してきた経緯あり

### TOON形式
- MCPサーバーの出力フォーマット（JSON比で約30%トークン削減）
- `mcp_server.py` 内で定義

### 文法チェック（Layer 5）について
- `particles.py`（助詞の連続）は MeCab だけで実装可能
- `argument.py`（格助詞の項構造）と `predicate.py`（主述不一致）は **GiNZA** が必要
- GiNZAは未導入。導入する場合は `pip install ginza ja-ginza` が必要

---

## 開発環境

- macOS (MacBook Air M2)
- Python 3.10+
- fugashi + unidic-lite（MeCab）
- pywebview（GUI）
- FastMCP（MCPサーバー）
- Node.js（personal-manager-app / SoloMGR の開発と並行）

## よく使うコマンド

```bash
cd ~/projects/meisai_checker

# GUI起動
python main.py

# CLIチェック
meisai-checker 明細書.txt
meisai-checker --json 明細書.txt

# 開発モードインストール
pip install -e ".[all]"
```
