#!/bin/bash
set -e
cd "$(dirname "$0")"

if ! command -v uv >/dev/null 2>&1; then
    echo ""
    echo "エラー: uv が見つかりません。"
    echo ""
    echo "以下のコマンドでインストールしてください:"
    echo "  curl -LsSf https://astral.sh/uv/install.sh | sh"
    echo ""
    echo "インストール後、ターミナルを再起動してからもう一度実行してください。"
    echo ""
    read -p "Enter キーで終了..."
    exit 1
fi

uv run main.py
