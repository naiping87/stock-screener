# -*- coding: utf-8 -*-
"""Activation dialog — shown on first launch until a valid code is entered.

Usage (in main.py):
    dlg = ActivationDialog(lic)
    if dlg.exec() != QDialog.DialogCode.Accepted:
        sys.exit(0)          # user did not activate -> exit, do not enter main UI
    # reached here = activated
"""
from PyQt6.QtCore import Qt
from PyQt6.QtWidgets import (
    QApplication,
    QDialog,
    QHBoxLayout,
    QLabel,
    QLineEdit,
    QPushButton,
    QVBoxLayout,
)

import i18n
from .styles import ACCENT, ACCENT_HOVER, BG_SURFACE, BG_WINDOW, BORDER, GREEN, RED, TEXT, TEXT_SEC

from licensing.license_manager import LicenseManager


class ActivationDialog(QDialog):
    def __init__(self, license_manager: LicenseManager, parent=None):
        super().__init__(parent)
        self.lic = license_manager
        self.setWindowTitle(i18n.t("Activate Stock Screener Pro"))
        self.setModal(True)
        self.setFixedWidth(540)
        self.setStyleSheet(
            f"QDialog {{ background: {BG_WINDOW}; }}"
            f"QLabel {{ color: {TEXT}; background: transparent; }}"
        )

        layout = QVBoxLayout(self)
        layout.setContentsMargins(28, 24, 28, 20)
        layout.setSpacing(10)

        title = QLabel(i18n.t("Activate Stock Screener Pro"))
        title.setStyleSheet(f"color:{TEXT}; font-size:22px; font-weight:700;")
        layout.addWidget(title)

        _info = self.lic.get_license_info()
        _expired = bool(_info.get("expired"))
        _sub_text = (i18n.t("Your trial has expired. Enter your lifetime code.") if _expired
                     else i18n.t("This software is license-protected. Enter your activation code to continue."))
        sub = QLabel(_sub_text)
        sub.setStyleSheet(f"color:{TEXT_SEC}; font-size:13px;")
        sub.setWordWrap(True)
        layout.addWidget(sub)
        layout.addSpacing(6)

        # ---- Machine code (used for pre-binding flow) ----
        mach_card = QLabel()
        mach_card.setTextFormat(Qt.TextFormat.RichText)
        mach_card.setWordWrap(True)
        mach_card.setStyleSheet(
            f"background:{BG_SURFACE}; border:1px solid {BORDER}; border-radius:8px;"
            f" padding:10px 12px; font-size:12px;")
        layout.addWidget(mach_card)

        mach_row = QHBoxLayout()
        mach_lbl = QLabel(i18n.t("Machine code:"))
        mach_lbl.setStyleSheet(f"color:{TEXT_SEC};")
        mach_row.addWidget(mach_lbl)

        self.mach_edit = QLineEdit()
        self.mach_edit.setReadOnly(True)
        self.mach_edit.setStyleSheet(
            f"QLineEdit {{ background:{BG_SURFACE}; color:{TEXT}; border:1px solid {BORDER};"
            f" border-radius:6px; padding:6px 8px; font-family:Consolas,monospace; font-size:12px; }}")
        mach_row.addWidget(self.mach_edit, 1)

        copy_btn = QPushButton(i18n.t("Copy"))
        copy_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_SURFACE}; color:{TEXT}; border:1px solid {BORDER};"
            f" border-radius:6px; padding:6px 12px; }}"
            f"QPushButton:hover {{ background:{ACCENT_HOVER}; }}")
        copy_btn.clicked.connect(self._copy_machine_code)
        mach_row.addWidget(copy_btn)
        layout.addLayout(mach_row)

        if self.lic.bind_mode == "pre":
            card = ("<b>%s</b><br/><span style='color:%s'>%s</span>" % (
                i18n.t("Send the machine code above to the seller to get an activation code bound to this computer."),
                TEXT_SEC,
                i18n.t("The code only works on this computer and cannot be shared.")))
            mach_card.setText(card)
            self.mach_edit.setText(self.lic.get_machine_code())
        else:
            card = ("<span style='color:%s'>%s</span>" % (
                TEXT_SEC,
                i18n.t("This build is not pre-bound. The code binds to the current computer the first time it is activated.")))
            mach_card.setText(card)
            self.mach_edit.setText(i18n.t("(not required in this mode)"))

        layout.addSpacing(10)

        # ---- Activation code input ----
        code_lbl = QLabel(i18n.t("Activation code:"))
        code_lbl.setStyleSheet(f"color:{TEXT_SEC};")
        layout.addWidget(code_lbl)

        self.code_edit = QLineEdit()
        self.code_edit.setPlaceholderText(i18n.t("Paste the activation code from your seller"))
        self.code_edit.setStyleSheet(
            f"QLineEdit {{ background:{BG_SURFACE}; color:{TEXT}; border:1px solid {BORDER};"
            f" border-radius:6px; padding:10px 12px; font-size:13px; }}"
            f"QLineEdit:focus {{ border-color:{ACCENT}; }}")
        layout.addWidget(self.code_edit)

        self.status = QLabel("")
        self.status.setStyleSheet(f"color:{RED}; font-size:12px;")
        self.status.setWordWrap(True)
        layout.addWidget(self.status)

        layout.addStretch(1)

        # ---- Buttons ----
        btn_row = QHBoxLayout()
        btn_row.addStretch(1)

        quit_btn = QPushButton(i18n.t("Exit"))
        quit_btn.setStyleSheet(
            f"QPushButton {{ background:{BG_SURFACE}; color:{TEXT}; border:1px solid {BORDER};"
            f" border-radius:6px; padding:10px 20px; }}"
            f"QPushButton:hover {{ background:{ACCENT_HOVER}; }}")
        quit_btn.clicked.connect(self.reject)
        btn_row.addWidget(quit_btn)

        activate_btn = QPushButton(i18n.t("Activate"))
        activate_btn.setStyleSheet(
            f"QPushButton {{ background:{ACCENT}; color:#fff; border:none; border-radius:6px;"
            f" padding:10px 28px; font-size:14px; font-weight:600; }}"
            f"QPushButton:hover {{ background:{ACCENT_HOVER}; }}")
        activate_btn.clicked.connect(self._on_activate)
        btn_row.addWidget(activate_btn)

        layout.addLayout(btn_row)

    def _copy_machine_code(self):
        QApplication.clipboard().setText(self.mach_edit.text())
        self.status.setStyleSheet(f"color:{GREEN}; font-size:12px;")
        self.status.setText(i18n.t("Machine code copied. Send it to the seller to get an activation code."))

    def _on_activate(self):
        token = self.code_edit.text().strip()
        if not token:
            self.status.setStyleSheet(f"color:{RED}; font-size:12px;")
            self.status.setText(i18n.t("Please enter the activation code."))
            return
        ok, msg = self.lic.activate(token)
        if ok:
            self.status.setStyleSheet(f"color:{GREEN}; font-size:13px; font-weight:600;")
            self.status.setText(i18n.t("Activated successfully"))
            self.accept()
        else:
            self.status.setStyleSheet(f"color:{RED}; font-size:12px;")
            self.status.setText(i18n.t("Activation failed: ") + msg)
