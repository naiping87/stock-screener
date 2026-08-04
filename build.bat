@echo off
echo === Stock Screener Pro — Build Installer ===
echo.
echo Step 1: Installing PyInstaller...
pip install pyinstaller -q

echo Step 2: Building exe...
pyinstaller --onefile --windowed ^
    --name="StockScreenerPro" ^
    --add-data="markets;markets" ^
    --add-data="tickers;tickers" ^
    --add-data="tickers.csv;." ^
    --add-data="ui;ui" ^
    --add-data="workers;workers" ^
    --hidden-import="PyQt6" ^
    --hidden-import="pandas" ^
    --hidden-import="numpy" ^
    --hidden-import="requests" ^
    --hidden-import="akshare" ^
    --hidden-import="markets.bursa" ^
    --hidden-import="markets.us" ^
    --hidden-import="markets.shanghai" ^
    --icon="resources/icon.ico" ^
    main.py

echo.
echo === Build complete ===
echo exe is in dist\StockScreenerPro.exe
pause
