# -*- coding: utf-8 -*-
"""简单 i18n：切换界面语言（English / Bahasa Melayu / 中文）。

用法：
    import i18n
    label = i18n.t("File")        # 按当前语言翻译；未翻译/缺 key 则返回原文
    i18n.set_lang("ms")           # 切换语言（保存到 QSettings，重启后生效）

菜单：菜单栏通过 UI 上的 "Language" 菜单切换；数据列头(TICKER/NAME…)保持英文。
"""
from PyQt6.QtCore import QSettings

_ORG = "StockScreenerPro"
_APP = "General"
_LANG_KEY = "app_lang"

SUPPORTED = {
    "en": "English",
    "ms": "Bahasa Melayu",
    "zh": "中文",
}

_KEY = "en"  # 模块内缓存，加速


# ── 翻译表（key = 英文原文）──────────────────────────────────────────────
STRINGS = {
    "ms": {
        # 菜单
        "File": "Fail",
        "Help": "Bantuan",
        "Language": "Bahasa",
        "About": "Perihal",
        "License Info": "Maklumat Lesen",
        "Refresh Data": "Muat Semula Data",
        "Export CSV...": "Eksport CSV...",
        "Quit": "Keluar",
        # 状态栏/通用
        "Ready": "Sedia",
        "Cancelled": "Dibatalkan",
        "Cancelling…": "Membatalkan…",
        "Run Screeners": "Jalankan Penapis",
        "Reset": "Set Semula",
        # 侧栏
        "Parameters": "Parameter",
        "Sector": "Sektor",
        "All Sectors": "Semua Sektor",
        "EMA Compression": "Mampatan EMA",
        "Volume Filters": "Penapis Volum",
        "KDJ Parameters": "Parameter KDJ",
        "Scoring System": "Sistem Pemarkahan",
        "Trend Periods": "Tempoh Trend",
        "Divergence %": "Sisihan %",
        "Min Bars": "Bar Minimum",
        "Daily Min Vol": "Vol Harian Min",
        "Hourly Min Vol": "Vol Jam Min",
        "Weekly Min Vol": "Vol Mingguan Min",
        "KDJ Daily Vol Min": "Vol Harian KDJ Min",
        "KDJ Vol Ratio": "Nisbah Vol KDJ",
        "Period (RSV)": "Tempoh (RSV)",
        "Signal Smooth": "Pelicinan Isyarat",
        "Div Lookback": "Pandang Balik Sisihan",
        "Trend Divergence %": "Sisihan Trend %",
        "Slope Bars": "Bar Cerun",
        "Vol Lookback": "Pandang Balik Vol",
        "Vol Threshold %": "Ambang Vol %",
        "Vol MA Bars": "Bar Purata Vol",
        "Vol MA Threshold": "Ambang Purata Vol",
        "Min Score": "Markah Minimum",
        "Top N Results": "Keputusan Teratas N",
        # Phase-1 / Ignition (new)
        "Ignition": "Pencetus",
        "Min Closing Strength": "Kekuatan Penutupan Min",
        "Min ADTV": "ADTV Minimum",
        "RS Rank": "Kedudukan RS",
        "RS Rank Chg": "Perubahan RS",
        "Target": "Sasaran",
        "Auto-refresh every 5 min": "Auto-muat semula setiap 5 minit",
        "Weekly KDJ alerts": "Amaran KDJ Mingguan",
        # 标签页
        "Top Movers": "Pergerakan Utama",
        "Daily EMA": "EMA Harian",
        "Hourly EMA": "EMA Jam",
        "Weekly EMA": "EMA Mingguan",
        "KDJ Divergence": "Sisihan KDJ",
        "Weekly KDJ": "KDJ Mingguan",
        "Daily KDJ": "KDJ Harian",
        "Scoring": "Pemarkahan",
        "New Picks": "Pilihan Baharu",
        # 空态
        "No results": "Tiada keputusan",
        "No movers yet": "Tiada pergerakan lagi",
        "No new picks yet": "Tiada pilihan baharu lagi",
        "Run Screeners from the sidebar to start, or adjust parameters and retry":
            "Jalankan Penapis dari bar sisi untuk mula, atau laraskan parameter dan cuba semula",
        "Stocks that pass the screeners for the first time appear here — the baseline is set on the first run after a data refresh":
            "Saham yang pertama kali lulus penapis muncul di sini — garis asas ditetapkan pada run pertama selepas muat semula data",
        "Run Screeners to load market data — today's top gainers, losers and actives appear here":
            "Jalankan Penapis untuk memuat data pasaran — pemenang, pecundang dan aktif teratas hari ini muncul di sini",
        "Search code / name / signal…": "Cari kod / nama / isyarat…",
        # 激活
        "Activate Stock Screener Pro": "Aktifkan Stock Screener Pro",
        "This software is license-protected. Enter your activation code to continue.":
            "Perisian ini dilindungi lesen. Masukkan kod pengaktifan anda untuk meneruskan.",
        "Machine code:": "Kod mesin:",
        "Copy": "Salin",
        "Activation code:": "Kod pengaktifan:",
        "Paste the activation code from your seller": "Tampal kod pengaktifan daripada penjual",
        "Exit": "Keluar",
        "Activate": "Aktifkan",
        "Please enter the activation code.": "Sila masukkan kod pengaktifan.",
        "Activated successfully": "Berjaya diaktifkan",
        "Activation failed: ": "Pengaktifan gagal: ",
        "Your trial has expired. Enter your lifetime code.":
            "Tempoh percubaan anda telah tamat. Sila masukkan kod seumur hidup anda.",
        "This software requires a valid activation code to run.\n\nPlease contact the seller to obtain one.":
            "Perisian ini memerlukan kod pengaktifan yang sah untuk dijalankan.\n\nSila hubungi penjual untuk mendapatkannya.",
        # 欢迎
        "Welcome to Stock Screener Pro": "Selamat Datang ke Stock Screener Pro",
        "Get Started": "Mula",
        "Don't show this again": "Jangan tunjuk lagi",
        "A multi-market screening terminal — here's how to get the most out of it:":
            "Terminal penapis pelbagai pasaran — begini cara memanfaatkannya sepenuhnya:",
        # 授权信息
        "Licensed to:": "Lesen kepada:",
        "Type:": "Jenis:",
    },
    "zh": {
        # 菜单
        "File": "文件",
        "Help": "帮助",
        "Language": "语言",
        "About": "关于",
        "License Info": "授权信息",
        "Refresh Data": "刷新数据",
        "Export CSV...": "导出CSV…",
        "Quit": "退出",
        # 状态栏/通用
        "Ready": "就绪",
        "Cancelled": "已取消",
        "Cancelling…": "取消中…",
        "Run Screeners": "运行筛选",
        "Reset": "重置",
        # 侧栏
        "Parameters": "参数",
        "Sector": "行业",
        "All Sectors": "全部行业",
        "EMA Compression": "EMA 压缩",
        "Volume Filters": "成交量过滤",
        "KDJ Parameters": "KDJ 参数",
        "Scoring System": "评分系统",
        "Trend Periods": "趋势周期",
        "Divergence %": "偏离 %",
        "Min Bars": "最少K线数",
        "Daily Min Vol": "日线最小成交量",
        "Hourly Min Vol": "小时线最小成交量",
        "Weekly Min Vol": "周线最小成交量",
        "KDJ Daily Vol Min": "KDJ 日线最小成交量",
        "KDJ Vol Ratio": "KDJ 量比",
        "Period (RSV)": "周期 (RSV)",
        "Signal Smooth": "信号平滑",
        "Div Lookback": "背离回看",
        "Trend Divergence %": "趋势偏离 %",
        "Slope Bars": "斜率K线数",
        "Vol Lookback": "成交量回看",
        "Vol Threshold %": "量能阈值 %",
        "Vol MA Bars": "成交量均线K线数",
        "Vol MA Threshold": "成交量均线阈值",
        "Min Score": "最低分",
        "Top N Results": "前 N 结果数",
        # Phase-1 / Ignition (new)
        "Ignition": "起爆点",
        "Min Closing Strength": "最低收盘强度",
        "Min ADTV": "最低成交额",
        "RS Rank": "RS 排名",
        "RS Rank Chg": "RS 排名变化",
        "Target": "目标位",
        "Auto-refresh every 5 min": "每 5 分钟自动刷新",
        "Weekly KDJ alerts": "周线 KDJ 提醒",
        # 标签页
        "Top Movers": "异动榜",
        "Daily EMA": "日线 EMA",
        "Hourly EMA": "小时 EMA",
        "Weekly EMA": "周线 EMA",
        "KDJ Divergence": "KDJ 背离",
        "Weekly KDJ": "周线 KDJ",
        "Daily KDJ": "日线 KDJ",
        "Scoring": "评分",
        "New Picks": "新发现",
        # 空态
        "No results": "无结果",
        "No movers yet": "暂无异动",
        "No new picks yet": "暂无新发现",
        "Run Screeners from the sidebar to start, or adjust parameters and retry":
            "从侧栏运行筛选开始，或调整参数后重试",
        "Stocks that pass the screeners for the first time appear here — the baseline is set on the first run after a data refresh":
            "首次通过筛选的股票会出现在这里——基线在数据刷新后的第一次运行时设定",
        "Run Screeners to load market data — today's top gainers, losers and actives appear here":
            "运行筛选以加载行情——今天的涨幅榜、跌幅榜与活跃股将显示在这里",
        "Search code / name / signal…": "搜索 代码 / 名称 / 信号…",
        # 激活
        "Activate Stock Screener Pro": "激活 Stock Screener Pro",
        "This software is license-protected. Enter your activation code to continue.":
            "本软件受许可证保护。请输入激活码以继续。",
        "Machine code:": "机器码：",
        "Copy": "复制",
        "Activation code:": "激活码：",
        "Paste the activation code from your seller": "粘贴卖家发来的激活码",
        "Exit": "退出程序",
        "Activate": "激 活",
        "Please enter the activation code.": "请输入激活码。",
        "Activated successfully": "激活成功",
        "Activation failed: ": "激活失败：",
        "Your trial has expired. Enter your lifetime code.":
            "试用已到期，请输入您的终生（永久）激活码。",
        "This software requires a valid activation code to run.\n\nPlease contact the seller to obtain one.":
            "本软件需要有效激活码才能运行。\n\n请联系卖家获取激活码。",
        # 欢迎
        "Welcome to Stock Screener Pro": "欢迎使用 Stock Screener Pro",
        "Get Started": "开始使用",
        "Don't show this again": "不再显示",
        "A multi-market screening terminal — here's how to get the most out of it:":
            "一个多市场筛选终端——以下是充分利用它的方法：",
        # 授权信息
        "Licensed to:": "授权给：",
        "Type:": "类型：",
    },
}


# ── 存取当前语言 ────────────────────────────────────────────────────────
def lang() -> str:
    return QSettings(_ORG, _APP).value(_LANG_KEY, "en")


def set_lang(code: str):
    if code in SUPPORTED:
        QSettings(_ORG, _APP).setValue(_LANG_KEY, code)


def current() -> str:
    l = lang()
    return l if l in SUPPORTED else "en"


def t(key: str) -> str:
    """按当前语言翻译 key（key = 英文原文）；缺翻译则返回原文。"""
    l = current()
    table = STRINGS.get(l, {})
    return table.get(key, key)
