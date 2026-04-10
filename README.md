# meisai-checker — 特許明細書チェッカー

特許明細書・特許願の方式要件を自動チェックするツールです。特許事務所・企業知財部での出願前確認作業を支援します。

**完全ローカル動作・無料・オープンソース** — 特許明細書は出願前の秘匿情報です。本ツールはすべての処理をお手元のPC上で完結し、入力テキストが外部に送信されることは一切ありません。ソースコードを直接確認できます。

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

## はじめかた

**Python 3.10以上が必要です。** 起動スクリプトが自動で検出します。

- **Mac**: Python 3.10以上が入っていない場合は `brew install python@3.12` または [python.org](https://www.python.org/downloads/) からインストール（macOS標準の`python3`はXcode付属の3.9で古いので注意）
- **Windows**: [python.org](https://www.python.org/downloads/) からインストール（「Add Python to PATH」にチェック）

### Windows

1. [ZIPをダウンロード](https://github.com/aki0ka/meisai-checker/archive/refs/heads/main.zip) して展開
2. `start.bat` をダブルクリック

### Mac

ターミナルで以下を実行してください（`git` が必要です。未インストールの場合は初回実行時にXcodeコマンドラインツールのインストールを促されます）:

```bash
git clone https://github.com/aki0ka/meisai-checker.git
cd meisai-checker
./start.command
```

2回目以降は `cd meisai-checker && ./start.command` で起動します。

> **なぜZIPではなくgit cloneか**: macOSはインターネットからダウンロードしたスクリプトを安全のためブロックします（Gatekeeper）。git clone した場合はこの制限がかからないため、追加の設定なしで実行できます。

<details>
<summary>どうしてもZIPで使いたい場合</summary>

ZIPをダウンロードして展開した後、ターミナルで隔離属性を削除してから実行してください:

```bash
xattr -cr ~/Downloads/meisai-checker-main
cd ~/Downloads/meisai-checker-main
./start.command
```
</details>

初回のみ自動でセットアップが走ります（venv作成＋依存インストール）。2回目以降は即起動します。

## 使い方

### GUI（デスクトップアプリ）

`start.bat` / `start.command` で起動、または:

```bash
meisai-checker
```

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
meisai-checker 明細書.txt

# JSON形式で出力
meisai-checker --json 明細書.txt

# HTMLレポートをブラウザで開く
meisai-checker --html 明細書.txt
```

### Claude（MCP）と連携

Claude Desktopの設定ファイルに追加します。`/path/to/meisai-checker` は展開したフォルダのパスに置き換えてください。

```json
{
  "mcpServers": {
    "meisai-checker": {
      "command": "/path/to/meisai-checker/.venv/bin/python",
      "args": ["-m", "meisai_checker.mcp_server"],
      "cwd": "/path/to/meisai-checker"
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

## フィードバック・改善提案

バグ報告・機能要望・チェックルールの改善提案を歓迎します。[GitHub Issues](https://github.com/aki0ka/meisai-checker/issues) までお気軽にどうぞ。実際の特許実務に基づくご意見は特に歓迎です。

## 開発

```bash
git clone https://github.com/aki0ka/meisai-checker
cd meisai-checker
pip install -e ".[all]"
python main.py        # GUI起動
meisai-checker --help # CLIヘルプ
```

## ライセンス

MIT License
