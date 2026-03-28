# 特許明細書チェッカー

特許明細書の方式要件を自動チェックするツールです。特許事務所・企業知財部での出願前確認作業を支援します。

## 何をチェックするか

| チェック項目 | 内容 |
|---|---|
| M2: 従属関係 | 自己引用・前方引用・マルチマルチクレーム |
| M3: 前記・当該 | 照応詞の先行詞が正しいスコープに存在するか |
| M4: 符号 | 図面符号・変数記号の要素名との対応 |
| M5: 構造 | JIS Z 8301準拠、段落番号、句読点、見出し番号 |
| M6: サポート要件 | 請求項の用語が発明の詳細な説明に記載されているか |

## インストール

Python 3.10以上が必要です。

```bash
pip install patent-checker
```

GUIアプリとして使う場合：

```bash
pip install "patent-checker[gui]"
```

## 使い方

### GUI（デスクトップアプリ）

```bash
patent-checker
```

または添付の `.app` / `.exe` をダブルクリック。

### コマンドライン

```bash
# テキストファイルを解析
patent-checker 明細書.txt

# J-PlatPatからコピーしたテキスト
patent-checker --format jplatpat 明細書.txt

# JSON形式で出力
patent-checker --json 明細書.txt

# HTMLレポートをブラウザで開く
patent-checker --html 明細書.txt
```

### Claude（MCP）と連携

Claude Desktopの設定ファイルに追加：

```json
{
  "mcpServers": {
    "patent-checker": {
      "command": "python",
      "args": ["-m", "patent_checker.mcp_server"]
    }
  }
}
```

Claudeに「この明細書をチェックして」と頼めます。

## 対応フォーマット

- **J-PlatPat形式**: J-PlatPatの公報ページからコピーしたテキスト（自動検出）
- **出願時形式**: 特許庁へ提出する明細書のテキスト（自動検出）

## 開発

```bash
git clone https://github.com/aki0ka/patent-checker
cd patent-checker
pip install -e ".[all]"
```

## ライセンス

MIT License
