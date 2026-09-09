# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Create app-only screenshots from an owned synthetic scan, never user data."""
import hashlib
import json
import multiprocessing
from pathlib import Path
import sys
import time

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT))


def main():
    from PySide6.QtCore import Qt
    from PySide6.QtWidgets import QApplication
    from PySide6.QtTest import QTest
    from foldertally_desktop import FolderTallyApp

    demo = Path('C:/FolderTally-Demo')
    destination = ROOT / 'assets/screenshots'
    if demo.exists() or destination.exists():
        raise SystemExit('Demo and screenshot destinations must be new. Existing files are never replaced.')
    print(f'Create synthetic fixtures: {demo}; capture only the application client into {destination}.', flush=True)
    source, reports = demo / 'SampleData', demo / 'Reports'
    source.mkdir(parents=True)
    reports.mkdir()
    for index, (name, filename) in enumerate((('Projects', 'Project-plan.txt'), ('Documents', 'Team-notes.txt'),
            ('Media', 'Catalog.txt'), ('Backups', 'Backup-index.txt'), ('Logs', 'Activity.txt'), ('Archives', 'Archive-index.txt'))):
        folder = source / name
        folder.mkdir()
        for number in range(1, 5):
            path = folder / f'{number:02d}-{filename}'
            content = b'Synthetic demo data.\r\n' * (index + 1) * number * 100
            with path.open('xb') as stream:
                stream.write(content)
    app = QApplication([])
    app.setQuitOnLastWindowClosed(False)
    window = FolderTallyApp(remember=False)
    # Render the real widget tree without the monitor's native height cap.
    # This is an app-only full-window capture, not a desktop capture or a stitch.
    window.setAttribute(Qt.WidgetAttribute.WA_DontShowOnScreen, True)
    window.source_entry.setText(str(source))
    window.destination_entry.setText(str(reports))
    window.format_buttons[0].setChecked(True)
    window.show()
    window.start_button.click()
    deadline = time.monotonic() + 30
    while window.process is not None and time.monotonic() < deadline:
        QTest.qWait(100)
    if window.process is not None or window.status_text != 'Report ready':
        raise RuntimeError(f'Demo scan did not finish: {window.status_text}')
    destination.mkdir(parents=True)
    results = []
    for mode, scale, width, height, filename in (('dark', 100, 1100, 1000, 'hero-dark.png'),
                                                ('light', 150, 1300, 1300, 'workflow-light.png')):
        window.theme_combo.setCurrentIndex(window.theme_combo.findData(mode))
        window.zoom_combo.setCurrentText(f'{scale}%')
        window.resize(width, height)
        window.scroll.verticalScrollBar().setValue(0)
        window.start_button.setFocus()
        QTest.qWait(500)
        window.scroll.verticalScrollBar().setValue(0)
        QTest.qWait(100)
        if window.scroll.verticalScrollBar().maximum():
            raise RuntimeError(f'Full capture is clipped: {window.size()}, scroll={window.scroll.verticalScrollBar().maximum()}')
        target = destination / filename
        if not window.grab().save(str(target), 'PNG'):
            raise RuntimeError('Screenshot could not be saved.')
        results.append({'path': target.relative_to(ROOT).as_posix(), 'theme': mode, 'text_size': scale,
                        'sha256': hashlib.sha256(target.read_bytes()).hexdigest(), 'completed': True})
    window.close()
    record = ROOT / '_Internal/verification/demo-screenshots.json'
    record.parent.mkdir(parents=True, exist_ok=True)
    record.write_text(json.dumps({'source': str(source), 'reports': str(reports), 'screenshots': results}, indent=2), encoding='utf-8')
    print(json.dumps(results, indent=2))


if __name__ == '__main__':
    multiprocessing.freeze_support()
    main()
