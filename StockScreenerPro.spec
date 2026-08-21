# -*- mode: python ; coding: utf-8 -*-


a = Analysis(
    ['main.py'],
    pathex=[],
    binaries=[],
    datas=[('markets', 'markets'), ('tickers', 'tickers'), ('tickers.csv', '.'), ('ui', 'ui'), ('workers', 'workers'), ('resources', 'resources'), ('tools', 'tools')],
    hiddenimports=['PyQt6', 'pandas', 'numpy', 'requests', 'pyqtgraph', 'akshare', 'markets.bursa', 'markets.us', 'markets.shanghai'],
    hookspath=[],
    hooksconfig={},
    runtime_hooks=[],
    excludes=[],
    noarchive=False,
    optimize=0,
)
pyz = PYZ(a.pure)

exe = EXE(
    pyz,
    a.scripts,
    a.binaries,
    a.datas,
    [],
    name='StockScreenerPro',
    debug=False,
    bootloader_ignore_signals=False,
    strip=False,
    upx=True,
    upx_exclude=[],
    runtime_tmpdir=None,
    console=False,
    disable_windowed_traceback=False,
    argv_emulation=False,
    target_arch=None,
    codesign_identity=None,
    entitlements_file=None,
    icon=['resources\\icon.ico'],
)
