#!/bin/bash
set -e
cd "$(dirname "$0")"

SENTINEL=".venv/.installed"

find_python() {
    for cmd in python3.13 python3.12 python3.11 python3.10 python3 python; do
        if command -v "$cmd" >/dev/null 2>&1; then
            ver=$("$cmd" -c 'import sys; print("{}.{}".format(sys.version_info[0], sys.version_info[1]))' 2>/dev/null || echo "")
            case "$ver" in
                3.10|3.11|3.12|3.13|3.14)
                    echo "$cmd"
                    return 0
                    ;;
            esac
        fi
    done
    return 1
}

if [ ! -f "$SENTINEL" ]; then
    PYTHON=$(find_python) || {
        echo ""
        echo "エラー: Python 3.10 以上が見つかりません。"
        echo ""
        echo "インストール方法:"
        echo "  1. Homebrew を使う場合:  brew install python@3.12"
        echo "  2. 公式サイトからインストール:  https://www.python.org/downloads/"
        echo ""
        echo "インストール後にもう一度このスクリプトを実行してください。"
        echo ""
        read -p "Enter キーで終了..."
        exit 1
    }
    echo "[1/2] 初回セットアップ中... ($PYTHON を使用、数分かかります)"
    if [ ! -f .venv/bin/python ]; then
        "$PYTHON" -m venv .venv
    fi
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e ".[gui]"
    touch "$SENTINEL"
    echo "セットアップ完了"
fi

echo "起動中..."
.venv/bin/python main.py
