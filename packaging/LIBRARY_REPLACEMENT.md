# Qt library sources and replacement

FolderTally uses the community LGPL-3.0 option for Qt Core, Gui, Widgets, PySide6, and Shiboken6, version 6.11.2. No commercial Qt license is claimed. FolderTally's first-party license does not limit the rights these libraries grant, including modification, replacement/relinking, and reverse engineering needed to debug a modified library.

## Sources supplied with the portable app

`sources/qtbase-everywhere-src-6.11.2.tar.xz` contains Qt Base source, bundled third-party source, and its CMake/configuration scripts. `sources/pyside-setup-everywhere-src-6.11.2.tar.xz` contains the bindings, Shiboken, and their build scripts. Both are unmodified upstream release archives. Their URLs and SHA-256 checksums are in `sources/qt-sources.json`; their file hashes also appear in `SHA256SUMS.txt`.

The runtime binaries come from the unmodified PyPI `PySide6-Essentials==6.11.2` and `shiboken6==6.11.2` Windows x64 wheels. FolderTally has not independently reproduced those upstream wheel builds bit for bit. A release review must check the source/binary provenance and applicable license obligations; equal version numbers alone are not a legal certification.

## Replace libraries without rebuilding FolderTally

1. Close FolderTally and make a separate copy of the complete portable folder. Keep the original for recovery.
2. Use ABI-compatible Windows x64 builds of the same Qt/PySide/Shiboken family. This package embeds CPython 3.14 x64. Follow the upstream build instructions in the archives and [Qt for Python build documentation](https://doc.qt.io/qtforpython-6/building_from_source/index.html).
3. In the test copy, replace the corresponding files under `_internal/PySide6`, including `Qt6Core.dll`, `Qt6Gui.dll`, `Qt6Widgets.dll`, the applicable `.pyd`/binding DLLs and matching `plugins/platforms/qwindows.dll`, `plugins/styles/qmodernwindowsstyle.dll`, and `plugins/imageformats/qico.dll`. Keep paths and filenames unchanged. If modifying Shiboken, replace its compatible DLL/extension under `_internal/shiboken6` as well.
4. Start that copy's `FolderTally.exe`. The application has no runtime signature or checksum gate that rejects modified libraries. Published checksums naturally no longer match your modified files. Test keyboard access, native folder dialogs, themes, TXT/JSON/PDF export, and cancellation.

To change Python modules beyond external extensions or use a different binding ABI, rebuild FolderTally against the modified packages. Source is provided under its separate application terms, which expressly preserve library debugging/relinking rights.

## Rebuild the application package

On Windows x64 with Python 3.14.7, create `.build-venv` and `.package-venv` at the repository root. Install `requirements-build.txt` in each. For modified libraries, install your compatible builds in `.package-venv` instead of the PyPI binding wheels. Run:

```powershell
.\.build-venv\Scripts\python.exe tools\fetch_qt_sources.py
.\Build-Portable.ps1
```

The build recipe in `tools/build_portable.py` creates an onedir package, not an installer. The hooks in `packaging/hooks` select native raster widgets and omit unused network, SVG, OpenGL-renderer, and translation plugins. If you change that selection, review the extra libraries and supply their corresponding sources and notices. For a modified library distribution, update the source manifest and ship your complete modified sources and build instructions, not the original archives alone.

For questions about the supplied source material, contact pradafitdev@gmail.com. Do not remove these instructions, source archives, or library notices when redistributing the portable package.
