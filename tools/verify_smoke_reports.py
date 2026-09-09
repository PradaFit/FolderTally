# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Parse reports from a completed native EXE smoke test."""
import json
from pathlib import Path
import sys
from pypdf import PdfReader


def main():
    results = json.loads(Path(sys.argv[1]).read_text(encoding='utf-8-sig'))
    paths = {item['check'].split()[0]: Path(item['path']) for item in results['checks'] if 'path' in item}
    assert set(paths) == {'txt', 'json', 'pdf'}
    assert len(set(paths.values())) == 3
    data = json.loads(paths['json'].read_text(encoding='utf-8'))
    assert data['total_size_bytes'] == 18
    assert data['counts']['files'] == 2 and data['counts']['folders'] == 2
    assert any('Résumé_漢.json' in item['path'] for item in data['entries'])
    text = paths['txt'].read_text(encoding='utf-8')
    assert 'Files: 2' in text and 'Résumé_漢.json' in text
    pdf = PdfReader(paths['pdf'])
    assert pdf.trailer['/Root']['/Lang'] == 'en-US'
    assert pdf.trailer['/Root']['/MarkInfo']['/Marked']
    assert '/StructTreeRoot' in pdf.trailer['/Root']
    text = '\n'.join(page.extract_text() for page in pdf.pages)
    assert 'Notes.txt' in text and '\\u6F22' in text
    assert results['exited_cleanly']
    print('Native TXT, JSON, PDF contents and PDF tags verified; 2 files, 2 folders, 18 bytes.')


if __name__ == '__main__':
    main()
