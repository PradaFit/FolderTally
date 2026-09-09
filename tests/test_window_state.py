# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

import json
import tempfile
import unittest
from pathlib import Path
from unittest.mock import patch
from foldertally_window_state import (load_monitor, save_monitor, choose_monitor, centered_frame,
                                     preferences_path, load_preferences, save_preferences, clean_preferences)


class WindowStateTests(unittest.TestCase):
    def test_center_negative_origin_taskbar_and_oversized_frame(self):
        self.assertEqual(centered_frame((-1920, 24, 1920, 1056), (1000, 900)), (-1460, 102))
        self.assertEqual(centered_frame((0, 0, 800, 600), (1000, 900)), (0, 0))

    def test_missing_monitor_falls_back(self):
        self.assertEqual(choose_monitor(['a', 'b'], 'b', 'a'), 'b')
        self.assertEqual(choose_monitor(['a', 'b'], 'gone', 'b'), 'b')
        self.assertEqual(choose_monitor(['a'], 'gone', 'gone'), 'a')
        self.assertEqual(choose_monitor([], '', ''), '')

    def test_only_display_preferences_saved_and_replaced_atomically(self):
        with tempfile.TemporaryDirectory(prefix='FolderTally_state_') as base:
            path = Path(base) / 'prefs' / 'window.json'
            self.assertEqual(load_monitor(path), '')
            self.assertTrue(save_monitor(path, 'monitor1'))
            self.assertTrue(save_monitor(path, 'monitor2'))
            self.assertEqual(json.loads(path.read_text()), {'monitor': 'monitor2', 'theme': 'system', 'text_size': 100})
            self.assertEqual(load_monitor(path), 'monitor2')
            self.assertEqual(list(path.parent.iterdir()), [path])

    def test_malformed_oversized_or_invalid_preferences_ignored(self):
        with tempfile.TemporaryDirectory(prefix='FolderTally_state_') as base:
            path = Path(base) / 'window.json'
            for data in (b'not json', b'[]', b'{"monitor": 42}', b'\xff', b' ' * 2049,
                         json.dumps({'monitor': 'x' * 129}).encode()):
                path.write_bytes(data)
                self.assertEqual(load_monitor(path), '')
            self.assertEqual(load_monitor(Path(base)), '')
            self.assertFalse(save_monitor(Path(base), 'name'))

    def test_io_errors_do_not_crash_or_replace_existing_preferences(self):
        with tempfile.TemporaryDirectory(prefix='FolderTally_state_') as base:
            path = Path(base) / 'window.json'
            self.assertTrue(save_monitor(path, 'original'))
            with patch('foldertally_window_state.os.replace', side_effect=PermissionError):
                self.assertFalse(save_monitor(path, 'new'))
            self.assertEqual(load_monitor(path), 'original')
            self.assertEqual(list(Path(base).iterdir()), [path])

    def test_redirected_parent_is_refused(self):
        with tempfile.TemporaryDirectory(prefix='FolderTally_state_') as base:
            with patch('foldertally_window_state._regular_directory', return_value=False):
                self.assertFalse(save_monitor(Path(base) / 'window.json', 'name'))
            self.assertEqual(list(Path(base).iterdir()), [])

    def test_invalid_local_appdata_disables_storage(self):
        with patch.dict('os.environ', {'LOCALAPPDATA': 'relative'}):
            self.assertIsNone(preferences_path())
        self.assertEqual(load_monitor(None), '')
        self.assertFalse(save_monitor(None, 'monitor'))

    def test_legacy_monitor_preferences_and_strict_appearance_values(self):
        with tempfile.TemporaryDirectory(prefix='FolderTally_state_') as base:
            path = Path(base) / 'window.json'
            path.write_text('{"monitor": "old display"}', encoding='utf-8')
            self.assertEqual(load_preferences(path), {'monitor': 'old display', 'theme': 'system', 'text_size': 100})
            for theme in ('system', 'light', 'dark'):
                values = {'monitor': 'display', 'theme': theme, 'text_size': 200}
                self.assertTrue(save_preferences(path, values))
                self.assertTrue(save_monitor(path, 'second display'))
                self.assertEqual(load_preferences(path), dict(values, monitor='second display'))
            for field, invalid in (('text_size', True), ('text_size', 100.0), ('text_size', 999),
                                   ('theme', ['dark']), ('theme', 'unknown'), ('scan_path', 'private')):
                values = dict(clean_preferences(None), **{field: invalid})
                self.assertFalse(save_preferences(path, values), values)
            self.assertEqual(clean_preferences({'theme': [], 'text_size': True}), clean_preferences(None))
