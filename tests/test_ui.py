# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

import json
import tempfile
import time
import unittest
from pathlib import Path
from unittest.mock import patch

from PySide6.QtCore import Qt, QTimer
from PySide6.QtGui import QAccessible
from PySide6.QtTest import QTest
from PySide6.QtWidgets import QApplication, QDialog, QMessageBox
from foldertally_desktop import FolderTallyApp, centered_on, monitor_id
from foldertally_window_state import load_monitor

APP = QApplication.instance() or QApplication([])
APP.setQuitOnLastWindowClosed(False)


class UITests(unittest.TestCase):
    def setUp(self):
        self.app = FolderTallyApp(remember=False)
        self.app.show()
        self.app.activateWindow()
        QTest.qWait(50)
        self.addCleanup(self.dispose)

    def dispose(self):
        self.app.close()
        self.app.deleteLater()
        APP.processEvents()

    def test_browse_buttons_and_inputs_align(self):
        app = self.app
        self.assertEqual(app.source_browse.x(), app.destination_browse.x())
        self.assertEqual(app.source_browse.width(), app.destination_browse.width())
        self.assertEqual(app.source_entry.width(), app.destination_entry.width())
        self.assertFalse(app.open_button.isEnabled())
        self.assertFalse(app.cancel_button.isEnabled())

    def test_appearance_row_fills_space_below_title(self):
        app = self.app
        app.resize(1000, 900)
        QTest.qWait(60)
        self.assertGreater(app.theme_combo.y(), app.brand_label.geometry().bottom())
        self.assertLessEqual(app.theme_combo.y() - app.brand_label.geometry().bottom(), 12)
        self.assertEqual(app.theme_combo.y(), app.zoom_combo.y())
        self.assertEqual(app.theme_combo.height(), app.zoom_combo.height())
        self.assertGreater(app.intro_label.y(), app.theme_combo.geometry().bottom())
        self.assertLessEqual(app.intro_label.y() - app.theme_combo.geometry().bottom(), 16)

    def test_appearance_controls_follow_resize_and_keep_tab_order(self):
        for size in (100, 200, 400, 100):
            self.app.zoom_combo.setCurrentText(f'{size}%')
            self.app.resize(440, 640)
            QTest.qWait(70)
            self.app.theme_combo.setFocus()
            QTest.qWait(20)
            QTest.keyClick(self.app.theme_combo, Qt.Key.Key_Tab)
            self.assertTrue(self.app.zoom_combo.hasFocus())
            self.assertLess(self.app.theme_combo.geometry().right(), self.app.body.width())
            self.assertLess(self.app.zoom_combo.geometry().right(), self.app.body.width())
            self.assertGreater(self.app.intro_label.y(), self.app.zoom_combo.geometry().bottom())

    def test_picker_controls_set_paths(self):
        with patch("foldertally_desktop.QFileDialog.getExistingDirectory", return_value="C:/Example"):
            self.app.source_browse.click()
            self.app.destination_browse.click()
        self.assertEqual(self.app.source_entry.text(), "C:/Example")
        self.assertEqual(self.app.destination_entry.text(), "C:/Example")

    def test_controls_have_accessible_names_roles_actions_and_values(self):
        for widget in self.app.tab_widgets:
            interface = QAccessible.queryAccessibleInterface(widget)
            self.assertIsNotNone(interface)
            self.assertTrue(interface.text(QAccessible.Text.Name), widget.objectName())
            self.assertNotEqual(interface.role(), QAccessible.Role.Client, widget.objectName())
        interface = QAccessible.queryAccessibleInterface(self.app.start_button)
        self.assertIn("Press", interface.actionInterface().actionNames())
        self.app.source_entry.setText("C:/Example")
        source = QAccessible.queryAccessibleInterface(self.app.source_entry)
        self.assertEqual(source.text(QAccessible.Text.Value), "C:/Example")
        self.assertTrue(QAccessible.queryAccessibleInterface(self.app.result_entry).state().readOnly)

    def test_keyboard_tab_and_mnemonic_validation(self):
        app = self.app
        app.source_entry.setFocus()
        QTest.qWait(100)
        QTest.keyClick(app.source_entry, Qt.Key.Key_Tab)
        QTest.qWait(20)
        self.assertTrue(app.source_browse.hasFocus())
        QTest.keyClick(app.source_browse, Qt.Key.Key_Backtab)
        self.assertTrue(app.source_entry.hasFocus())
        QTest.keyClick(app, Qt.Key.Key_C, Qt.KeyboardModifier.AltModifier)
        QTest.qWait(180)
        self.assertEqual(app.status_text, "Check your folder selection")
        self.assertTrue(app.source_entry.hasFocus())
        self.assertIsNone(app.process)

    def test_all_formats_and_memory_values(self):
        for button, expected in zip(self.app.format_buttons, ("txt", "json", "pdf")):
            button.click()
            self.assertEqual(self.app.format_group.checkedButton().property("format"), expected)
        self.assertEqual([self.app.memory_combo.itemData(i) for i in range(4)], [256, 512, 1024, 2048])

    def test_status_announcements_are_deduplicated(self):
        announcements = []
        self.app.announced.connect(announcements.append)
        self.app.set_status("Report ready", "Saved successfully")
        self.app.set_status("Report ready", "Saved successfully")
        self.assertEqual(announcements, ["Report ready. Saved successfully"])
        self.assertEqual(QAccessible.queryAccessibleInterface(self.app.status_label).text(QAccessible.Text.Name), "Report ready")

    def test_high_contrast_removes_custom_colors(self):
        with patch("foldertally_desktop.high_contrast_enabled", return_value=True):
            self.app._theme()
        self.assertEqual(self.app.styleSheet(), "")

    def test_theme_switch_is_deferred_and_preserves_focus_geometry(self):
        for theme in ('light', 'dark', 'system'):
            self.app.theme_combo.setCurrentIndex(self.app.theme_combo.findData(theme))
            QTest.qWait(80)
            self.assertEqual(self.app.preferences['theme'], theme)
            geometry = self.app.start_button.geometry()
            self.app.start_button.setFocus()
            QTest.qWait(20)
            self.assertEqual(self.app.start_button.geometry(), geometry)
            self.app.theme_combo.setFocus()
            QTest.qWait(20)
            self.assertEqual(self.app.start_button.geometry(), geometry)
        self.assertFalse(hasattr(self.app, 'author_label'))

    def test_appearance_preferences_survive_relaunch(self):
        with tempfile.TemporaryDirectory(prefix='FolderTally_theme_') as base:
            state = Path(base) / 'window.json'
            self.app.state_path = state
            self.app.theme_combo.setCurrentIndex(2)
            self.app.zoom_combo.setCurrentIndex(1)
            QTest.qWait(80)
            self.app.remember_monitor()
            reopened = FolderTallyApp(state_path=state)
            try:
                self.assertEqual(reopened.theme_combo.currentData(), 'dark')
                self.assertEqual(reopened.zoom_combo.currentText(), '125%')
                self.assertEqual(reopened.effective_theme, 'dark')
            finally:
                reopened.close()
                reopened.deleteLater()
            self.app.state_path = None

    def test_close_has_no_exit_modal_and_declined_cancellation_stays_open(self):
        self.app.process = object()
        with patch.object(self.app, 'message', return_value=False):
            self.assertFalse(self.app.close())
        self.app.process = None
        with patch('foldertally_desktop.QMessageBox.exec', side_effect=AssertionError('Unexpected exit dialog')):
            self.assertTrue(self.app.close())
        self.assertFalse(self.app.isVisible())

    def test_about_identifies_publisher_and_current_license(self):
        with patch.object(self.app, '_document') as document:
            self.app.about()
        title, text = document.call_args.args
        self.assertEqual(title, 'About FolderTally')
        self.assertIn('Published by PradaFit', text)
        self.assertIn('Copyright (C) 2026 PradaFit', text)
        self.assertIn('Source-available noncommercial or separate commercial license', text)
        self.assertIn('FolderTally Noncommercial License', text)

    def test_close_waits_for_worker_cleanup(self):
        self.app.process = object()
        with patch.object(self.app, 'message', return_value=True), patch.object(self.app, 'cancel') as cancel:
            self.assertFalse(self.app.close())
        cancel.assert_called_once()
        self.assertTrue(self.app.isVisible())
        self.app.process = None
        self.app._finish({'kind': 'cancelled'})
        self.assertFalse(self.app.isVisible())

    def test_zoom_and_narrow_layout_keep_controls_reachable(self):
        self.app.resize(640, 640)
        for index in range(self.app.zoom_combo.count()):
            self.app.zoom_combo.setCurrentIndex(index)
            QTest.qWait(50)
            for button in self.app.interactive:
                self.assertGreaterEqual(button.width(), button.sizeHint().width(), button.objectName())
            self.app.memory_combo.setFocus()
            QTest.qWait(20)
            visible = self.app.memory_combo.mapTo(self.app.scroll.viewport(), self.app.memory_combo.rect().center())
            self.assertTrue(self.app.scroll.viewport().rect().contains(visible), (index, visible))
        self.assertEqual(self.app.font().pointSizeF(), self.app.base_font.pointSizeF() * 4)

    def test_open_only_report_types_and_missing_report(self):
        with tempfile.TemporaryDirectory(prefix="FolderTally_ui_") as base:
            path = Path(base) / "sample.txt"
            path.touch()
            self.app.last_report = path
            with patch("foldertally_desktop.os.startfile") as opened:
                self.app.open_report()
                self.app.show_folder()
                self.app.last_report = Path(base) / "unsafe.exe"
                self.app.open_report()
            self.assertEqual([call.args[0] for call in opened.call_args_list], [str(path), str(path.parent)])
            self.app.last_report = Path(base) / "missing.txt"
            with patch.object(self.app, "message") as error:
                self.app.open_report()
            error.assert_called_once()

    def test_dialogs_center_on_current_monitor(self):
        for screen in APP.screens():
            self.app.windowHandle().setScreen(screen)
            centered_on(self.app, screen)
            QTest.qWait(50)
            result = []
            def inspect():
                dialog = next(w for w in APP.topLevelWidgets() if isinstance(w, QDialog) and w.isVisible())
                delta = dialog.frameGeometry().center() - screen.availableGeometry().center()
                result.append((delta.x(), delta.y()))
                dialog.reject()
            QTimer.singleShot(70, inspect)
            self.app.help()
            self.assertTrue(all(abs(x) <= 2 for x in result[0]), (screen.name(), result))

    def test_close_when_worker_finishes_during_confirmation(self):
        self.app.process = object()
        def answer(*_args, **_kwargs):
            self.app.process = None
            return True
        with patch.object(self.app, "message", side_effect=answer):
            self.assertTrue(self.app.close())

    def test_monitor_persists_and_reopens_centered_on_each_display(self):
        with tempfile.TemporaryDirectory(prefix="FolderTally_monitor_") as base:
            state = Path(base) / "window.json"
            for screen in APP.screens():
                self.app.state_path = state
                self.app.windowHandle().setScreen(screen)
                centered_on(self.app, screen)
                self.app.move(self.app.x() + 37, self.app.y() + 21)
                QTest.qWait(80)
                self.app.remember_monitor()
                self.assertEqual(load_monitor(state), monitor_id(screen))
                reopened = FolderTallyApp(state_path=state)
                try:
                    reopened.show()
                    QTest.qWait(50)
                    self.assertEqual(reopened.screen(), screen)
                    delta = reopened.frameGeometry().center() - screen.availableGeometry().center()
                    self.assertLessEqual(max(abs(delta.x()), abs(delta.y())), 2)
                finally:
                    reopened.close()
                    reopened.deleteLater()
                    APP.processEvents()
            self.app.state_path = None

    def _wait(self):
        deadline = time.monotonic() + 30
        while self.app.process is not None and time.monotonic() < deadline:
            QTest.qWait(20)
        self.assertIsNone(self.app.process, "Worker did not finish")

    def test_real_scan_and_cancel(self):
        with tempfile.TemporaryDirectory(prefix="FolderTally_ui_") as base:
            source, output = Path(base) / "source", Path(base) / "reports"
            source.mkdir()
            output.mkdir()
            (source / "sample.txt").write_bytes(b"abc")
            self.app.source_entry.setText(str(source))
            self.app.destination_entry.setText(str(output))
            self.app.format_buttons[1].click()
            self.app.start_button.click()
            self.assertFalse(self.app.source_entry.isEnabled())
            self._wait()
            self.assertEqual(self.app.status_text, "Report ready", self.app.detail_label.text())
            self.assertEqual(self.app.metrics["size"].text(), "Total file size: 3 B")
            self.assertTrue(self.app.open_button.isEnabled())
            self.app.start_button.click()
            self.app.cancel_button.click()
            self._wait()
            self.assertEqual(self.app.status_text, "Scan cancelled", self.app.detail_label.text())
            self.assertEqual(len(list(output.iterdir())), 1)


if __name__ == "__main__":
    unittest.main()
