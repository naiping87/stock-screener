"""TableView — QTableView with sorting, column sizing, and right-click export."""

import csv
import os
from PyQt6.QtCore import Qt, pyqtSignal
from PyQt6.QtGui import QAction, QKeySequence
from PyQt6.QtWidgets import (
    QTableView, QHeaderView, QMenu, QFileDialog, QMessageBox,
)


class TableView(QTableView):
    """Enhanced QTableView with sort-on-click, auto-resize, and export."""

    export_requested = pyqtSignal(str)  # emits export file path

    def __init__(self):
        super().__init__()
        self.setSortingEnabled(True)
        self.setShowGrid(True)
        self.setSelectionBehavior(QTableView.SelectionBehavior.SelectRows)
        self.setSelectionMode(QTableView.SelectionMode.ExtendedSelection)
        self.setContextMenuPolicy(Qt.ContextMenuPolicy.CustomContextMenu)
        self.customContextMenuRequested.connect(self._on_context_menu)

        # Header
        h_header = self.horizontalHeader()
        h_header.setSectionsClickable(True)
        h_header.setSortIndicatorShown(True)
        h_header.setStretchLastSection(True)
        h_header.setSectionResizeMode(QHeaderView.ResizeMode.Interactive)

        v_header = self.verticalHeader()
        v_header.setDefaultSectionSize(28)
        v_header.setVisible(False)

    def setModel(self, model):
        super().setModel(model)
        # Auto-resize columns to content
        self.resizeColumnsToContents()
        # Set minimum column widths
        for i in range(model.columnCount()):
            w = self.columnWidth(i)
            self.setColumnWidth(i, max(w, 60))

    def _on_context_menu(self, pos):
        """Right-click menu: copy, export CSV."""
        menu = QMenu(self)

        copy_action = QAction("&Copy Selected Rows", self)
        copy_action.setShortcut(QKeySequence("Ctrl+C"))
        copy_action.triggered.connect(self._copy_selected)
        menu.addAction(copy_action)

        export_action = QAction("&Export All to CSV...", self)
        export_action.setShortcut(QKeySequence("Ctrl+E"))
        export_action.triggered.connect(self._export_csv)
        menu.addAction(export_action)

        menu.exec(self.viewport().mapToGlobal(pos))

    def _copy_selected(self):
        """Copy selected rows to clipboard (tab-separated)."""
        model = self.model()
        if not model:
            return
        selection = self.selectionModel().selectedRows()
        if not selection:
            return
        lines = []
        for idx in sorted(selection, key=lambda x: x.row()):
            row_data = []
            for col in range(model.columnCount()):
                row_data.append(str(model.index(idx.row(), col).data() or ""))
            lines.append("\t".join(row_data))
        from PyQt6.QtWidgets import QApplication
        QApplication.clipboard().setText("\n".join(lines))

    def _export_csv(self):
        """Export full table to CSV file."""
        model = self.model()
        if not model:
            return
        path, _ = QFileDialog.getSaveFileName(
            self, "Export Results", "screener_results.csv",
            "CSV Files (*.csv);;All Files (*)"
        )
        if not path:
            return
        try:
            with open(path, "w", encoding="utf-8", newline="") as f:
                writer = csv.writer(f)
                # Header
                writer.writerow([
                    model.headerData(c, Qt.Orientation.Horizontal,
                                     Qt.ItemDataRole.DisplayRole)
                    for c in range(model.columnCount())
                ])
                # Rows
                for r in range(model.rowCount()):
                    row = []
                    for c in range(model.columnCount()):
                        row.append(model.index(r, c).data() or "")
                    writer.writerow(row)
            QMessageBox.information(
                self, "Export Complete",
                f"Exported {model.rowCount()} rows to:\n{path}"
            )
        except Exception as e:
            QMessageBox.warning(self, "Export Failed", str(e))
