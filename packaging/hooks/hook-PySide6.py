# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""FolderTally uses raster widgets, not optional OpenGL/ANGLE renderers."""
from PyInstaller.utils.hooks.qt import ensure_single_qt_bindings_package

ensure_single_qt_bindings_package('PySide6')
hiddenimports = ['shiboken6', 'inspect', 'PySide6.support.deprecated']
