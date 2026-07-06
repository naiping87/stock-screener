"""Bloomberg Terminal inspired dark theme — QSS stylesheet + color constants."""

# ── Color palette ────────────────────────────────────────────────────────
BG_DARK = "#0d1117"
BG_CARD = "#161b22"
BG_SIDEBAR = "#0d1117"
BG_TABLE = "#161b22"
BORDER = "#30363d"
TEXT_PRIMARY = "#e6edf3"
TEXT_SECONDARY = "#8b949e"
TEXT_DIM = "#484f58"
GREEN = "#3fb950"
RED = "#f85149"
ORANGE = "#d2991d"
BLUE = "#58a6ff"
PURPLE = "#bc8cff"
ACCENT = "#1f6feb"
HOVER = "rgba(177, 186, 196, 0.08)"
SELECTION = "rgba(31, 111, 235, 0.3)"

# ── Stylesheet ───────────────────────────────────────────────────────────
STYLESHEET = f"""
QMainWindow {{
    background: {BG_DARK};
    color: {TEXT_PRIMARY};
}}

QWidget {{
    font-family: "Segoe UI", "微软雅黑", sans-serif;
    font-size: 13px;
    color: {TEXT_PRIMARY};
}}

/* ── Menu bar ──────────────────────────────────────────────────────── */
QMenuBar {{
    background: {BG_CARD};
    border-bottom: 1px solid {BORDER};
    padding: 2px 8px;
}}
QMenuBar::item {{
    background: transparent;
    padding: 6px 12px;
    border-radius: 4px;
}}
QMenuBar::item:selected {{
    background: {HOVER};
}}
QMenu {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 4px;
}}
QMenu::item {{
    padding: 6px 32px 6px 16px;
    border-radius: 4px;
}}
QMenu::item:selected {{
    background: {HOVER};
}}
QMenu::separator {{
    height: 1px;
    background: {BORDER};
    margin: 4px 8px;
}}

/* ── Tab widget ─────────────────────────────────────────────────────── */
QTabWidget::pane {{
    border: 1px solid {BORDER};
    background: {BG_DARK};
    border-radius: 6px;
}}
QTabBar::tab {{
    background: {BG_CARD};
    color: {TEXT_SECONDARY};
    padding: 7px 16px;
    margin-right: 2px;
    border-top-left-radius: 6px;
    border-top-right-radius: 6px;
    border: 1px solid transparent;
    border-bottom: none;
}}
QTabBar::tab:selected {{
    background: {BG_DARK};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-bottom: 2px solid {ACCENT};
}}
QTabBar::tab:hover:!selected {{
    background: {HOVER};
    color: {TEXT_PRIMARY};
}}

/* ── Table view ─────────────────────────────────────────────────────── */
QTableView {{
    background: {BG_TABLE};
    alternate-background-color: {BG_DARK};
    gridline-color: rgba(48, 54, 61, 0.3);
    border: 1px solid {BORDER};
    border-radius: 6px;
    selection-background-color: {SELECTION};
    selection-color: {TEXT_PRIMARY};
    outline: none;
}}
QHeaderView::section {{
    background: {BG_CARD};
    color: {TEXT_SECONDARY};
    padding: 6px 8px;
    border: none;
    border-bottom: 2px solid {BORDER};
    font-weight: 600;
    font-size: 12px;
}}
QHeaderView::section:hover {{
    color: {TEXT_PRIMARY};
    background: {HOVER};
}}
QTableView::item {{
    padding: 4px 8px;
    border: none;
}}

/* ── Scrollbar ──────────────────────────────────────────────────────── */
QScrollBar:vertical {{
    background: {BG_DARK};
    width: 8px;
    margin: 0;
}}
QScrollBar::handle:vertical {{
    background: {BORDER};
    border-radius: 4px;
    min-height: 30px;
}}
QScrollBar::handle:vertical:hover {{
    background: {TEXT_DIM};
}}
QScrollBar::add-line:vertical,
QScrollBar::sub-line:vertical {{
    height: 0;
}}

/* ── Group box ──────────────────────────────────────────────────────── */
QGroupBox {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
    margin-top: 16px;
    padding: 20px 12px 12px 12px;
    font-weight: 600;
    color: {TEXT_PRIMARY};
}}
QGroupBox::title {{
    subcontrol-origin: margin;
    left: 12px;
    padding: 0 6px;
    color: {BLUE};
}}

/* ── Buttons ────────────────────────────────────────────────────────── */
QPushButton {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 7px 16px;
    font-weight: 500;
}}
QPushButton:hover {{
    background: {HOVER};
    border-color: {ACCENT};
}}
QPushButton:pressed {{
    background: {SELECTION};
}}
QPushButton#runBtn {{
    background: {GREEN};
    color: #000;
    border: none;
    font-weight: 700;
    font-size: 14px;
    padding: 10px 24px;
}}
QPushButton#runBtn:hover {{
    background: #2ea043;
}}
QPushButton#runBtn:pressed {{
    background: #238636;
}}

/* ── Combo box ──────────────────────────────────────────────────────── */
QComboBox {{
    background: {BG_DARK};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 6px 12px;
    min-width: 120px;
}}
QComboBox:hover {{
    border-color: {ACCENT};
}}
QComboBox::drop-down {{
    border: none;
    padding-right: 8px;
}}
QComboBox QAbstractItemView {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 4px;
    selection-background-color: {HOVER};
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
    background: {BG_DARK};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 6px;
    padding: 5px 8px;
}}
QSpinBox:hover, QDoubleSpinBox:hover {{
    border-color: {ACCENT};
}}

/* ── Check box ──────────────────────────────────────────────────────── */
QCheckBox {{
    color: {TEXT_PRIMARY};
    spacing: 8px;
}}
QCheckBox::indicator {{
    width: 16px;
    height: 16px;
    border: 2px solid {BORDER};
    border-radius: 3px;
    background: transparent;
}}
QCheckBox::indicator:checked {{
    background: {ACCENT};
    border-color: {ACCENT};
}}

/* ── Label ──────────────────────────────────────────────────────────── */
QLabel#sectionTitle {{
    color: {BLUE};
    font-weight: 700;
    font-size: 14px;
    padding: 4px 0;
}}

/* ── Progress bar ───────────────────────────────────────────────────── */
QProgressBar {{
    background: {BG_DARK};
    border: 1px solid {BORDER};
    border-radius: 4px;
    height: 8px;
    text-align: center;
}}
QProgressBar::chunk {{
    background: {ACCENT};
    border-radius: 3px;
}}
QProgressDialog {{
    background: {BG_CARD};
    border: 1px solid {BORDER};
    border-radius: 8px;
}}

/* ── Splitter ───────────────────────────────────────────────────────── */
QSplitter::handle {{
    background: {BORDER};
    width: 1px;
}}
QSplitter::handle:hover {{
    background: {ACCENT};
}}

/* ── Status bar ─────────────────────────────────────────────────────── */
QStatusBar {{
    background: {BG_CARD};
    color: {TEXT_SECONDARY};
    border-top: 1px solid {BORDER};
    font-size: 12px;
    padding: 2px 8px;
}}

/* ── Tool tip ───────────────────────────────────────────────────────── */
QToolTip {{
    background: {BG_CARD};
    color: {TEXT_PRIMARY};
    border: 1px solid {BORDER};
    border-radius: 4px;
    padding: 4px 8px;
}}
"""
