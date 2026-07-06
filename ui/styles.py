"""Professional dark theme — Apple/ProTool inspired."""

# ── Color palette ────────────────────────────────────────────────────────
BG_WINDOW = "#0a0e14"
BG_SURFACE = "#12171d"
BG_CARD = "#181e26"
BG_INPUT = "#1a2029"
BG_HOVER = "#1e2732"
BORDER = "#252e3b"
BORDER_FOCUS = "#3b82f6"
TEXT = "#e6edf3"
TEXT_SEC = "#8b949e"
TEXT_DIM = "#484f58"
GREEN = "#26a641"
RED = "#e5534b"
ORANGE = "#d2991d"
BLUE = "#58a6ff"
PURPLE = "#bc8cff"
ACCENT = "#3b82f6"
ACCENT_HOVER = "#2563eb"

# ── Stylesheet ───────────────────────────────────────────────────────────
STYLESHEET = f"""
* {{
    font-family: "Segoe UI", "Microsoft YaHei UI", sans-serif;
    font-size: 13px;
    color: {TEXT};
}}

QMainWindow {{
    background: {BG_WINDOW};
}}

/* ── Menu bar ──────────────────────────────────────────────────────── */
QMenuBar {{
    background: {BG_SURFACE};
    border-bottom: 1px solid {BORDER};
    padding: 2px 10px;
    font-size: 13px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 5px;
    margin: 2px 1px;
}}
QMenuBar::item:selected {{
    background: rgba(59, 130, 246, 0.15);
}}
QMenu {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    padding: 6px;
}}
QMenu::item {{
    padding: 7px 36px 7px 18px;
    border-radius: 5px;
}}
QMenu::item:selected {{
    background: rgba(59, 130, 246, 0.15);
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 5px 10px;
}}

/* ── Tab widget ─────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: none;
    background: {BG_WINDOW};
    padding: 4px 2px 2px 2px;
}}
QTabBar::tab {{
    background: transparent;
    color: {TEXT_SEC};
    padding: 8px 18px;
    margin-right: 2px;
    border-bottom: 2px solid transparent;
    font-size: 13px;
}}
QTabBar::tab:selected {{
    color: {TEXT};
    border-bottom: 2px solid {ACCENT};
    font-weight: 600;
}}
QTabBar::tab:hover:!selected {{
    color: {TEXT};
    background: rgba(255,255,255,0.03);
}}

/* ── Table view ─────────────────────────────────────────────────────── */
QTableView {{
    background: {BG_SURFACE};
    alternate-background-color: rgba(255,255,255,0.015);
    border: 1px solid {BORDER};
    border-radius: 8px;
    gridline-color: transparent;
    selection-background-color: rgba(59, 130, 246, 0.25);
    selection-color: {TEXT};
    outline: none;
}}
QHeaderView::section {{
    background: {BG_CARD};
    color: {TEXT_SEC};
    padding: 8px 10px;
    border: none;
    border-bottom: 2px solid {BORDER};
    font-weight: 600;
    font-size: 12px;
    letter-spacing: 0.3px;
}}
QHeaderView::section:hover {{
    color: {TEXT};
    background: {BG_HOVER};
}}

/* ── Scrollbar ──────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: transparent;
    width: 6px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 3px;
    min-height: 36px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_DIM};
}}
QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {{
    height: 0;
}}
QScrollBar:horizontal {{
    height: 6px;
    background: transparent;
}}
QScrollBar::handle:horizontal {{
    background: {BORDER};
    border-radius: 3px;
}}

/* ── Group box ──────────────────────────────────────────────────────── */
QGroupBox {{
    font-weight: 600;
    color: {TEXT_SEC};
    border: 1px solid {BORDER};
    border-radius: 10px;
    margin-top: 12px;
    padding: 18px 10px 10px 10px;
    font-size: 12px;
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 14px;
    padding: 0 8px;
    color: {BLUE};
    font-size: 12px;
}}

/* ── Buttons ────────────────────────────────────────────────────────── */
QPushButton {{
    background: {BG_CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 8px 18px;
    font-weight: 500;
    font-size: 13px;
}}
QPushButton:hover {{
    background: {BG_HOVER};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: rgba(59, 130, 246, 0.15);
}}
QPushButton#runBtn {{
    background: {ACCENT};
    color: #fff;
    border: none;
    font-weight: 700;
    font-size: 14px;
    padding: 12px 28px;
    border-radius: 8px;
}}
QPushButton#runBtn:hover {{
    background: {ACCENT_HOVER};
}}
QPushButton#runBtn:pressed {{
    background: #1d4ed8;
}}

/* ── Combo box ──────────────────────────────────────────────────────── */
QComboBox {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 7px;
    padding: 7px 14px;
    font-size: 13px;
    min-width: 100px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    width: 28px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
    selection-background-color: rgba(59, 130, 246, 0.15);
    outline: none;
}}

/* ── Slider ─────────────────────────────────────────────────────────── */
QSlider::groove:horizontal {{
    background: {BORDER};
    height: 4px;
    border-radius: 2px;
}}
QSlider::handle:horizontal {{
    background: {ACCENT};
    width: 14px;
    height: 14px;
    margin: -5px 0;
    border-radius: 7px;
}}
QSlider::handle:horizontal:hover {{
    background: {BLUE};
}}

/* ── Spin box ───────────────────────────────────────────────────────── */
QSpinBox, QDoubleSpinBox {{
    background: {BG_INPUT};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 10px;
    font-size: 13px;
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {ACCENT};
}}
QSpinBox::up-button, QDoubleSpinBox::up-button {{
    border-left: 1px solid {BORDER};
    width: 20px;
    border-top-right-radius: 6px;
    border-bottom-right-radius: 6px;
}}
QSpinBox::down-button, QDoubleSpinBox::down-button {{
    border-left: 1px solid {BORDER};
    width: 20px;
    border-bottom-left-radius: 6px;
    border-top-left-radius: 6px;
}}

/* ── Check box ──────────────────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT};
    spacing: 10px;
}}
QCheckBox::indicator {{
    width: 18px;
    height: 18px;
    border: 2px solid {BORDER};
    border-radius: 4px;
    background: transparent;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Progress bar ───────────────────────────────────────────────────── */
QProgressBar {{
    background: {BG_INPUT};
    border: 1px solid {BORDER};
    border-radius: 4px;
    height: 6px;
    font-size: 0px;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}

/* ── Splitter ───────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {BORDER};
    width: 1px;
}}

/* ── Status bar ─────────────────────────────────────────────────────── */
QStatusBar {{
    background: {BG_SURFACE};
    color: {TEXT_SEC};
    border-top: 1px solid {BORDER};
    font-size: 12px;
    padding: 3px 12px;
}}

/* ── Scroll area ────────────────────────────────────────────────────── */
QScrollArea {{
    border: none;
    background: transparent;
}}

/* ── Tool tip ───────────────────────────────────────────────────────── */
QToolTip {{
    background: {BG_CARD};
    color: {TEXT};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 8px 12px;
    font-size: 12px;
}}
"""

# Legacy aliases for backward compatibility
BG_DARK = BG_WINDOW
TEXT_PRIMARY = TEXT
TEXT_SECONDARY = TEXT_SEC
