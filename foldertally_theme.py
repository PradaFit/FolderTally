# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Display colors and constant-width focus styling for the desktop."""

PALETTES = {
    "light": dict(page="#F3F6FA", panel="#FFFFFF", text="#172B43", muted="#46596E",
                  border="#61758A", accent="#155AC5", on_accent="#FFFFFF",
                  hover="#EAF2FF", disabled="#E9EDF3", disabled_text="#64748B"),
    "dark": dict(page="#101820", panel="#17232F", text="#E8EEF5", muted="#BAC8D8",
                 border="#8B9CAF", accent="#85BAFF", on_accent="#10243A",
                 hover="#263A50", disabled="#25313D", disabled_text="#9AA8B8"),
}


def stylesheet(mode, point_size):
    c = PALETTES[mode]
    return f"""
        QWidget {{ font-size: {point_size}pt; color: {c['text']}; }}
        QMainWindow, QDialog, QMessageBox, QWidget#workflowBody {{ background: {c['page']}; }}
        QLabel {{ background: transparent; font-weight: normal; }}
        QLabel#brandTitle {{ font-size: {point_size * 1.8}pt; font-weight: 700; }}
        QLabel#scanStatus {{ font-weight: 700; }}
        QGroupBox {{ background: {c['panel']}; border: 2px solid {c['border']}; border-radius: 5px;
                     margin-top: {round(point_size * 1.8)}px; font-weight: 600; }}
        QGroupBox::title {{ subcontrol-origin: margin; left: 12px; padding: 0 5px; }}
        QLineEdit, QComboBox, QTextBrowser {{ color: {c['text']}; background: {c['panel']};
            border: 2px solid {c['border']}; border-radius: 3px; padding: 6px;
            selection-background-color: {c['accent']}; selection-color: {c['on_accent']}; }}
        QComboBox QAbstractItemView {{ background: {c['panel']}; color: {c['text']};
            selection-background-color: {c['accent']}; selection-color: {c['on_accent']}; }}
        QPushButton {{ color: {c['text']}; background: {c['panel']}; border: 2px solid {c['border']};
                       border-radius: 3px; padding: 7px 12px; }}
        QPushButton:hover {{ background: {c['hover']}; }}
        QPushButton:disabled {{ color: {c['disabled_text']}; background: {c['disabled']}; }}
        QPushButton#createReport {{ background: {c['accent']}; color: {c['on_accent']}; }}
        QPushButton#createReport:disabled {{ background: {c['disabled']}; color: {c['disabled_text']}; }}
        QPushButton#createReport:focus {{ border-color: {c['on_accent']}; }}
        QRadioButton {{ padding: 6px; border: 2px solid transparent; border-radius: 3px; }}
        QRadioButton::indicator {{ width: 16px; height: 16px; border-radius: 9px;
                                  border: 2px solid {c['border']}; background: {c['panel']}; }}
        QRadioButton::indicator:checked {{ background: {c['accent']}; border-color: {c['accent']}; }}
        QLineEdit:focus, QComboBox:focus, QPushButton:focus, QRadioButton:focus, QTextBrowser:focus {{
            border-color: {c['accent']}; }}
        QScrollBar:vertical {{ background: {c['page']}; width: 14px; }}
        QScrollBar::handle:vertical {{ background: {c['border']}; min-height: 28px; border-radius: 4px; }}
        QToolTip {{ color: {c['text']}; background: {c['panel']}; border: 1px solid {c['border']}; }}
    """
