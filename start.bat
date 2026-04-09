@echo off
chcp 65001 >nul
title meisai-checker

cd /d "%~dp0"

if not exist ".venv\Scripts\python.exe" (
    echo [1/2] 初回セットアップ中...
    python -m venv .venv
    if errorlevel 1 (
        echo.
        echo エラー: Python が見つかりません。
        echo https://www.python.org/downloads/ からインストールしてください。
        pause
        exit /b 1
    )
    .venv\Scripts\pip install --quiet -e ".[gui]"
    echo セットアップ完了
)

echo 起動中...
.venv\Scripts\python main.py
