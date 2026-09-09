# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Build a new private artifact directory without replacing prior artifacts."""

import hashlib
import importlib.metadata
import json
import os
import shutil
import subprocess
import sys
import tarfile
from datetime import datetime
from pathlib import Path

from PIL import Image, ImageDraw

ROOT = Path(__file__).resolve().parents[1]


def make_icon():
    # Original vector-style geometric mark, rasterized for the Windows icon.
    image = Image.new("RGBA", (256, 256), (0, 0, 0, 0))
    draw = ImageDraw.Draw(image)
    draw.rounded_rectangle((8, 8, 248, 248), radius=50, fill="#172B43")
    draw.polygon(((45, 69), (106, 69), (127, 92), (211, 92), (211, 191), (45, 191)), fill="#69B5FF")
    for left, top in ((80, 144), (117, 125), (154, 107)):
        draw.rounded_rectangle((left, top, left + 21, 170), radius=3, fill="#172B43")
    assets = ROOT / "assets"
    assets.mkdir(exist_ok=True)
    image.save(assets / "FolderTally.ico", sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])


def license_bundle(work):
    licenses = work / "licenses"
    licenses.mkdir()
    import reportlab
    import PyInstaller
    sources = {
        "Python.txt": Path(sys.base_prefix) / "LICENSE.txt",
        "ReportLab.txt": Path(reportlab.__file__).parent.parent / "reportlab-5.0.1.dist-info" / "licenses" / "LICENSE",
        "Bitstream-Vera.txt": Path(reportlab.__file__).parent / "fonts" / "bitstream-vera-license.txt",
        "PyInstaller.txt": Path(PyInstaller.__file__).parent.parent / "pyinstaller-6.22.2.dist-info" / "licenses" / "COPYING.txt",
        "Qt-6.11.2-notices.txt": ROOT / "packaging/licenses/Qt-6.11.2-notices.txt",
        "OpenSSL-3.5.8.txt": ROOT / "packaging/licenses/OpenSSL-3.5.8.txt",
        "Expat-2.8.2.txt": ROOT / "packaging/licenses/Expat-2.8.2.txt",
        "libffi.txt": ROOT / "packaging/licenses/libffi.txt",
    }
    # Wheel metadata layouts vary. Select only license files, never package
    # configurations or environment data.
    for package in ("pillow", "charset-normalizer", "pypdf"):
        dist = importlib.metadata.distribution(package)
        for item in dist.files or []:
            if "license" in str(item).lower() and ".dist-info/" in str(item).replace('\\', '/'):
                sources[f"{package}-{Path(item).name}"] = Path(dist.locate_file(item))
    for name, path in sources.items():
        if path.is_file():
            (licenses / name).write_bytes(path.read_bytes())
        else:
            raise FileNotFoundError(f"Required license not found: {path}")
    for entry in json.loads((ROOT / 'packaging/qt-sources.json').read_text(encoding='utf-8')):
        source = ROOT / '_Internal/third-party-sources' / entry['filename']
        if sha256(source) != entry['sha256']:
            raise ValueError(f"Source archive mismatch: {source.name}")
        with tarfile.open(source) as archive:
            for member in archive:
                if member.isfile() and '/LICENSES/' in member.name and member.name.endswith('.txt'):
                    name = entry['filename'].split('-everywhere')[0] + '-' + Path(member.name).name
                    with archive.extractfile(member) as text:
                        (licenses / name).write_bytes(text.read())
    return licenses


def sha256(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    if os.name != "nt" or sys.maxsize <= 2**32:
        raise SystemExit("Build on Windows with 64-bit Python.")
    stamp = datetime.now().strftime("%Y%m%d-%H%M%S")
    work = ROOT / "_Internal" / "build" / stamp
    output = ROOT / "dist" / f"FolderTally-Portable-{stamp}"
    work.mkdir(parents=True, exist_ok=False)
    output.mkdir(parents=True, exist_ok=False)
    make_icon()
    licenses = license_bundle(work)
    command = [sys.executable, "-m", "PyInstaller", "--onedir", "--windowed", "--noupx",
               "--name", "FolderTally", "--distpath", str(output), "--workpath", str(work / "pyinstaller"),
               "--specpath", str(work), "--icon", str(ROOT / "assets/FolderTally.ico"),
               "--manifest", str(ROOT / "packaging/FolderTally.manifest"),
               "--version-file", str(ROOT / "packaging/version_info.txt"),
               "--collect-data", "reportlab", "--add-data", f"{ROOT / 'assets/FolderTally.ico'};assets",
               "--additional-hooks-dir", str(ROOT / 'packaging/hooks')]
    for module in ("pip", "pip_audit", "psutil", "pytest", "numpy", "matplotlib", "tkinter", "_tkinter",
                   "PySide6.QtTest", "PySide6.QtNetwork", "PySide6.QtSvg", "PySide6.QtSvgWidgets"):
        command.extend(["--exclude-module", module])
    command.append(str(ROOT / "FolderTallyGUI.py"))
    with (work / "build.log").open("w", encoding="utf-8") as log:
        subprocess.run(command, cwd=ROOT, stdout=log, stderr=subprocess.STDOUT, check=True)
    portable = output / 'FolderTally'
    for name in ('LICENSE', 'THIRD_PARTY_NOTICES.md', 'ACCESSIBILITY.md', 'SECURITY.md'):
        shutil.copy2(ROOT / name, portable / name)
    shutil.copytree(licenses, portable / 'licenses')
    shutil.copy2(ROOT / 'packaging/LIBRARY_REPLACEMENT.md', portable / 'LIBRARY_REPLACEMENT.md')
    source_dir = portable / 'sources'
    source_dir.mkdir()
    source_entries = json.loads((ROOT / 'packaging/qt-sources.json').read_text(encoding='utf-8'))
    for entry in source_entries:
        shutil.copy2(ROOT / '_Internal/third-party-sources' / entry['filename'], source_dir / entry['filename'])
    shutil.copy2(ROOT / 'packaging/qt-sources.json', source_dir / 'qt-sources.json')
    exe = portable / 'FolderTally.exe'
    digest = sha256(exe)
    files = {p.relative_to(portable).as_posix(): sha256(p) for p in sorted(portable.rglob('*')) if p.is_file()}
    (portable / 'SHA256SUMS.txt').write_text(''.join(f'{value}  {name}\n' for name, value in files.items()), encoding='utf-8')
    inputs = [*ROOT.glob('*.py'), ROOT / 'LICENSE', ROOT / 'THIRD_PARTY_NOTICES.md', ROOT / 'ACCESSIBILITY.md',
              ROOT / 'README.md', ROOT / 'CHANGELOG.md', ROOT / 'SECURITY.md', ROOT / 'CONTRIBUTING.md',
              ROOT / 'requirements-build.txt', ROOT / 'requirements.txt', ROOT / 'Build-Portable.ps1', ROOT / '.gitignore']
    for directory in ('packaging', 'tests', 'tools', 'assets', '.github'):
        inputs.extend((ROOT / directory).rglob('*'))
    source_hashes = {p.relative_to(ROOT).as_posix(): sha256(p) for p in sorted(inputs) if p.is_file() and '__pycache__' not in p.parts}
    metadata = {"python": sys.version, "packages": {p: importlib.metadata.version(p) for p in
                ("pyinstaller", "pyinstaller-hooks-contrib", "reportlab", "pillow", "charset-normalizer", "pypdf", "PySide6-Essentials", "shiboken6")},
                "exe_sha256": digest, "bytes": exe.stat().st_size, "architecture": "x64", "signed": False,
                "mode": "onedir", "exe": str(exe), "source_inputs": source_hashes, "files": files,
                "corresponding_sources": source_entries}
    (work / "build-metadata.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    with (work / 'build.log').open('a', encoding='utf-8') as log:
        log.write(f'\nCompleted EXE SHA256: {digest}\nPackage: {portable}\n')
    print(f"EXE: {exe}\nSHA256: {digest}\nBUILD: {work}")


if __name__ == "__main__":
    main()
