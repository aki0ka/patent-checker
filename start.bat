@echo off
chcp 65001 >nul
title meisai-checker

cd /d "%~dp0"

if not exist ".venv\.installed" (
    echo [1/2] 初回セットアップ中... ^(数分かかることがあります^)
    if not exist ".venv\Scripts\python.exe" (
        python -m venv .venv
        if errorlevel 1 (
            echo.
            echo エラー: Python が見つかりません。
            echo https://www.python.org/downloads/ からインストールしてください。
            pause
            exit /b 1
        )
    )
    .venv\Scripts\pip install --upgrade pip
    .venv\Scripts\pip install -e ".[gui]"
    if errorlevel 1 (
        echo.
        echo エラー: 依存ライブラリのインストールに失敗しました。
        pause
        exit /b 1
    )
    type nul > .venv\.installed
    echo セットアップ完了
)

echo 起動中...
.venv\Scripts\python main.py
if errorlevel 1 pause
