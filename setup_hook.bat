@echo off
chcp 65001 >nul
setlocal
cd /d "%~dp0"

echo ==============================================================
echo   Claude Code - Discord Notify : setup (user-level hook)
echo ==============================================================
echo.

where python >nul 2>nul
if errorlevel 1 (
    echo [ERROR] Python not found on PATH.
    echo         Install Python 3 first: https://www.python.org/downloads/
    echo.
    pause
    exit /b 1
)

python "%~dp0notify.py" --install-hooks
if errorlevel 1 (
    echo.
    echo [ERROR] Install failed. See the message above.
    pause
    exit /b 1
)

echo.
echo Next steps:
echo   1. Put your Discord webhook URL in notify_config.json
echo   2. Restart Claude Code, or open the /hooks menu once.
echo.
pause
