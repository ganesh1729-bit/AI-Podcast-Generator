@echo off
REM ============================================================
REM  AI Podcast Generator - Windows setup (one time)
REM  Double-click this file, or run it from a Command Prompt.
REM ============================================================
setlocal
cd /d "%~dp0"

echo ============================================================
echo   AI Podcast Generator - Windows setup
echo ============================================================
echo.

set "PY="
where py >nul 2>nul && set "PY=py -3"
if defined PY goto :havepython
where python >nul 2>nul && set "PY=python"
if defined PY goto :havepython

echo [X] Python was not found on your PATH.
echo.
echo   Install Python 3.10 or newer from:
echo     https://www.python.org/downloads/windows/
echo.
echo   IMPORTANT: on the first installer screen, tick
echo     [x] Add python.exe to PATH
echo   ...then CLOSE this window and run setup_windows.bat again.
echo.
echo   (If you already installed Python but still see this, open
echo    Settings ^> Apps ^> Advanced app settings ^> App execution aliases
echo    and turn OFF the "python.exe" / "python3.exe" entries.)
echo.
pause
exit /b 1

:havepython
echo Using interpreter: %PY%
echo.

echo [1/3] Creating virtual environment (.venv) ...
%PY% -m venv .venv
if errorlevel 1 goto :fail

call ".venv\Scripts\activate.bat"

echo [2/3] Installing dependencies ...
python -m pip install --upgrade pip >nul
pip install -r requirements.txt
if errorlevel 1 goto :fail

echo [3/3] Preparing .env ...
if not exist .env (
    copy .env.example .env >nul
    echo     Created .env
) else (
    echo     .env already exists - leaving it alone
)

echo.
echo ============================================================
echo   Setup complete.
echo.
echo   Next:
echo     1. Open the file  .env  (in Notepad) and set
echo          SARVAM_API_KEY=your-key-here
echo     2. Then run:  run_windows.bat "Your episode topic"
echo ============================================================
pause
exit /b 0

:fail
echo.
echo [X] Setup failed. Scroll up to read the error.
pause
exit /b 1
