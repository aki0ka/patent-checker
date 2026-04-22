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
| TC: 文章形式 | 括弧対応・語句の繰り返し・敬体混入・一文の長さ |
| G1: 助詞 | 同一助詞の連続・「の」の過剰連鎖 |

## はじめかた

### 最も簡単な方法（推奨）

**ステップ 1 — uv をインストール（初回のみ・Python 不要）**

**Mac** — ターミナルに貼り付けて Enter:

```bash
curl -LsSf https://astral.sh/uv/install.sh | sh
```

**Windows** — PowerShell に貼り付けて Enter:

```powershell
powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 | iex"
```

インストール後、ターミナル / PowerShell を **一度閉じて再起動** してください。

**ステップ 2 — 起動**

```bash
uvx meisai-checker
```

初回はライブラリのダウンロードに数分かかります。以降は即座に起動します。

**アップデート**:

```bash
uvx meisai-checker@latest
```

**完全に消す**:

```bash
uv cache clean
```

---

### ソースから実行する方法

git clone してローカルで動かしたい場合:

**Mac**:

```bash
git clone https://github.com/aki0ka/meisai-checker.git ~/meisai-checker && ~/meisai-checker/start.command
```

**Windows**:

1. [ZIPをダウンロード](https://github.com/aki0ka/meisai-checker/archive/refs/heads/main.zip)
2. 任意のフォルダに展開
3. フォルダ内の `start.bat` をダブルクリック

## 使い方

### GUI（デスクトップアプリ）

```bash
uvx meisai-checker
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

Claude Desktopの設定ファイルに追加します。

```json
{
  "mcpServers": {
    "meisai-checker": {
      "command": "uvx",
      "args": ["--with", "fastmcp", "--with", "pytoony", "meisai-checker-mcp"]
    }
  }
}
```

Claudeから使えるツール：

| ツール | 用途 |
|---|---|
| `patent_check_summary` | 全チェック（M2〜M9・TC・G1）のエラー・警告サマリー |
| `patent_check_issues` | 全チェックの詳細issueリスト（レベル・マイルストーンでフィルタ可） |
| `patent_check_m3` | M3 照応詞（前記・当該）チェックのみ |
| `patent_check_m4` | M4 符号チェックのみ |
| `patent_check_m7` | M7 係り受け曖昧性チェックのみ |
| `patent_check_m8` | M8 明細書記録項目チェックのみ |
| `patent_check_m9` | M9 特許願記録項目チェックのみ |

MCPサーバーの出力はTOON形式（JSON比で約30%トークン削減）を使用しています。

## 対応フォーマット

- **J-PlatPat形式**: J-PlatPatの公報ページからコピーしたテキスト（自動検出）
- **出願時形式**: 特許庁へ提出する明細書のテキスト（自動検出）
- **Word (.docx)**: GUI/CLIでファイルを直接読み込み（全段落を順に結合）
- **PDF (.pdf)**: テキストレイヤー付きPDFのみ対応（スキャンPDFは非対応）

## トラブルシューティング

### Mac: `You have not agreed to the Xcode and Apple SDKs license` と表示される

macOS のアップデートや Xcode の再インストール後に表示されることがあります。ターミナルで以下を実行して同意してください:

```bash
sudo xcodebuild -license accept
```

パスワードを求められたら Mac のログインパスワードを入力します。完了後、もう一度 `uvx meisai-checker` を実行してください。

### `uv: command not found` と表示される

uv がインストールされていないか、ターミナルを再起動していません。「ステップ 1」のコマンドを実行し、ターミナルを閉じて再起動してから再試行してください。

### MeCab（形態素解析）が動かない

`pip install fugashi unidic-lite` を実行してください。MeCab が動かない場合、M3（前記チェック）・M4（符号チェック）・M6（サポート要件）・M7（曖昧性）が実行されませんが、それ以外のチェックは動作します。

## フィードバック・改善提案

バグ報告・機能要望・チェックルールの改善提案を歓迎します。[GitHub Issues](https://github.com/aki0ka/meisai-checker/issues) までお気軽にどうぞ。実際の特許実務に基づくご意見は特に歓迎です。

## 開発

```bash
git clone https://github.com/aki0ka/meisai-checker
cd meisai-checker
uv run main.py        # GUI起動
uv run -m meisai_checker.cli --help  # CLIヘルプ
```

## ライセンス

MIT License


