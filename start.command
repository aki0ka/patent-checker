#!/bin/bash
set -e
cd "$(dirname "$0")"

SENTINEL=".venv/.installed"

if [ ! -f "$SENTINEL" ]; then
    echo "[1/2] 初回セットアップ中... (数分かかることがあります)"
    if [ ! -f .venv/bin/python ]; then
        python3 -m venv .venv
    fi
    .venv/bin/pip install --upgrade pip
    .venv/bin/pip install -e ".[gui]"
    touch "$SENTINEL"
    echo "セットアップ完了"
fi

echo "起動中..."
.venv/bin/python main.py
