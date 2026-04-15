@echo off
chcp 65001 >nul
title meisai-checker
cd /d "%~dp0"

where uv >nul 2>&1
if errorlevel 1 (
    echo.
    echo エラー: uv が見つかりません。
    echo.
    echo 以下のコマンドを PowerShell で実行してインストールしてください:
    echo   powershell -ExecutionPolicy ByPass -c "irm https://astral.sh/uv/install.ps1 ^| iex"
    echo.
    echo インストール後、このファイルを再実行してください。
    echo.
    pause
    exit /b 1
)

uv run --extra gui main.py
if errorlevel 1 pause
