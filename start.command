#!/bin/bash
cd "$(dirname "$0")"

if [ ! -f .venv/bin/python ]; then
    echo "[1/2] 初回セットアップ中..."
    python3 -m venv .venv
    .venv/bin/pip install --quiet -e ".[gui]"
    echo "セットアップ完了"
fi

echo "起動中..."
.venv/bin/python main.py
