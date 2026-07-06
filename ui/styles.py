"""Apple-inspired light-dark hybrid theme — clean, minimal, professional."""

# ── Color palette ────────────────────────────────────────────────────────
BG_WINDOW = "#f5f5f7"
BG_SURFACE = "#ffffff"
BG_CARD = "#fafafa"
BG_INPUT = "#f0f0f2"
BG_HOVER = "#e8e8ed"
BORDER = "#d2d2d7"
BORDER_FOCUS = "#0071e3"
TEXT = "#1d1d1f"
TEXT_SEC = "#6e6e73"
TEXT_DIM = "#aeaeb2"
GREEN = "#34c759"
RED = "#ff3b30"
ORANGE = "#ff9500"
BLUE = "#0071e3"
PURPLE = "#af52de"
ACCENT = "#0071e3"
ACCENT_HOVER = "#0077ed"

SIDEBAR_BG = "#f0f0f2"
SIDEBAR_SECTION = "#fafafa"

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
    background: rgba(255,255,255,0.85);
    border-bottom: 1px solid rgba(0,0,0,0.08);
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
    background: rgba(0,0,0,0.06);
}}
QMenu {{
    background: rgba(255,255,255,0.95);
    border: 1px solid rgba(0,0,0,0.1);
    border-radius: 10px;
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
    background: rgba(0,0,0,0.08);
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
    alternate-background-color: #f9f9fb;
    border: 1px solid rgba(0,0,0,0.06);
    border-radius: 10px;
    gridline-color: transparent;
    selection-background-color: rgba(0, 113, 227, 0.12);
    selection-color: {TEXT};
    outline: none;
}}
QHeaderView::section {{
    background: {BG_CARD};
    color: {TEXT_SEC};
    padding: 10px 14px;
    border: none;
    border-bottom: 1px solid rgba(0,0,0,0.06);
    font-weight: 600;
    font-size: 11px;
    letter-spacing: 0.5px;
    text-transform: uppercase;
}}
QHeaderView::section:hover {{
    color: {TEXT};
    background: rgba(0,0,0,0.03);
}}

/* ── Scrollbar ──────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: rgba(0,0,0,0.15);
    border-radius: 3px;
    min-height: 40px;
}}
QScrollBar::handle:vertical:hover {{
    background: rgba(0,0,0,0.25);
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
    border-radius: 12px;
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
    border-radius: 8px;
    padding: 8px 20px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {BG_HOVER};
}}
QPushButton:pressed {{
    background: rgba(0,0,0,0.08);
}}
QPushButton#runBtn {{
    background: {ACCENT};
    color: #fff;
    border: none;
    font-weight: 600;
    font-size: 15px;
    padding: 14px 32px;
    border-radius: 12px;
    letter-spacing: 0.3px;
}}
QPushButton#runBtn:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton#runBtn:pressed {{
    background: #0062cc;
}}

/* ── Combo box ──────────────────────────────────────────────────────── */
QComboBox {{
    background: {BG_SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
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
    border: 1px solid rgba(0,0,0,0.1);
    border-radius: 8px;
    padding: 6px;
    selection-background-color: {ACCENT};
    selection-color: #fff;
    outline: none;
}}

/* ── Slider ─────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: rgba(0,0,0,0.1);
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 18px;
    height: 18px;
    margin: -7px 0;
    border-radius: 9px;
    border: 2px solid #fff;
}}
QSlider::handle:horizontal:hover {{
    background: {ACCENT_HOVER};
    transform: scale(1.1);
}}

/* ── Spin box ───────────────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background: {BG_SURFACE};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 7px 12px;
    font-size: 13px;
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {ACCENT};
}}
QSpinBox:focus, QDoubleSpinBox:focus {{
    border-color: {ACCENT};
    background: #fff;
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
    background: {BG_SURFACE};
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
    background: rgba(0,0,0,0.06);
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
    background: rgba(0,0,0,0.06);
    width: 1px;
}}

/* ── Status bar ─────────────────────────────────────────────────────── */
QStatusBar {{
    background: rgba(255,255,255,0.85);
    color: {TEXT_SEC};
    border-top: 1px solid rgba(0,0,0,0.06);
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

/* ── Tool tip ───────────────────────────────────────────────────────── */
QToolTip {{
    background: rgba(30,30,32,0.95);
    color: #fff;
    border: none;
    border-radius: 6px;
    padding: 8px 14px;
    font-size: 12px;
}}
"""

# Legacy aliases for backward compatibility
BG_DARK = BG_WINDOW
TEXT_PRIMARY = TEXT
TEXT_SECONDARY = TEXT_SEC
