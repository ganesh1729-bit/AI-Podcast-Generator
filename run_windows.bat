@echo off
REM ============================================================
REM  AI Podcast Generator - Windows runner
REM
REM  Examples (run from a Command Prompt, or double-click for help):
REM    run_windows.bat generate --topic "The future of UPI in India" --lang en-IN --minutes 8 --out episode.wav
REM    run_windows.bat generate --topic "गगनयान मिशन की तैयारी" --lang hi-IN --out gagan.wav
REM    run_windows.bat voices --lang ta-IN
REM    run_windows.bat generate --topic "ISRO" --script-only
REM ============================================================
setlocal
cd /d "%~dp0"

if not exist ".venv\Scripts\activate.bat" (
    echo [X] Not set up yet. Please run  setup_windows.bat  first.
    pause
    exit /b 1
)

call ".venv\Scripts\activate.bat"

REM Make sure a key is available (from env or .env).
if "%SARVAM_API_KEY%"=="" (
    if not exist ".env" (
        echo [X] No API key found.
        echo     Either set it for this window:   set SARVAM_API_KEY=your-key
        echo     or put it in .env:                SARVAM_API_KEY=your-key
        pause
        exit /b 1
    )
)

if "%~1"=="" (
    echo Usage: run_windows.bat ^<command^> [options]
    echo.
    python -m podcastgen --help
    echo.
    echo Example:
    echo   run_windows.bat generate --topic "The future of UPI in India" --lang en-IN --minutes 8 --out episode.wav
    pause
    exit /b 0
)

python -m podcastgen %*
set "RC=%errorlevel%"
echo.
if not "%RC%"=="0" echo [X] Command exited with code %RC%.
pause
exit /b %RC%
