@echo off
echo === Stock Screener Pro — Build Installer ===
echo.
echo Step 1: Installing PyInstaller...
python -m pip install pyinstaller -q

echo Step 2: Building exe...
python -m PyInstaller --onefile --windowed ^
    --name="StockScreenerPro" ^
    --add-data="markets;markets" ^
    --add-data="tickers;tickers" ^
    --add-data="tickers.csv;." ^
    --add-data="ui;ui" ^
    --add-data="workers;workers" ^
    --add-data="resources;resources" ^
    --add-data="licensing;licensing" ^
    --collect-all=cryptography ^
    --collect-all=akshare ^
    --collect-all=pyqtgraph ^
    --hidden-import="PyQt6" ^
    --hidden-import="pandas" ^
    --hidden-import="numpy" ^
    --hidden-import="requests" ^
    --hidden-import="markets.bursa" ^
    --hidden-import="markets.us" ^
    --hidden-import="markets.shanghai" ^
    --hidden-import="licensing.license_manager" ^
    --icon="resources/icon.ico" ^
    main.py

echo.
echo === Build complete ===
echo exe is in dist\StockScreenerPro.exe
pause
