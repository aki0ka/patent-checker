# meisai-checker — Claude Code 引き継ぎファイル

## プロジェクト概要

日本語特許明細書・特許願の方式要件を自動チェックするツール。
**完全ローカル動作・無料・OSS（MIT）**

バージョン管理: `git rev-list --count HEAD` をマイナーバージョンに使用。mainへのpushごとにGitHub Actionsが `0.N.0` に自動更新。

- GitHub: https://github.com/aki0ka/meisai-checker
- 作者: 岡田 晃久（弁理士 登録番号14374）
- リリース名: meisai-checker（旧称 patent-checker、2026-04に改名）

---

## 現在の実装状況（2026-04-11 更新）

### 実装済みチェック

| ID | 関数 | 場所 | 内容 |
|----|------|------|------|
| M2 | check_dependency | parser.py | 自己引用・前方引用・マルチマルチクレーム |
| M3 | check_zenshou | patent/anaphora.py | 前記・当該の照応詞チェック（MeCab使用） |
| M4 | check_fugo | patent/fugo.py | 符号・変数記号と要素名の対応 |
| M5 | check_structure 等 | structure/sections.py 等 | JIS Z 8301準拠・段落番号・句読点・見出し |
| M6 | check_support | patent/support.py | サポート要件（請求項の用語が詳細説明にあるか） |
| M7 | check_ambiguity | patent/ambiguity.py | 係り受け曖昧性（AまたはBのC等） |
| M8 | check_docfields | structure/docfields.py | 明細書記録項目・様式第29 |
| M9 | check_gansho | structure/gansho.py | 願書記録項目・様式第26 |
| TC1 | check_brackets | textcheck/brackets.py | 括弧対応の整合性 |
| TC2 | check_repetition | textcheck/repetition.py | 語句・句読点の繰り返し |
| TC3 | check_style | textcheck/style.py | 敬体（です・ます）混入検出 |
| TC4 | check_length | textcheck/length.py | 一文200文字超の警告 |
| G1 | check_particles | grammar/particles.py | 同一助詞連続・「の」過剰連鎖（MeCab使用） |

### パッケージ構成

```
meisai_checker/
  __init__.py            ← __version__ = "16.1.0"
  analyzer.py            ← 220行（analyze() + 再エクスポートシム）
  blocks.py              ← build_blocks / _highlight_*（ビューア用）
  cli.py                 ← CLIエントリポイント
  config.py              ← 設定管理
  file_reader.py         ← txt/docx/pdf読み込み
  gui.py                 ← PyWebViewベースのGUI
  html_template.html     ← GUIフロントエンド
  mcp_server.py          ← MCPサーバー（FastMCP）
  parser.py              ← セクション分割・請求項パース・M2依存関係
  preprocessor.py        ← 書式検出・正規化（J-PlatPat/出願書類）
  tokenizer.py           ← fugashi（MeCab）形態素解析
  viewer.py              ← 結果表示ヘルパー
  textcheck/
    kuten.py             ← check_kuten
    charset.py           ← check_jis
    brackets.py          ← check_brackets（TC1）
    repetition.py        ← check_repetition（TC2）
    style.py             ← check_style（TC3）
    length.py            ← check_length（TC4）
  structure/
    abstract.py          ← check_abstract
    sections.py          ← check_structure, check_para_nums, check_midashi_numbers
    docfields.py         ← check_docfields（旧 m8_docfields.py）
    gansho.py            ← check_gansho（旧 m9_gansho.py）
  patent/
    anaphora.py          ← check_zenshou, build_noun_groups
    fugo.py              ← check_fugo, classify_fugo, FUGO_EXCLUDE_LIST 等
    title.py             ← check_title
    support.py           ← check_support
    ambiguity.py         ← check_ambiguity（旧 m7_ambiguity.py）
  grammar/
    particles.py         ← check_particles（G1）
main.py                  ← GUI起動エントリポイント
DESIGN.md                ← アーキテクチャ設計書（2026-04策定）
README.md                ← ユーザー向けドキュメント
.github/ISSUE_TEMPLATE/
  false_detection.md     ← 誤検知・見逃し報告フォーム
```

### テスト基盤

- `tests/fixtures/` (gitignore) に 4 件のサンプル明細書
- `tests/snapshots/` に 65 件の golden JSON（git 追跡対象）

**テスト実行コマンド:**
```bash
# venv（依存ライブラリ一式入り）
/Users/akihisa/Desktop/meisai-checker/.venv/bin/python -m pytest tests/ -q

# ベースライン再作成（analyze() の出力を意図的に変えた後）
/Users/akihisa/Desktop/meisai-checker/.venv/bin/python -m pytest tests/ --update-snapshots
```

---

## 既知の課題・今後の方針

### 検出精度（偽陽性・偽陰性）

- **M個の端末** など「アルファベット＋個」の量化子表現を符号と誤検知する場合がある
- **土台側、範囲内、走査線上** など方位・方角指示文言（側・内・上・下・直下・近傍等）が名詞境界を侵害することがある
- NEologd 導入では根本解決にならない（辞書語彙でなく形態素境界の問題）
- `.github/ISSUE_TEMPLATE/false_detection.md` でユーザーフィードバックを収集し、事例が集まってからルール化する方針

### 次の作業候補

| 優先度 | 作業 | 規模 |
|--------|------|------|
| 中 | Phase 3: preprocessor.py → normalize/ 分割・PCT対応 | 大 |
| 中 | analyze() 戻り値を Issue dataclass に統一 | 中 |
| 中 | CLI サブコマンド化（meisai check-text 等） | 中 |
| 低 | Layer 5: argument.py / predicate.py（GiNZA必要、未導入） | 大 |

---

## 技術的な注意事項

### MeCab / fugashi
- `tokenizer.py` の `_tokenize()` を使うこと。直接 fugashi を呼ばない

### pywebview（GUI）
- `window.width` が `None` を返すバグあり → config保存時は `isinstance(w, int) and w > 0` で確認済み
- D&D は FileReader API ベース（file.path は使えない）

### FUGO_EXCLUDE_LIST
- `patent/fugo.py` にある除外リスト
- 誤検出防止のために単語を追加してきた経緯あり

### TOON形式
- MCP サーバーの出力フォーマット（JSON比で約30%トークン削減）
- `mcp_server.py` 内で定義

### 文法チェック（Layer 5）について
- `particles.py`（助詞の連続）は実装済み（MeCab のみ）
- `argument.py`（格助詞の項構造）と `predicate.py`（主述不一致）は **GiNZA** が必要
- GiNZA は未導入。導入する場合は `pip install ginza ja-ginza`

---

## 開発環境

- macOS (MacBook Air M2)
- Python 3.12（Desktop venv: `/Users/akihisa/Desktop/meisai-checker/.venv`）
- fugashi + unidic-lite（MeCab）
- pywebview（GUI）
- FastMCP（MCPサーバー）

## よく使うコマンド

```bash
cd ~/projects/meisai_checker

# GUI起動（Desktop venv を使用）
/Users/akihisa/Desktop/meisai-checker/.venv/bin/python main.py

# テスト
/Users/akihisa/Desktop/meisai-checker/.venv/bin/python -m pytest tests/ -q

# push
git push origin main
```

