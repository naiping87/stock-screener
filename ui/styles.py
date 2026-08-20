"""TradingView-inspired dark theme — flat, dense, professional terminal look.

Palette mirrors TradingView's classic dark scheme:
  #131722 window / #1e222d panels / #2a2e39 raised & borders /
  #2962FF brand blue / #089981 up / #f23645 down.
"""

# ── Color palette ────────────────────────────────────────────────────────
BG_WINDOW = "#131722"
BG_SURFACE = "#1e222d"
BG_CARD = "#1e222d"
BG_INPUT = "#2a2e39"
BG_HOVER = "#2a2e39"
BORDER = "#2a2e39"
BORDER_FOCUS = "#2962FF"
TEXT = "#d1d4dc"
TEXT_SEC = "#787b86"
TEXT_DIM = "#5d606b"
GREEN = "#089981"
RED = "#f23645"
ORANGE = "#f7c600"
BLUE = "#2962FF"
PURPLE = "#b18cff"
ACCENT = "#2962FF"
ACCENT_HOVER = "#3b7aff"

SIDEBAR_BG = "#131722"
SIDEBAR_SECTION = "#1e222d"

# ── Stylesheet ───────────────────────────────────────────────────────────
STYLESHEET = f"""
* {{
    font-family: "SF Pro Display", "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}

QMainWindow {{
    background: {BG_WINDOW};
}}

/* ── Menu bar ──────────────────────────────────────────────────────── */
QMenuBar {{
    background: rgba(30,34,45,0.95);
    border-bottom: 1px solid rgba(255,255,255,0.06);
    padding: 4px 16px;
    font-size: 13px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 5px 14px;
    border-radius: 6px;
    margin: 2px 1px;
}}
QMenuBar::item:selected {{
    background: rgba(255,255,255,0.06);
}}
QMenu {{
    background: rgba(30,34,45,0.98);
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 6px 32px 6px 16px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background: {ACCENT};
    color: #fff;
}}
QMenu::separator {{
    height: 1px;
    background: rgba(255,255,255,0.08);
    margin: 4px 8px;
}}

/* ── Tab widget ─────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: none;
    background: {BG_WINDOW};
    padding: 6px 4px 4px 4px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_SEC};
    padding: 8px 20px;
    margin-right: 4px;
    border-bottom: 2px solid transparent;
    font-size: 13px;
    font-weight: 500;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
}}

/* ── Table view ─────────────────────────────────────────────────────── */
QTableView {{
    background: {BG_SURFACE};
    alternate-background-color: #181c26;
    border: 1px solid rgba(255,255,255,0.06);
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: rgba(41, 98, 255, 0.25);
    selection-color: {TEXT};
    outline: none;
}}
QHeaderView::section {{
    background: {BG_CARD};
    color: {TEXT_SEC};
    padding: 10px 14px;
    border: none;
    border-bottom: 1px solid rgba(255,255,255,0.06);
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
QHeaderView::section:hover {{
    color: {TEXT};
    background: rgba(255,255,255,0.04);
}}

/* ── Scrollbar ──────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(255,255,255,0.15);
    border-radius: 3px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(255,255,255,0.25);
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Group box ──────────────────────────────────────────────────────── */
QGroupBox {{
    font-weight: 600;
    color: {TEXT};
    border: none;
    background: {SIDEBAR_SECTION};
    border-radius: 10px;
    margin-top: 10px;
    padding: 20px 16px 14px 16px;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 16px;
    padding: 0 8px;
    color: {TEXT};
    font-size: 13px;
    font-weight: 600;
}}

/* ── Buttons ────────────────────────────────────────────────────────── */
QPushButton {{
    background: {BG_SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 20px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {BG_HOVER};
}}
QPushButton:pressed {{
    background: rgba(255,255,255,0.08);
}}
QPushButton#runBtn {{
    background: {ACCENT};
    color: #fff;
    border: none;
    font-weight: 600;
    font-size: 15px;
    padding: 14px 32px;
    border-radius: 8px;
    letter-spacing: 0.3px;
}}
QPushButton#runBtn:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton#runBtn:pressed {{
    background: #1e53e5;
}}

/* ── Line edit (search box etc.) ───────────────────────────────────── */
QLineEdit {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 13px;
    selection-background-color: {ACCENT};
    selection-color: #fff;
}}
QLineEdit:hover {{
    border-color: rgba(255,255,255,0.14);
}}
QLineEdit:focus {{
    border-color: {ACCENT};
    background: {BG_INPUT};
}}

/* ── Combo box ──────────────────────────────────────────────────────── */
QComboBox {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 16px;
    font-size: 14px;
    min-width: 100px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 30px;
}}
QComboBox QAbstractItemView {{
    background: {BG_SURFACE};
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 6px;
    padding: 6px;
    selection-background-color: {ACCENT};
    selection-color: #fff;
    outline: none;
}}

/* ── Slider ─────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: rgba(255,255,255,0.15);
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
    border: 2px solid {BG_WINDOW};
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_HOVER};
    transform: scale(1.1);
}}

/* ── Spin box ───────────────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px 30px 4px 10px;
    font-size: 13px;
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {ACCENT};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
    background: {BG_INPUT};
}}
/* Qt6/Windows 11 默认把 up/down 按钮左右并排,箭头小且难分辨;
   这里强制上下堆叠并画清晰三角箭头。 */
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    subcontrol-origin: border;
    subcontrol-position: top right;
    width: 28px;
    border-left: 1px solid {BORDER};
    border-bottom: 1px solid {BORDER};
    border-top-right-radius: 6px;
    background: {BG_INPUT};
}}
QSpinBox::up-button:hover, QDoubleSpinBox::up-button:hover {{
    background: {BG_HOVER};
}}
QSpinBox::up-button:pressed, QDoubleSpinBox::up-button:pressed {{
    background: rgba(41,98,255,0.20);
}}
QSpinBox::up-arrow, QDoubleSpinBox::up-arrow {{
    width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-bottom: 6px solid {ACCENT};
    image: none;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    subcontrol-origin: border;
    subcontrol-position: bottom right;
    width: 28px;
    border-left: 1px solid {BORDER};
    border-bottom-right-radius: 6px;
    background: {BG_INPUT};
}}
QSpinBox::down-button:hover, QDoubleSpinBox::down-button:hover {{
    background: {BG_HOVER};
}}
QSpinBox::down-button:pressed, QDoubleSpinBox::down-button:pressed {{
    background: rgba(41,98,255,0.20);
}}
QSpinBox::down-arrow, QDoubleSpinBox::down-arrow {{
    width: 0; height: 0;
    border-left: 5px solid transparent;
    border-right: 5px solid transparent;
    border-top: 6px solid {ACCENT};
    image: none;
}}

/* ── Check box ──────────────────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT};
    spacing: 8px;
    font-size: 13px;
}}
QCheckBox::indicator {{
    width: 20px;
    height: 20px;
    border: 2px solid {BORDER};
    border-radius: 5px;
    background: {BG_INPUT};
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}
QCheckBox::indicator:hover {{
    border-color: {ACCENT};
}}

/* ── Progress bar ───────────────────────────────────────────────────── */
QProgressBar {{
    background: rgba(255,255,255,0.08);
    border: none;
    border-radius: 3px;
    height: 4px;
    font-size: 0px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 2px;
}}

/* ── Splitter ───────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: rgba(255,255,255,0.08);
    width: 1px;
}}

/* ── Status bar ─────────────────────────────────────────────────────── */
QStatusBar {{
    background: rgba(30,34,45,0.95);
    color: {TEXT_SEC};
    border-top: 1px solid rgba(255,255,255,0.06);
    font-size: 12px;
    padding: 4px 16px;
}}

/* ── Scroll area ────────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}

/* ── Label section titles ───────────────────────────────────────────── */
QLabel#sectionTitle {{
    color: {TEXT_SEC};
    font-size: 11px;
    font-weight: 600;
    letter-spacing: 0.5px;
    text-transform: uppercase;
    padding: 8px 0 4px 0;
}}

/* ── Empty state (results panel) ────────────────────────────────────── */
QLabel#emptyStateIcon {{
    color: {TEXT_DIM};
    font-size: 36px;
}}
QLabel#emptyStateTitle {{
    color: {TEXT_SEC};
    font-size: 14px;
    font-weight: 600;
}}
QLabel#emptyStateHint {{
    color: {TEXT_DIM};
    font-size: 12px;
}}

/* ── Tool tip ───────────────────────────────────────────────────────── */
QToolTip {{
    background: rgba(30,34,45,0.98);
    color: {TEXT};
    border: 1px solid rgba(255,255,255,0.1);
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 12px;
}}
"""

# Legacy aliases for backward compatibility
BG_DARK = BG_WINDOW
TEXT_PRIMARY = TEXT
TEXT_SECONDARY = TEXT_SEC
