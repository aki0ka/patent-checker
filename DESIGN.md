# meisai-checker アーキテクチャ設計書

## 設計方針

### 基本原則
1. **シーンで分ける** — 「いつ・何のために使うか」が異なる処理は分離する
2. **固定アルゴリズム優先** — LLMは使わない。MeCabも必要な層だけ
3. **CUIで独立呼び出し可能** — 各レイヤーを単独で `meisai <command>` できる
4. **疎結合** — 各レイヤーは上位レイヤーに依存しない

### シーンの違い（なぜ分けるか）

| シーン | タイミング | 担当 |
|--------|----------|------|
| 書式正規化 | 受け取った公報・他形式を出願書類に変換するとき | Layer 1 |
| 文章形式チェック | 文章を書いた直後の自己チェック | Layer 2 |
| 書類構造チェック | 提出前の書類全体の確認 | Layer 3 |
| 特許法的チェック | 明細書として法的に問題ないかの確認 | Layer 4 |
| 文法チェック | 深い言語的問題の検出（MeCab必須） | Layer 5 |

---

## レイヤー構造

```
meisai_checker/
  meisai/
    # ── 共通基盤 ─────────────────────────────
    _io/
      file_reader.py    # txt/docx/pdf読み込み（現状 file_reader.py）
      tokenizer.py      # MeCab形態素解析（現状 tokenizer.py）
      parser.py         # セクション分割・請求項パース（現状 parser.py）

    # ── Layer 1: 書式正規化 ─────────────────
    normalize/
      detector.py       # DocFormat判定（現状 preprocessor.py → detect_format）
      jplatpat.py       # J-PlatPat公報 → 出願書類形式
      pct.py            # PCT形式の差異処理（請求の範囲・要約書）
      filing.py         # 出願書類の正規化（現状 preprocessor.py → _normalize_filing）

    # ── Layer 2: 文章形式チェック ────────────
    # MeCab不要。正規表現のみ
    textcheck/
      kuten.py          # 句点のない文（現状 analyzer.py → check_kuten）
      brackets.py       # 括弧対応の整合性 ← 新規
      repetition.py     # 前記前記・。。・、、等の繰り返し ← 新規
      style.py          # 常体/敬体の整合性 ← 新規
      length.py         # 一文の文字数制限 ← 新規
      charset.py        # JIS-X0208 + 禁止文字（現状 analyzer.py → check_jis）

    # ── Layer 3: 書類構造チェック ────────────
    # 書類の完全性・形式。MeCab不要
    structure/
      sections.py       # 章立て・段落番号（現状 analyzer.py → check_structure, check_para_nums, check_midashi_numbers）
      abstract.py       # 要約書チェック（現状 analyzer.py → check_abstract）
      docfields.py      # 書類フィールド構造（現状 m8_docfields.py）
      gansho.py         # 願書チェック（現状 m9_gansho.py）

    # ── Layer 4: 特許法的チェック ────────────
    # 特許固有の意味的チェック。MeCab必須
    patent/
      dependency.py     # 請求項の引用関係（現状 parser.py → check_dependency）
      anaphora.py       # 前記・当該の照応（現状 analyzer.py → check_zenshou） ※旧M3
      fugo.py           # 符号チェック（現状 analyzer.py → check_fugo） ※旧M4
      title.py          # 発明の名称との整合（現状 analyzer.py → check_title） ※旧M5
      support.py        # サポート要件（現状 analyzer.py → check_support） ※旧M6
      ambiguity.py      # 曖昧性（現状 m7_ambiguity.py） ※旧M7

    # ── Layer 5: 文法チェック ───────────────
    # 深い言語解析。MeCab必須、将来GiNZA対応も視野
    grammar/
      particles.py      # 助詞の連続・浮き（接頭辞+助詞等）← 新規・比較的容易
      argument.py       # 格助詞の項構造未充足 ← 新規・難易度高
      predicate.py      # 係り受けミスマッチ（主述不一致）← 新規・難易度高

    # ── インターフェース ─────────────────────
    cli.py              # CLIエントリポイント（現状 cli.py を更新）
    mcp_server.py       # MCPサーバー（現状 mcp_server.py を更新）
    gui.py              # GUI（現状 gui.py）
    config.py           # 設定（現状 config.py）
    analyze.py          # フルスキャン（全レイヤー実行、現状 analyzer.py → analyze()）
```

---

## CUIインターフェース設計

```bash
# 書式正規化
meisai normalize --from jplatpat input.txt -o output.txt
meisai normalize --from pct input.txt -o output.txt

# 文章形式チェック（MeCabなし、高速）
meisai check-text input.txt
meisai check-text --only kuten,brackets,charset input.txt

# 書類構造チェック
meisai check-structure input.txt
meisai check-structure --type gansho input.txt    # 願書のみ
meisai check-structure --type docfields input.txt # 書類フィールドのみ

# 特許法的チェック（MeCab必須）
meisai check-patent input.txt
meisai check-patent --only anaphora,fugo input.txt

# 文法チェック（MeCab必須）
meisai check-grammar input.txt
meisai check-grammar --only particles input.txt   # 簡易なものだけ

# フルスキャン（現状のデフォルト動作）
meisai check input.txt
meisai check --skip grammar input.txt  # 文法チェックを除外
```

---

## 現状コードとの対応表

| 現状 | 移行先 | 備考 |
|------|--------|------|
| preprocessor.py detect_format | normalize/detector.py | そのまま移動 |
| preprocessor.py normalize | normalize/filing.py + jplatpat.py | 分割 |
| parser.py split_sections, parse_claims | _io/parser.py | そのまま移動 |
| parser.py check_dependency | patent/dependency.py | 移動 |
| analyzer.py check_zenshou | patent/anaphora.py | 移動 |
| analyzer.py check_fugo | patent/fugo.py | 移動 |
| analyzer.py check_jis | textcheck/charset.py | 移動 |
| analyzer.py check_structure | structure/sections.py | 移動 |
| analyzer.py check_para_nums | structure/sections.py | 統合 |
| analyzer.py check_kuten | textcheck/kuten.py | 移動 |
| analyzer.py check_abstract | structure/abstract.py | 移動 |
| analyzer.py check_midashi_numbers | structure/sections.py | 統合 |
| analyzer.py check_title | patent/title.py | 移動 |
| analyzer.py check_support | patent/support.py | 移動 |
| analyzer.py build_blocks, _highlight_* | analyze.py または gui.py | GUI専用ロジック |
| m7_ambiguity.py | patent/ambiguity.py | 移動 |
| m8_docfields.py | structure/docfields.py | 移動 |
| m9_gansho.py | structure/gansho.py | 移動 |

---

## 実装優先度

### Phase 1: リファクタリング（機能追加なし）
analyzer.py を上記の対応表に従って分割するだけ。  
動作は変わらない。テストで確認しながら進める。

### Phase 2: Layer 2 拡充（新規チェック追加）
MeCab不要で実装可能なものから：
1. `brackets.py` — 括弧対応の整合性
2. `repetition.py` — 前記前記・。。等
3. `style.py` — 常体/敬体
4. `length.py` — 文字数制限
5. `charset.py` への禁止文字追加

### Phase 3: Layer 1 完成（書式正規化）
- J-PlatPat公報 → 出願書類変換の完成
- PCT対応

### Phase 4: Layer 5 導入（文法チェック）
- `particles.py`（助詞の連続）から着手
- `argument.py`・`predicate.py` は依存パーサー（GiNZA推奨）が必要

---

## 技術メモ

### Layer 5 の文法チェックに必要なもの
- **現状のMeCab（fugashi）** では品詞列の表層的なチェックのみ可能
- **係り受け解析（dependency parsing）** には GiNZA（spaCy + ja_ginza モデル）が必要
- `particles.py`（助詞の連続）は MeCab だけで実装可能
- `argument.py`（格助詞の項構造）と `predicate.py`（主述不一致）は GiNZA 推奨

### MCPサーバーへの公開単位
各 `check-*` コマンドをそれぞれ独立したMCPツールとして公開することで、  
AIエージェントが「文章形式チェックだけ」「符号チェックだけ」と選択的に呼び出せる。

```python
# MCPツールとして公開する単位（例）
@mcp.tool()
def check_text(text: str, checks: list[str] = None) -> list[dict]: ...

@mcp.tool()
def check_patent(text: str, checks: list[str] = None) -> list[dict]: ...

@mcp.tool()
def normalize(text: str, source_format: str = "auto") -> str: ...
```
