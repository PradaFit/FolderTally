# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Inspect the onedir PE, external runtime, checksums, and embedded code."""
import hashlib
import json
from pathlib import Path
import sys
from types import CodeType

import pefile
from PyInstaller.archive.readers import CArchiveReader


def main():
    path = Path(sys.argv[1]).resolve(strict=True)
    pe = pefile.PE(str(path))
    manifests = [pe.get_data(item.data.struct.OffsetToData, item.data.struct.Size).decode("utf-8")
                 for kind in pe.DIRECTORY_ENTRY_RESOURCE.entries if kind.id == 24
                 for entry in kind.directory.entries for item in entry.directory.entries]
    archive = CArchiveReader(str(path))
    portable = path.parent
    runtime = portable / '_internal'
    files = [p for p in portable.rglob('*') if p.is_file()]
    native_names = {p.name.lower() for p in files if p.suffix.lower() in ('.dll', '.pyd', '.exe')}
    pyz = archive.open_embedded_archive("PYZ.pyz")
    modules = pyz.toc
    def normalized(code):
        return code.replace(co_filename="", co_consts=tuple(normalized(item) if isinstance(item, CodeType) else item for item in code.co_consts))
    source_root = Path(__file__).resolve().parents[1]
    source_matches = {}
    for module in ("FolderTally", "foldertally_desktop", "foldertally_service", "foldertally_window_state", "foldertally_pdf_accessibility", "foldertally_theme"):
        compiled = compile((source_root / (module + '.py')).read_text(encoding='utf-8'), '', 'exec', dont_inherit=True)
        source_matches[module] = normalized(compiled) == normalized(pyz.extract(module))
    with path.open("rb") as stream:
        digest = hashlib.file_digest(stream, "sha256").hexdigest()
    result = {
        "exe": str(path), "sha256": digest, "bytes": path.stat().st_size,
        "x64": pe.FILE_HEADER.Machine == 0x8664, "windowed": pe.OPTIONAL_HEADER.Subsystem == 2,
        "standard_user": any('level="asInvoker"' in text for text in manifests),
        "PerMonitorV2": any("PerMonitorV2" in text for text in manifests),
        "DEP": bool(pe.OPTIONAL_HEADER.DllCharacteristics & 0x100),
        "ASLR": bool(pe.OPTIONAL_HEADER.DllCharacteristics & 0x40),
        "high_entropy_ASLR": bool(pe.OPTIONAL_HEADER.DllCharacteristics & 0x20),
        "CFG": bool(pe.OPTIONAL_HEADER.DllCharacteristics & 0x4000),
        "no_local_command_notes": not any("FolderTally_Cmds" in name for name in archive.toc),
        "no_private_evidence": not any(part.lower() in ('_verification', 'verification', 'build-records')
                                       or part in ('_Internal', 'info1.txt', 'FolderTally_Cmds.txt')
                                       for p in files for part in p.relative_to(portable).parts),
        "no_development_packages": not any(name in modules for name in ("pip", "pip_audit", "psutil", "defusedxml", "tkinter", "PySide6.QtTest")),
        "qt_accessible_ui": "foldertally_desktop" in modules and (runtime / 'PySide6/Qt6Widgets.dll').is_file(),
        "external_replaceable_qt": all((runtime / 'PySide6' / name).is_file() for name in ('Qt6Core.dll', 'Qt6Gui.dll', 'Qt6Widgets.dll')),
        "unused_qt_excluded": not any(name in native_names for name in ('qt6network.dll', 'qt6svg.dll', 'qt6test.dll', 'opengl32sw.dll')),
        "current_source_matches": source_matches,
        "licenses": [p.name for p in (portable / 'licenses').iterdir() if p.is_file()],
    }
    expected_names = set()
    for line in (portable / 'SHA256SUMS.txt').read_text(encoding='utf-8').splitlines():
        expected, name = line.split('  ', 1)
        target = (portable / name).resolve(strict=True)
        assert target.is_relative_to(portable) and name not in expected_names
        expected_names.add(name)
        with target.open('rb') as stream:
            assert hashlib.file_digest(stream, 'sha256').hexdigest() == expected, name
    result['checksums_match'] = expected_names == {p.relative_to(portable).as_posix() for p in files if p.name != 'SHA256SUMS.txt'}
    qt_imports = {}
    for file in files:
        if file.suffix.lower() in ('.dll', '.pyd', '.exe'):
            with pefile.PE(str(file), fast_load=True) as native:
                native.parse_data_directories(directories=[pefile.DIRECTORY_ENTRY['IMAGE_DIRECTORY_ENTRY_IMPORT']])
                imports = [item.dll.decode('ascii').lower() for item in getattr(native, 'DIRECTORY_ENTRY_IMPORT', [])]
            qt_imports[file.relative_to(portable).as_posix()] = [name for name in imports if name.startswith('qt6')]
    result['qt_native_imports_resolve'] = all(name in native_names for imports in qt_imports.values() for name in imports)
    result['native_qt_imports'] = {name: imports for name, imports in qt_imports.items() if imports}
    for key in ("x64", "windowed", "standard_user", "PerMonitorV2", "DEP", "ASLR", "high_entropy_ASLR",
                "CFG", "no_local_command_notes", "no_private_evidence", "no_development_packages", "qt_accessible_ui",
                "external_replaceable_qt", "unused_qt_excluded", "checksums_match", "qt_native_imports_resolve"):
        assert result[key], key
    assert len(result["licenses"]) >= 8
    assert all(name in result['licenses'] for name in ('pillow-LICENSE', 'pypdf-LICENSE', 'charset-normalizer-LICENSE',
                                                      'pyside-setup-LGPL-3.0-only.txt', 'qtbase-GPL-3.0-only.txt'))
    assert all(source_matches.values()), source_matches
    output = Path(sys.argv[2]) if len(sys.argv) > 2 else Path(__file__).resolve().parents[1] / "_Internal/verification/artifact.json"
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(result, indent=2), encoding="utf-8")
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()
