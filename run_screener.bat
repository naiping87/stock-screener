@echo off
title Bursa Malaysia Stock Screener
echo ============================================
echo   Bursa Malaysia Stock Screener
echo   EMA Divergence + Bullish Alignment Filter
echo ============================================
echo.

REM Check Python installation
python --version >nul 2>&1
if errorlevel 1 (
    echo [ERROR] Python not found in PATH.
    echo.
    echo Please install Python 3.8+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo During installation, check "Add Python to PATH".
    echo.
    pause
    exit /b 1
)

echo Python found. Installing / verifying dependencies ...
python -m pip install -r "%~dp0requirements.txt" -q
if errorlevel 1 (
    echo [ERROR] Failed to install dependencies. Check your internet connection.
    pause
    exit /b 1
)

echo.
echo Running screener — processing ~845 Malaysian stocks.
echo This typically takes 3-5 minutes. Progress:
echo.

python "%~dp0screener.py"

echo.
echo ============================================
echo Results saved to: output\screener_results_*.csv
echo ============================================
pause
