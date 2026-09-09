# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Check widget geometry and capture only the app, at several text sizes."""
import json
from pathlib import Path
import sys
from unittest.mock import patch
sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from PySide6.QtCore import QPoint, Qt
from PySide6.QtGui import QPalette, QColor
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QLabel
from foldertally_desktop import FolderTallyApp


def main():
    output = Path(sys.argv[1]) if len(sys.argv) > 1 else Path(__file__).resolve().parents[1] / "_Internal" / "verification"
    output.mkdir(parents=True, exist_ok=True)
    qt = QApplication([])
    qt.setQuitOnLastWindowClosed(False)
    results = []
    for mode in ("light", "dark", "high-contrast"):
        original = qt.palette()
        if mode == "light":
            palette = QPalette(original)
            for role, color in ((QPalette.Window, "#F3F6FA"), (QPalette.WindowText, "#172B43"),
                                (QPalette.Base, "#FFFFFF"), (QPalette.Text, "#172B43"),
                                (QPalette.Button, "#FFFFFF"), (QPalette.ButtonText, "#172B43")):
                palette.setColor(role, QColor(color))
            qt.setPalette(palette)
        elif mode == "dark":
            palette = QPalette(original)
            for role, color in ((QPalette.Window, "#202020"), (QPalette.WindowText, "#FFFFFF"),
                                (QPalette.Base, "#121212"), (QPalette.Text, "#FFFFFF"),
                                (QPalette.Button, "#333333"), (QPalette.ButtonText, "#FFFFFF")):
                palette.setColor(role, QColor(color))
            qt.setPalette(palette)
        with patch("foldertally_desktop.high_contrast_enabled", return_value=mode == "high-contrast"):
            window = FolderTallyApp(remember=False)
            window.theme_combo.setCurrentIndex(window.theme_combo.findData('dark' if mode == 'high-contrast' else mode))
            window.show()
            for zoom in range(window.zoom_combo.count()):
                for width, height, label in ((1000, 900, "default"), (640, 640, "compact"), (440, 500, "minimum")):
                    window.zoom_combo.setCurrentIndex(zoom)
                    window.resize(width, height)
                    window.source_entry.setFocus()
                    QTest.qWait(100)
                    issues = []
                    if window.body.width() > window.scroll.viewport().width():
                        issues.append('content is wider than the scroll viewport')
                    if not (window.brand_label.geometry().bottom() < window.theme_combo.y()
                            <= window.zoom_combo.y() < window.intro_label.y()):
                        issues.append('appearance controls are not between the title and introduction')
                    for control in (window.theme_combo, window.zoom_combo):
                        if control.geometry().right() >= window.body.width():
                            issues.append(f'{control.objectName()}: header control exceeds content width')
                    expected_font = window.base_font.pointSizeF() * int(window.zoom_combo.currentText().rstrip('%')) / 100
                    for widget in (window.source_entry, window.destination_entry, window.start_button, window.zoom_combo):
                        if abs(widget.font().pointSizeF() - expected_font) > 0.1:
                            issues.append(f"{widget.objectName()}: font did not scale")
                    for widget in (*window.interactive, *window.format_buttons, window.memory_combo, window.zoom_combo, window.theme_combo):
                        if widget.width() + 2 < widget.sizeHint().width():
                            issues.append(f"{widget.objectName()}: width {widget.width()} < {widget.sizeHint().width()}")
                        if widget.height() < widget.fontMetrics().height() + 16:
                            issues.append(f"{widget.objectName()}: insufficient text height")
                    for widget in window.findChildren(QLabel):
                        if widget.text() and widget.height() + 2 < widget.heightForWidth(widget.width()):
                            issues.append(f"label {widget.objectName() or widget.text()[:25]}: clipped height")
                    for button in (window.start_button, window.cancel_button, window.help_button, window.about_button):
                        point = button.mapTo(window.body, QPoint(button.width(), button.height()))
                        if point.y() > window.body.height() or point.x() > window.body.width():
                            issues.append(f"{button.objectName()}: outside scrollable content")
                        if zoom == 0 and label == 'default':
                            visible_corner = button.mapTo(window.scroll.viewport(), button.rect().bottomRight())
                            if not window.scroll.viewport().rect().contains(visible_corner):
                                issues.append(f"{button.objectName()}: clipped in default layout")
                    work = window.screen().availableGeometry()
                    if window.frameGeometry().height() > work.height() or window.frameGeometry().width() > work.width():
                        issues.append("window exceeds monitor work area")
                    assert window.source_browse.x() == window.destination_browse.x()
                    window.grab().save(str(output / f"qt-{mode}-{window.zoom_combo.currentText()}-{label}.png"))
                    results.append({"mode": mode, "text": window.zoom_combo.currentText(), "layout": label,
                                    "window": [window.width(), window.height()], "issues": issues})
            window.zoom_combo.setCurrentIndex(0)
            window.resize(1000, 900)
            QTest.qWait(80)
            window.close()
            window.deleteLater()
            qt.processEvents()
        qt.setPalette(original)
    (output / "layout-results-qt.json").write_text(json.dumps(results, indent=2), encoding="utf-8")
    print(json.dumps(results, indent=2))
    if any(item["issues"] for item in results):
        raise SystemExit(1)


if __name__ == "__main__":
    main()
