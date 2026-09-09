# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

import unittest
from foldertally_theme import PALETTES


def luminance(color):
    channels = [int(color[index:index + 2], 16) / 255 for index in (1, 3, 5)]
    linear = [v / 12.92 if v <= 0.04045 else ((v + 0.055) / 1.055) ** 2.4 for v in channels]
    return sum(v * weight for v, weight in zip(linear, (0.2126, 0.7152, 0.0722)))


def contrast(first, second):
    a, b = sorted((luminance(first), luminance(second)))
    return (b + 0.05) / (a + 0.05)


class ThemeTests(unittest.TestCase):
    def test_active_text_contrast(self):
        for mode, colors in PALETTES.items():
            for foreground, background in (('text', 'panel'), ('text', 'page'), ('muted', 'page'),
                                           ('text', 'hover'), ('on_accent', 'accent')):
                with self.subTest(mode=mode, pair=(foreground, background)):
                    self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 4.5)

    def test_control_and_focus_contrast(self):
        for mode, colors in PALETTES.items():
            for foreground, background in (('border', 'panel'), ('border', 'page'), ('accent', 'panel'),
                                           ('accent', 'page'), ('on_accent', 'accent')):
                with self.subTest(mode=mode, pair=(foreground, background)):
                    self.assertGreaterEqual(contrast(colors[foreground], colors[background]), 3)
