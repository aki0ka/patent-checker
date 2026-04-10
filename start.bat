@echo off
chcp 65001 >nul
title meisai-checker

cd /d "%~dp0"

if not exist ".venv\.installed" (
    call :find_python
    if errorlevel 1 (
        echo.
        echo エラー: Python 3.10 以上が見つかりません。
        echo.
        echo https://www.python.org/downloads/ からインストールしてください。
        echo インストール時に「Add Python to PATH」にチェックを入れてください。
        echo.
        pause
        exit /b 1
    )

    echo [1/2] 初回セットアップ中... ^(数分かかることがあります^)
    if not exist ".venv\Scripts\python.exe" (
        %PYTHON_CMD% -m venv .venv
        if errorlevel 1 (
            echo venv 作成に失敗しました。
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
exit /b 0

:find_python
for %%P in (py python3.13 python3.12 python3.11 python3.10 python3 python) do (
    where %%P >nul 2>&1
    if not errorlevel 1 (
        for /f "tokens=*" %%V in ('%%P -c "import sys; print(sys.version_info[0]*100+sys.version_info[1])" 2^>nul') do (
            if %%V GEQ 310 (
                set PYTHON_CMD=%%P
                exit /b 0
            )
        )
    )
)
exit /b 1
