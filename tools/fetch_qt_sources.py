# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Fetch hash-pinned upstream source archives into a private build cache."""
import hashlib
import json
from pathlib import Path
import shutil
import urllib.request

ROOT = Path(__file__).resolve().parents[1]


def main():
    destination = ROOT / '_Internal/third-party-sources'
    destination.mkdir(parents=True, exist_ok=True)
    for entry in json.loads((ROOT / 'packaging/qt-sources.json').read_text(encoding='utf-8')):
        target = destination / entry['filename']
        if target.name != entry['filename'] or not entry['url'].startswith('https://download.qt.io/'):
            raise ValueError('Unexpected source manifest entry')
        if not target.exists():
            print(f"Download: {entry['url']} -> {target}; SHA-256 must match the manifest.", flush=True)
            with urllib.request.urlopen(entry['url'], timeout=60) as response, target.open('xb') as stream:
                shutil.copyfileobj(response, stream)
        with target.open('rb') as stream:
            digest = hashlib.file_digest(stream, 'sha256').hexdigest()
        if digest != entry['sha256']:
            raise ValueError(f'Archive checksum mismatch: {target.name}. Existing files are not overwritten.')
        print(f'Verified: {target.name} {digest}', flush=True)


if __name__ == '__main__':
    main()
