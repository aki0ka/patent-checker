# 特許明細書チェッカー

特許明細書・特許願の方式要件を自動チェックするツールです。特許事務所・企業知財部での出願前確認作業を支援します。

## 何をチェックするか

| チェック項目 | 内容 |
|---|---|
| M2: 従属関係 | 自己引用・前方引用・マルチマルチクレーム |
| M3: 前記・当該 | 照応詞の先行詞が正しいスコープに存在するか |
| M4: 符号 | 図面符号・変数記号の要素名との対応 |
| M5: 構造 | JIS Z 8301準拠、段落番号、句読点、見出し番号 |
| M6: サポート要件 | 請求項の用語が発明の詳細な説明に記載されているか |
| M7: 係り受け曖昧性 | 「AまたはBのC」構造など複数解釈が生じやすいパターン |
| M8: 明細書記録項目 | 様式第29に基づく必須項目・順序・段落番号の整合性 |
| M9: 特許願記録項目 | 様式第26に基づく願書の必須記載事項・書式 |

## ダウンロード（インストール不要）

GitHubリリースページからOSに合った実行ファイルをダウンロードしてダブルクリックするだけで動きます。

- **Mac**: `PatentChecker-mac.zip`
- **Windows**: `PatentChecker-win.zip`

→ [Releases](https://github.com/aki0ka/patent-checker/releases)

## Pythonでインストール

Python 3.10以上が必要です。

```bash
# CLIのみ（最小構成）
pip install patent-checker

# GUIアプリ付き（.docx / .pdf の読み込みを含む）
pip install "patent-checker[gui]"

# MCPサーバー付き（Claude Desktopと連携）
pip install "patent-checker[mcp]"

# すべて
pip install "patent-checker[all]"
```

## 使い方

### GUI（デスクトップアプリ）

```bash
python -m patent_checker
```

または `patent-checker` コマンド、もしくはダウンロードした `.app` / `.exe` をダブルクリック。

**入力方法**

- ファイルをウィンドウにドラッグ＆ドロップ（`.txt` / `.docx` / `.pdf`）
- テキストエリアに貼り付けて「チェック実行」ボタンを押す

**その他の機能**

- 「📌 前面固定」：常に前面表示のON/OFF（設定は次回起動時も保持）
- 「📋 コピー」：チェック結果をMarkdown形式でクリップボードにコピー
- ☀/🌙：ライト/ダークテーマ切り替え

### コマンドライン

```bash
# テキストファイルを解析
patent-checker 明細書.txt

# JSON形式で出力
patent-checker --json 明細書.txt

# HTMLレポートをブラウザで開く
patent-checker --html 明細書.txt
```

### Claude（MCP）と連携

`pip install "patent-checker[mcp]"` の後、Claude Desktopの設定ファイルに追加します。

```json
{
  "mcpServers": {
    "patent-checker": {
      "command": "python3",
      "args": ["-m", "patent_checker.mcp_server"]
    }
  }
}
```

Claudeから使えるツール：

| ツール | 用途 |
|---|---|
| `patent_check_full` | 全チェック（M2〜M8）を一括実行 |
| `patent_check_m7` | 係り受け曖昧性チェックのみ |
| `patent_check_m8` | 明細書記録項目チェックのみ |
| `patent_check_m9` | 特許願記録項目チェックのみ |

MCPサーバーの出力はTOON形式（JSON比で約30%トークン削減）を使用しています。

## 対応フォーマット

- **J-PlatPat形式**: J-PlatPatの公報ページからコピーしたテキスト（自動検出）
- **出願時形式**: 特許庁へ提出する明細書のテキスト（自動検出）
- **Word (.docx)**: GUI/CLIでファイルを直接読み込み（全段落を順に結合）
- **PDF (.pdf)**: テキストレイヤー付きPDFのみ対応（スキャンPDFは非対応）

## 開発

```bash
git clone https://github.com/aki0ka/patent-checker
cd patent-checker
pip install -e ".[all]"
python main.py        # GUI起動
patent-checker --help # CLIヘルプ
```

## ライセンス

MIT License
