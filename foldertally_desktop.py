# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Windows desktop interface with platform accessibility support."""
import ctypes
import hashlib
import multiprocessing
import os
import sys
from pathlib import Path
import time

from PySide6.QtCore import QEvent, QPoint, Qt, QTimer, Signal
from PySide6.QtGui import (QAccessible, QAccessibleAnnouncementEvent, QFont, QIcon,
                          QKeySequence, QPalette, QShortcut, QCursor)
from PySide6.QtWidgets import (QApplication, QButtonGroup, QComboBox, QDialog,
    QDialogButtonBox, QFileDialog, QFrame, QGridLayout, QGroupBox, QHBoxLayout,
    QLabel, QLineEdit, QMainWindow, QMessageBox, QPushButton, QRadioButton,
    QScrollArea, QSizePolicy, QTextBrowser, QVBoxLayout, QWidget)

import FolderTally as core
from foldertally_service import scan_worker, validate_request
from foldertally_window_state import (preferences_path, load_preferences, save_preferences,
                                    choose_monitor, centered_frame, TEXT_SIZES)
from foldertally_theme import PALETTES, stylesheet


def resource_path(name):
    if getattr(sys, 'frozen', False) and name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'licenses'):
        return Path(sys.executable).resolve().parent / name
    return Path(__file__).resolve().parent / name


def high_contrast_enabled():
    if os.name != "nt":
        return False
    class HighContrast(ctypes.Structure):
        _fields_ = [("cbSize", ctypes.c_uint), ("dwFlags", ctypes.c_uint), ("scheme", ctypes.c_wchar_p)]
    info = HighContrast()
    info.cbSize = ctypes.sizeof(info)
    return bool(ctypes.windll.user32.SystemParametersInfoW(0x0042, info.cbSize, ctypes.byref(info), 0) and info.dwFlags & 1)


def monitor_id(screen):
    serial = screen.serialNumber()
    suffix = hashlib.sha256(serial.encode()).hexdigest()[:16] if serial else f"{screen.geometry().x()},{screen.geometry().y()}"
    return f"{screen.name()[:80]}|{suffix}"


def centered_on(widget, screen):
    work = screen.availableGeometry()
    frame = widget.frameGeometry()
    x, y = centered_frame(work.getRect(), (frame.width(), frame.height()))
    widget.move(x, y)


class FolderTallyApp(QMainWindow):
    announced = Signal(str)

    def __init__(self, state_path=None, remember=True):
        super().__init__()
        self.setWindowTitle("FolderTally")
        self.setWindowIcon(QIcon(str(resource_path("assets/FolderTally.ico"))))
        self.setAccessibleName("FolderTally folder inventory")
        self.state_path = (state_path if state_path is not None else preferences_path()) if remember else None
        self.preferences = load_preferences(self.state_path)
        self.saved_monitor = self.preferences["monitor"]
        self.initial_screen = self._choose_screen()
        self.initial_placement = True
        self.ready = False
        self.process = self.connection = self.cancel_event = None
        self.terminal = None
        self.last_report = None
        self.closing = False
        self.appearance_pending = False
        self.applying_theme = False
        self.status_text = "Ready to scan"
        self.last_announcement = ""
        self.base_font = QFont(QApplication.font())
        self.base_font.setPointSizeF(max(10.0, self.base_font.pointSizeF()))
        self.setFont(self.base_font)
        self.controls = []
        self.interactive = []
        self._build()
        self.apply_zoom()
        self.poll_timer = QTimer(self)
        self.poll_timer.setInterval(100)
        self.poll_timer.timeout.connect(self._poll)
        self.remember_timer = QTimer(self)
        self.remember_timer.setSingleShot(True)
        self.remember_timer.setInterval(300)
        self.remember_timer.timeout.connect(self.remember_monitor)
        self.winId()
        self.windowHandle().setScreen(self.initial_screen)
        self.windowHandle().screenChanged.connect(self._screen_changed)
        QApplication.instance().screenRemoved.connect(self._screen_removed)
        QApplication.instance().focusChanged.connect(self._focus_changed)
        self.resize_for_screen(self.initial_screen)
        for sequence, callback in (("Esc", self.cancel),
                                   ("F1", self.help), ("Ctrl++", lambda: self.zoom_step(1)),
                                   ("Ctrl+=", lambda: self.zoom_step(1)), ("Ctrl+-", lambda: self.zoom_step(-1)),
                                   ("Ctrl+0", lambda: self.zoom_combo.setCurrentIndex(0)),
                                   ("Alt+R", self.focus_results)):
            shortcut = QShortcut(QKeySequence(sequence), self)
            shortcut.activated.connect(callback)
        self.ready = True

    def _choose_screen(self):
        app = QApplication.instance()
        screens = app.screens()
        fallback = app.screenAt(QCursor.pos()) or app.primaryScreen()
        names = [monitor_id(s) for s in screens]
        selected = choose_monitor(names, self.saved_monitor, monitor_id(fallback))
        return next(s for s in screens if monitor_id(s) == selected)

    def resize_for_screen(self, screen):
        work = screen.availableGeometry()
        self.setMinimumSize(min(440, work.width() - 32), min(400, work.height() - 64))
        self.resize(min(1000, work.width() - 32), min(900, work.height() - 80))

    def showEvent(self, event):
        super().showEvent(event)
        if self.initial_placement:
            self.initial_placement = False
            centered_on(self, self.initial_screen)
            self.source_entry.setFocus()
            self.remember_timer.start()
            QTimer.singleShot(0, self._reflow)

    def moveEvent(self, event):
        super().moveEvent(event)
        if self.ready and not self.isMinimized():
            self.remember_timer.start()

    def _screen_changed(self, _screen):
        if self.ready:
            self.remember_timer.start()

    def _screen_removed(self, _screen):
        QTimer.singleShot(100, self._recover_screen)

    def _recover_screen(self):
        if not any(s.availableGeometry().intersects(self.frameGeometry()) for s in QApplication.screens()):
            screen = self._choose_screen()
            self.windowHandle().setScreen(screen)
            self.resize_for_screen(screen)
            centered_on(self, screen)

    def remember_monitor(self):
        if self.isMinimized() or not self.isVisible():
            return
        screen = self.screen()
        name = monitor_id(screen)
        if self.state_path is not None:
            self.preferences["monitor"] = name
            if not save_preferences(self.state_path, self.preferences):
                self.preference_note.setText("Display preferences could not be saved on this computer.")
                self.preference_note.show()
            else:
                self.preference_note.hide()
        self.saved_monitor = name

    def _name(self, widget, name, identifier, description=""):
        widget.setAccessibleName(name)
        widget.setAccessibleDescription(description)
        widget.setObjectName(identifier)
        return widget

    def _label(self, text, parent=None):
        label = QLabel(text, parent)
        label.setTextFormat(Qt.TextFormat.PlainText)
        label.setWordWrap(True)
        label.setSizePolicy(QSizePolicy.Policy.Ignored, QSizePolicy.Policy.Preferred)
        return label

    def _button(self, text, name, identifier, callback):
        button = self._name(QPushButton(text), name, identifier)
        button.clicked.connect(callback)
        button.setMinimumHeight(38)
        self.interactive.append(button)
        return button

    def _build(self):
        central = QWidget()
        self.setCentralWidget(central)
        outer = QVBoxLayout(central)
        outer.setContentsMargins(20, 16, 20, 16)
        outer.setSpacing(14)
        header = QVBoxLayout()
        header.setSpacing(10)
        brand = self._label("FolderTally")
        self.brand_label = brand
        brand.setObjectName("brandTitle")
        font = QFont(self.font()); font.setPointSizeF(font.pointSizeF() * 1.8); font.setBold(True)
        brand.setFont(font)
        brand.setSizePolicy(QSizePolicy.Policy.Expanding, QSizePolicy.Policy.Preferred)
        brand_stack = QVBoxLayout()
        brand_stack.setSpacing(3)
        brand_stack.setAlignment(Qt.AlignmentFlag.AlignTop)
        brand_stack.addWidget(brand)
        header.addLayout(brand_stack)
        appearance = QGridLayout()
        appearance.setHorizontalSpacing(12)
        appearance.setVerticalSpacing(8)
        self.appearance_layout = appearance
        self.theme_combo = self._name(QComboBox(), "Theme", "appearanceTheme", "System, Light, or Dark. Windows high contrast takes priority.")
        for name, value in (("System", "system"), ("Light", "light"), ("Dark", "dark")):
            self.theme_combo.addItem(name, value)
        self.theme_combo.setCurrentIndex(self.theme_combo.findData(self.preferences["theme"]))
        theme_label = self._label("The&me")
        self.theme_label = theme_label
        theme_label.setBuddy(self.theme_combo)
        theme_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        appearance.addWidget(theme_label, 0, 0)
        appearance.addWidget(self.theme_combo, 0, 1)
        self.zoom_combo = self._name(QComboBox(), "Text size", "textSize", "Enlarge text without changing Windows settings.")
        self.zoom_combo.addItems(["100%", "125%", "150%", "200%", "300%", "400%"])
        self.zoom_combo.setCurrentIndex(TEXT_SIZES.index(self.preferences["text_size"]))
        zoom_label = self._label("Te&xt size")
        self.zoom_label = zoom_label
        zoom_label.setTextFormat(Qt.TextFormat.AutoText)
        zoom_label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
        zoom_label.setBuddy(self.zoom_combo)
        appearance.addWidget(zoom_label, 0, 2)
        appearance.addWidget(self.zoom_combo, 0, 3)
        appearance.setColumnStretch(4, 1)
        header.addLayout(appearance)
        self.scroll = QScrollArea()
        self.scroll.setObjectName("workflowScroll")
        self.scroll.setAccessibleName("Report settings and results")
        self.scroll.setWidgetResizable(True)
        self.scroll.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.scroll.viewport().installEventFilter(self)
        self.scroll.setFrameShape(QFrame.Shape.NoFrame)
        self.scroll.setHorizontalScrollBarPolicy(Qt.ScrollBarPolicy.ScrollBarAlwaysOff)
        self.body = QWidget()
        self.body.setObjectName("workflowBody")
        body = QVBoxLayout(self.body)
        body.setContentsMargins(0, 0, 0, 0)
        body.setSpacing(14)
        body.addLayout(header)
        self.intro_label = self._label("Choose a folder to review its sizes and export a file inventory.")
        self.intro_label.setObjectName("workflowIntro")
        body.addWidget(self.intro_label)
        form = self._name(QGroupBox("Report settings"), "Report settings", "reportSettings")
        self.form_grid = QGridLayout(form)
        self.form_grid.setContentsMargins(18, 22, 18, 16)
        self.form_grid.setVerticalSpacing(10)
        self.form_grid.setHorizontalSpacing(12)
        self.form_grid.setColumnStretch(0, 1)
        self.source_entry = self._name(QLineEdit(), "Source folder", "sourceFolder", "Folder to inventory. File contents are not read.")
        self.destination_entry = self._name(QLineEdit(str(core.get_downloads_folder())), "Save report in", "reportFolder", "Existing folder for the report. Existing files are preserved.")
        self.source_browse = self._button("Browse source", "Browse source folder", "browseSource", self.browse_source)
        self.destination_browse = self._button("Browse reports", "Browse report folder", "browseReports", self.browse_destination)
        self.path_labels = []
        for row, label_text, entry, button in ((0, "&Source folder", self.source_entry, self.source_browse),
                                               (2, "Save report &in", self.destination_entry, self.destination_browse)):
            label = self._label(label_text)
            label.setBuddy(entry)
            label.setSizePolicy(QSizePolicy.Policy.Preferred, QSizePolicy.Policy.Preferred)
            self.path_labels.append(label)
            self.form_grid.addWidget(label, row, 0, 1, 2)
            self.form_grid.addWidget(entry, row + 1, 0)
            self.form_grid.addWidget(button, row + 1, 1)
            entry.setMinimumHeight(38)
        self.controls.extend([self.source_entry, self.destination_entry, self.source_browse, self.destination_browse])
        note = self._label("Each report gets a unique filename. Existing files are preserved.")
        self.output_note = note
        self.form_grid.addWidget(note, 4, 0, 1, 2)
        self.format_box = self._name(QGroupBox("Report format"), "Report format", "reportFormat")
        self.format_layout = QGridLayout(self.format_box)
        self.format_group = QButtonGroup(self)
        self.format_buttons = []
        for index, (fmt, text) in enumerate((("txt", "&TXT text"), ("json", "&JSON data"), ("pdf", "&PDF document"))):
            button = self._name(QRadioButton(text), text.replace("&", ""), f"format_{fmt}")
            button.setProperty("format", fmt)
            self.format_group.addButton(button, index)
            self.format_layout.addWidget(button, 0, index)
            self.format_buttons.append(button)
            self.controls.append(button)
        self.format_buttons[0].setChecked(True)
        self.memory_box = self._name(QGroupBox("Worker memory limit"), "Worker memory limit", "workerMemory")
        memory_layout = QVBoxLayout(self.memory_box)
        self.memory_combo = self._name(QComboBox(), "Worker memory limit", "memoryLimit")
        for cap in (256, 512, 1024, 2048): self.memory_combo.addItem(f"{cap} MiB", cap)
        self.memory_combo.setCurrentIndex(3)
        memory_layout.addWidget(self.memory_combo)
        self.controls.append(self.memory_combo)
        self.form_grid.addWidget(self.format_box, 5, 0)
        self.form_grid.addWidget(self.memory_box, 5, 1)
        body.addWidget(form)
        self.metrics_box = self._name(QGroupBox("Inventory totals"), "Inventory totals", "inventoryTotals")
        self.metrics_grid = QGridLayout(self.metrics_box)
        self.metrics = {}
        for index, (key, text) in enumerate((("files", "Files"), ("folders", "Subfolders"), ("size", "Total file size"), ("warnings", "Read errors"))):
            label = self._label(f"{text}: 0 B" if key == "size" else f"{text}: 0")
            label.setAccessibleName(label.text())
            label.setObjectName(f"total_{key}")
            self.metrics[key] = label
            self.metrics_grid.addWidget(label, 0, index)
        body.addWidget(self.metrics_box)
        self.result_box = self._name(QGroupBox("Results"), "Results", "results")
        results = QVBoxLayout(self.result_box)
        results.setContentsMargins(18, 22, 18, 16)
        results.setSpacing(10)
        self.status_label = self._name(self._label("Ready to scan"), "Ready to scan", "scanStatus")
        status_font = QFont(self.font()); status_font.setBold(True); self.status_label.setFont(status_font)
        self.detail_label = self._label("Choose a source folder, then create your report.")
        self.detail_label.setObjectName("scanDetail")
        self.elapsed_label = self._label("")
        self.elapsed_label.setObjectName("elapsedTime")
        self.elapsed_label.hide()
        results.addWidget(self.status_label)
        results.addWidget(self.detail_label)
        results.addWidget(self.elapsed_label)
        self.result_entry = self._name(QLineEdit(), "Saved report path", "savedReport", "Read-only path. Copy it with Control+C or use Open report.")
        self.result_entry.setReadOnly(True)
        self.result_entry.setMinimumHeight(38)
        results.addWidget(self.result_entry)
        self.result_actions = QHBoxLayout()
        self.open_button = self._button("&Open report", "Open report", "openReport", self.open_report)
        self.folder_button = self._button("Show &folder", "Show folder", "showFolder", self.show_folder)
        self.open_button.setEnabled(False); self.folder_button.setEnabled(False)
        self.result_actions.addWidget(self.open_button); self.result_actions.addWidget(self.folder_button)
        self.result_actions.addStretch()
        results.addLayout(self.result_actions)
        body.addWidget(self.result_box)
        body.addWidget(self._label("File metadata only. No telemetry or file-content uploads."))
        self.preference_note = self._label("")
        self.preference_note.hide()
        body.addWidget(self.preference_note)
        body.addStretch()
        self.scroll.setWidget(self.body)
        outer.addWidget(self.scroll, 1)
        self.footer = QGridLayout()
        self.help_button = self._button("&Help", "Help", "help", self.help)
        self.about_button = self._button("&About", "About FolderTally", "about", self.about)
        self.start_button = self._button("&Create report", "Create report", "createReport", self.start)
        self.cancel_button = self._button("Cancel", "Cancel scan", "cancelScan", self.cancel)
        self.cancel_button.setEnabled(False)
        for column, button in enumerate((self.help_button, self.about_button, self.start_button, self.cancel_button)):
            self.footer.addWidget(button, 0, column)
        body.insertLayout(body.count() - 1, self.footer)
        self.zoom_combo.currentIndexChanged.connect(self.queue_appearance)
        self.theme_combo.currentIndexChanged.connect(self.queue_appearance)
        # Explicit order follows the visual workflow, including result actions.
        self.tab_widgets = [self.source_entry, self.source_browse, self.destination_entry, self.destination_browse,
                            *self.format_buttons, self.memory_combo, self.result_entry, self.open_button,
                            self.folder_button, self.start_button, self.cancel_button, self.help_button,
                            self.about_button, self.theme_combo, self.zoom_combo]
        for first, second in zip(self.tab_widgets, self.tab_widgets[1:]): self.setTabOrder(first, second)
        self.setTabOrder(self.tab_widgets[-1], self.tab_widgets[0])

    def _theme(self):
        if self.applying_theme:
            return
        self.applying_theme = True
        try:
            system_palette = QApplication.palette()
            if high_contrast_enabled():
                self.setStyleSheet("")
                self.setPalette(system_palette)
                self.effective_theme = "high-contrast"
                return
            mode = self.theme_combo.currentData()
            if mode == "system":
                mode = "dark" if system_palette.color(QPalette.ColorRole.Window).lightness() < 100 else "light"
            self.effective_theme = mode
            colors = PALETTES[mode]
            palette = QPalette(system_palette)
            from PySide6.QtGui import QColor
            for role, key in ((QPalette.Window, "page"), (QPalette.WindowText, "text"),
                              (QPalette.Base, "panel"), (QPalette.Text, "text"),
                              (QPalette.Button, "panel"), (QPalette.ButtonText, "text"),
                              (QPalette.Highlight, "accent"), (QPalette.HighlightedText, "on_accent")):
                palette.setColor(role, QColor(colors[key]))
            self.setPalette(palette)
            point_size = self.base_font.pointSizeF() * int(self.zoom_combo.currentText().rstrip("%")) / 100
            self.setStyleSheet(stylesheet(mode, point_size))
        finally:
            self.applying_theme = False

    def queue_appearance(self):
        if not self.appearance_pending:
            self.appearance_pending = True
            QTimer.singleShot(0, self._apply_appearance)

    def _apply_appearance(self):
        self.appearance_pending = False
        self.preferences["theme"] = self.theme_combo.currentData()
        self.preferences["text_size"] = int(self.zoom_combo.currentText().rstrip("%"))
        self.apply_zoom()
        if self.ready:
            self.remember_timer.start()

    def changeEvent(self, event):
        super().changeEvent(event)
        if event.type() in (QEvent.Type.ApplicationPaletteChange, QEvent.Type.ThemeChange) and self.ready:
            self._theme()

    def resizeEvent(self, event):
        super().resizeEvent(event)
        if self.ready:
            self._reflow()

    def eventFilter(self, watched, event):
        if self.ready and watched is self.scroll.viewport() and event.type() == QEvent.Type.Resize:
            QTimer.singleShot(0, self._reflow)
        return super().eventFilter(watched, event)

    def _reflow(self):
        for control in (*self.interactive, *self.format_buttons, self.source_entry, self.destination_entry,
                        self.result_entry, self.theme_combo, self.zoom_combo, self.memory_combo):
            control.setMinimumHeight(max(38, control.fontMetrics().height() + 20))
        narrow = self.scroll.viewport().width() < round(760 * self.font().pointSizeF() / self.base_font.pointSizeF())
        self.memory_box.setTitle("Memory limit" if self.zoom_combo.currentIndex() >= 4 else "Worker memory limit")
        self.memory_box.setMinimumWidth(self.memory_box.fontMetrics().horizontalAdvance(self.memory_box.title()) + 42)
        for widget in (self.source_entry, self.source_browse, self.destination_entry, self.destination_browse,
                       *self.path_labels, self.format_box, self.memory_box):
            self.form_grid.removeWidget(widget)
        # The explanatory note occupies row 4 in wide mode and row 6 in narrow mode.
        note_widget = self.output_note
        self.form_grid.removeWidget(note_widget)
        for i, (label, entry, button) in enumerate(zip(self.path_labels, (self.source_entry, self.destination_entry),
                                                      (self.source_browse, self.destination_browse))):
            row = i * (3 if narrow else 2)
            self.form_grid.addWidget(label, row, 0, 1, 2)
            self.form_grid.addWidget(entry, row + 1, 0, 1, 2 if narrow else 1)
            self.form_grid.addWidget(button, row + 2 if narrow else row + 1, 0 if narrow else 1, 1, 2 if narrow else 1)
        note_row = 6 if narrow else 4
        if note_widget: self.form_grid.addWidget(note_widget, note_row, 0, 1, 2)
        self.form_grid.addWidget(self.format_box, note_row + 1, 0, 1, 2 if narrow else 1)
        self.form_grid.addWidget(self.memory_box, note_row + 2 if narrow else note_row + 1, 0 if narrow else 1, 1, 2 if narrow else 1)
        for index, button in enumerate(self.format_buttons):
            self.format_layout.removeWidget(button)
            self.format_layout.addWidget(button, index if narrow else 0, 0 if narrow else index)
        for index, label in enumerate(self.metrics.values()):
            self.metrics_grid.removeWidget(label)
            self.metrics_grid.addWidget(label, index // (2 if narrow else 4), index % (2 if narrow else 4))
        footer_buttons = (self.help_button, self.about_button, self.start_button, self.cancel_button)
        footer_columns = max(1, min(4, (self.width() - 40) // (max(b.sizeHint().width() for b in footer_buttons) + 12)))
        for index, button in enumerate(footer_buttons):
            self.footer.removeWidget(button)
            self.footer.addWidget(button, index // footer_columns, index % footer_columns)
        self.zoom_combo.setMinimumWidth(self.zoom_combo.sizeHint().width())
        self.theme_combo.setMinimumWidth(self.theme_combo.sizeHint().width())
        appearance_controls = (self.theme_label, self.theme_combo, self.zoom_label, self.zoom_combo)
        appearance_width = sum(widget.sizeHint().width() for widget in appearance_controls) + 3 * self.appearance_layout.horizontalSpacing()
        stack_appearance = appearance_width > self.scroll.viewport().width()
        for widget in appearance_controls:
            self.appearance_layout.removeWidget(widget)
        for column in range(5):
            self.appearance_layout.setColumnStretch(column, 0)
        for index, widget in enumerate(appearance_controls):
            row, column = divmod(index, 2) if stack_appearance else (0, index)
            self.appearance_layout.addWidget(widget, row, column)
        self.appearance_layout.setColumnStretch(2 if stack_appearance else 4, 1)
        self.result_actions.setDirection(QHBoxLayout.Direction.TopToBottom if narrow else QHBoxLayout.Direction.LeftToRight)
        # At the largest text sizes, stop shrinking before unbreakable control
        # labels exceed the viewport. Vertical content remains scrollable.
        self.body.layout().activate()
        minimum = max(440, self.body.minimumSizeHint().width() + 54) if self.zoom_combo.currentIndex() >= 4 else 440
        self.setMinimumWidth(min(minimum, self.screen().availableGeometry().width() - 32))

    def apply_zoom(self):
        factor = int(self.zoom_combo.currentText().rstrip("%")) / 100
        font = QFont(self.base_font); font.setPointSizeF(self.base_font.pointSizeF() * factor)
        self.setFont(font)
        self._theme()
        title = QFont(font); title.setPointSizeF(font.pointSizeF() * 1.8); title.setBold(True)
        self.brand_label.setFont(title)
        status = QFont(font); status.setBold(True); self.status_label.setFont(status)
        self._reflow()
        QTimer.singleShot(0, lambda: self._focus_changed(None, QApplication.focusWidget()))

    def zoom_step(self, step):
        self.zoom_combo.setCurrentIndex(max(0, min(self.zoom_combo.count() - 1, self.zoom_combo.currentIndex() + step)))

    def _focus_changed(self, _old, current):
        if current is not None and self.body.isAncestorOf(current):
            self.scroll.ensureWidgetVisible(current, 12, 12)

    def focus_results(self):
        self.result_entry.setFocus()
        self._announce(self.status_text + ". " + self.detail_label.text())

    def _announce(self, message):
        if message == self.last_announcement:
            return
        self.last_announcement = message
        event = QAccessibleAnnouncementEvent(self.status_label, message)
        event.setPoliteness(QAccessible.AnnouncementPoliteness.Polite)
        QAccessible.updateAccessibility(event)
        self.announced.emit(message)

    def set_status(self, title, detail=None, announce=True):
        changed = title != self.status_text
        self.status_text = title
        self.status_label.setText(title); self.status_label.setAccessibleName(title)
        if detail is not None: self.detail_label.setText(detail)
        if announce and (changed or detail is not None):
            self._announce(title + (". " + detail if detail else ""))

    def browse_source(self):
        path = QFileDialog.getExistingDirectory(self, "Choose source folder")
        if path: self.source_entry.setText(path)
        self.source_entry.setFocus()

    def browse_destination(self):
        path = QFileDialog.getExistingDirectory(self, "Choose report folder")
        if path: self.destination_entry.setText(path)
        self.destination_entry.setFocus()

    def _busy(self, busy):
        for control in self.controls: control.setEnabled(not busy)
        self.start_button.setEnabled(not busy)
        self.cancel_button.setEnabled(busy)
        self.open_button.setEnabled(not busy and self.last_report is not None)
        self.folder_button.setEnabled(not busy and self.last_report is not None)

    def start(self):
        if self.process is not None: return
        try:
            cap = self.memory_combo.currentData()
            fmt = self.format_group.checkedButton().property("format")
            source, destination = validate_request(self.source_entry.text(), self.destination_entry.text(), fmt, cap)
        except (ValueError, OSError) as exc:
            self.set_status("Check your folder selection", str(exc))
            field = self.source_entry if "source" in str(exc).lower() else self.destination_entry
            field.setAccessibleDescription(str(exc)); field.setFocus()
            return
        self.last_report = None
        self.result_entry.clear()
        self._update_metrics({"total": 0, "counts": {"files": 0, "folders": 0, "errors": 0}})
        self.set_status("Starting scan", "Reading file metadata. Cancel or press Escape to stop.")
        self.started = time.monotonic(); self.terminal = None
        context = multiprocessing.get_context("spawn")
        self.connection, sender = context.Pipe(duplex=False)
        self.cancel_event = context.Event()
        request = {"target": str(source), "destination": str(destination), "format": fmt, "cap": cap}
        self.process = context.Process(target=scan_worker, args=(sender, self.cancel_event, request), daemon=True)
        try:
            self.process.start()
        except Exception as exc:
            sender.close(); self.connection.close()
            self.process = self.connection = None
            self.set_status("Could not start scan", str(exc)); self._busy(False)
            return
        sender.close(); self._busy(True)
        self.cancel_button.setFocus()
        self.poll_timer.start()

    def _update_metrics(self, data):
        counts = data["counts"]
        values = {"files": f"Files: {counts['files']:,}", "folders": f"Subfolders: {counts['folders']:,}",
                  "size": f"Total file size: {core.human_size(data['total'])}", "warnings": f"Read errors: {counts['errors']:,}"}
        for key, text in values.items():
            self.metrics[key].setText(text); self.metrics[key].setAccessibleName(text)

    def _poll(self):
        if self.process is None: return
        self.elapsed_label.setText(f"Elapsed: {int(time.monotonic() - self.started):,} seconds")
        self.elapsed_label.show()
        self._drain()
        if not self.process.is_alive():
            self._drain()
            self.process.join(timeout=0); self.process.close(); self.process = None
            self.connection.close(); self.connection = None; self.poll_timer.stop()
            self._finish(self.terminal or {"kind": "error", "message": "The worker stopped unexpectedly. Try a higher memory limit or a smaller folder."})

    def _drain(self):
        try:
            while self.connection.poll():
                data = self.connection.recv()
                if data["kind"] in ("complete", "cancelled", "error"):
                    self.terminal = data
                elif data["kind"] == "progress":
                    self._update_metrics(data)
                    if not self.cancel_event.is_set(): self.set_status("Writing report" if data["phase"] == "exporting" else "Scanning folders")
                elif data["kind"] == "started" and not self.cancel_event.is_set():
                    self.set_status("Scanning folders")
        except (EOFError, OSError):
            pass

    def _finish(self, data):
        if data["kind"] == "complete":
            self._update_metrics(data)
            self.last_report = Path(data["path"]); self.result_entry.setText(str(self.last_report))
            errors = data["counts"]["errors"]
            self.set_status("Report saved with read errors" if errors else "Report ready",
                f"{data['format'].upper()} report saved. {data['counts']['files']:,} files, {data['counts']['folders']:,} subfolders, "
                f"{core.human_size(data['total'])}. {errors:,} read errors.")
        elif data["kind"] == "cancelled":
            self.set_status("Scan cancelled", "No report was saved. You can adjust your selection and start again.")
        else:
            self.set_status("Report could not be created", data["message"])
        restore_focus = self.cancel_button.hasFocus() or QApplication.focusWidget() is None
        self._busy(False)
        if restore_focus:
            (self.open_button if self.last_report else self.start_button).setFocus()
        if self.closing: self.close()

    def cancel(self):
        if self.process is None: return
        self.cancel_event.set()
        self.cancel_button.setEnabled(False)
        self.set_status("Cancelling scan", "Waiting for the current file operation and temporary file cleanup.")
        self.help_button.setFocus()

    def _open(self, path):
        try:
            if not path.exists(): raise FileNotFoundError("The report or its folder has been moved or removed.")
            os.startfile(str(path))
        except OSError as exc:
            self.message("Could not open", str(exc))

    def open_report(self):
        if self.last_report is not None and self.last_report.suffix.lower() in (".txt", ".json", ".pdf"):
            self._open(self.last_report)

    def show_folder(self):
        if self.last_report is not None: self._open(self.last_report.parent)

    def _center_dialog(self, dialog):
        dialog.winId()
        dialog.windowHandle().setScreen(self.screen())
        dialog.show()
        centered_on(dialog, self.screen())

    def message(self, title, text, confirm=False):
        dialog = QMessageBox(self)
        dialog.setWindowTitle(title); dialog.setTextFormat(Qt.TextFormat.PlainText); dialog.setText(text)
        dialog.setStandardButtons(QMessageBox.StandardButton.Yes | QMessageBox.StandardButton.No if confirm else QMessageBox.StandardButton.Ok)
        if confirm: dialog.setDefaultButton(QMessageBox.StandardButton.No)
        self._center_dialog(dialog)
        return dialog.exec() == QMessageBox.StandardButton.Yes

    def _document(self, title, text):
        dialog = QDialog(self); dialog.setWindowTitle(title); dialog.setAccessibleName(title)
        layout = QVBoxLayout(dialog)
        browser = self._name(QTextBrowser(), title + " text", "documentText")
        browser.setOpenExternalLinks(False); browser.setPlainText(text)
        browser.setLineWrapMode(QTextBrowser.LineWrapMode.WidgetWidth)
        layout.addWidget(browser)
        buttons = QDialogButtonBox(QDialogButtonBox.StandardButton.Close)
        buttons.rejected.connect(dialog.reject); layout.addWidget(buttons)
        work = self.screen().availableGeometry()
        dialog.resize(min(700, work.width() - 48), min(580, work.height() - 80))
        self._center_dialog(dialog); browser.setFocus(); dialog.exec()

    def help(self):
        self._document("FolderTally help", "Choose a source folder and an existing report folder. Select TXT, JSON, or PDF, then Create report. "
            "Source file contents are not read. Existing reports are preserved.\n\n"
            "Keyboard: Tab and Shift+Tab move between controls. Space activates a button or radio choice. Arrow keys change a format or memory selection. "
            "Alt+C creates a report; Escape cancels. Alt+O opens a completed report; Alt+F opens its folder. Alt+R reads the result status. F1 opens this help.\n\n"
            "Text size: use the Text size selector or Control+Plus, Control+Minus, and Control+0. Content wraps and scrolls when needed. "
            "Windows high-contrast colors and the system font are respected.\n\n"
            "Theme: choose System, Light, or Dark. Windows high contrast takes priority. Theme and text size are remembered.\n\n"
            "The app opens centered on the last-used monitor. Only display preferences are saved in the current user's FolderTally application-data folder. "
            "If that monitor is disconnected, an available monitor is used.\n\n"
            "Read errors mean some entries could not be inventoried. Files can change during a scan. Cancellation waits for the current Windows file operation. "
            "For very large folders, TXT or JSON uses less report-generation memory. Reports may contain private file and folder names.")

    def about(self):
        text = f"FolderTally {core.VERSION}\nPublished by PradaFit\nCopyright (C) 2026 PradaFit\nSource-available noncommercial or separate commercial license\n\n"
        for name in ("THIRD_PARTY_NOTICES.md", "LICENSE"):
            try: text += resource_path(name).read_text(encoding="utf-8") + "\n\n"
            except OSError: text += name + " is available with the project source.\n"
        for path in sorted(resource_path("licenses").glob("*")):
            if path.is_file(): text += path.name + "\n" + path.read_text(encoding="utf-8", errors="replace") + "\n\n"
        self._document("About FolderTally", text)

    def closeEvent(self, event):
        if self.process is not None:
            if not self.closing:
                if not self.message("Close FolderTally?", "Cancel the active scan and close when cleanup finishes?", confirm=True):
                    event.ignore(); return
                self.closing = True
                if self.process is not None: self.cancel()
            if self.process is not None:
                event.ignore(); return
        self.remember_timer.stop(); self.remember_monitor()
        self.poll_timer.stop()
        event.accept()


def main():
    app = QApplication([])
    app.setApplicationName("FolderTally")
    app.setOrganizationName("PradaFit")
    app.setApplicationVersion(core.VERSION)
    window = FolderTallyApp()
    window.show()
    return app.exec()
