# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Keep only the native Windows platform and ICO reader used by this app."""
from pathlib import Path
from PyInstaller.utils.hooks.qt import add_qt6_dependencies

hiddenimports, binaries, datas = add_qt6_dependencies(__file__)
binaries = [(source, target) for source, target in binaries
            if Path(source).name.lower() in ('qwindows.dll', 'qico.dll')]
datas = []  # The application is English-only and does not load Qt translations.
