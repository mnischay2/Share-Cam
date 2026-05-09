@echo off
REM install_windows.bat — ShareCam Windows Setup
REM Prerequisites: Python 3.11+, OBS Studio with VirtualCam plugin installed

echo.
echo ==========================================
echo   ShareCam - Windows Setup
echo ==========================================
echo.

REM Check Python
python --version >nul 2>&1 || (
    echo ERROR: Python not found. Install from https://python.org
    pause & exit /b 1
)

REM Create venv
echo [1/3] Creating virtual environment...
python -m venv .venv
call .venv\Scripts\activate.bat

REM Install deps
echo [2/3] Installing Python dependencies...
pip install --upgrade pip -q
pip install -r requirements.txt -q

echo [3/3] Done.
echo.
echo ==========================================
echo   IMPORTANT — Windows Virtual Camera
echo ==========================================
echo   You need OBS Studio with VirtualCam plugin:
echo   https://obsproject.com/
echo.
echo   pyvirtualcam will auto-detect OBS VirtualCam.
echo.
echo   To start ShareCam:
echo     .venv\Scripts\activate.bat
echo     python run.py
echo ==========================================
echo.
pause
