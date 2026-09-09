# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Run a supplied local veraPDF CLI against explicitly selected test reports."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess


def digest(path):
    with path.open('rb') as stream:
        return hashlib.file_digest(stream, 'sha256').hexdigest()


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument('--java', type=Path, required=True)
    parser.add_argument('--validator', type=Path, required=True)
    parser.add_argument('--exe', type=Path, required=True, help='Build being verified; not executed by this check')
    parser.add_argument('--output', type=Path, required=True)
    parser.add_argument('pdfs', type=Path, nargs='+')
    args = parser.parse_args()
    if args.output.exists():
        raise SystemExit('Validation output must be a new file.')
    pdfs = [p.resolve(strict=True) for p in args.pdfs]
    command = [str(args.java.resolve(strict=True)), '-jar', str(args.validator.resolve(strict=True)),
               '--flavour', 'ua1', '--format', 'json', *(str(p) for p in pdfs)]
    result = subprocess.run(command, capture_output=True, encoding='utf-8',
                            creationflags=getattr(subprocess, 'CREATE_NO_WINDOW', 0), timeout=120)
    report = json.loads(result.stdout)
    jobs = report['report']['jobs']
    passed = result.returncode == 0 and len(jobs) == len(pdfs) and all(
        job.get('validationResult') and all(item.get('compliant') is True and item.get('jobEndStatus') == 'normal'
        for item in job['validationResult']) for job in jobs)
    record = {'exe_sha256': digest(args.exe), 'validator_jar_sha256': digest(args.validator),
              'pdf_sha256': {str(p): digest(p) for p in pdfs}, 'machine_checks_passed': passed,
              'human_screen_reader_review': 'not performed', 'stderr': result.stderr, 'validator_report': report}
    args.output.parent.mkdir(parents=True, exist_ok=True)
    with args.output.open('x', encoding='utf-8') as stream:
        json.dump(record, stream, indent=2)
    print(f"PDF/UA-1 machine validation: {len(jobs)} reports; {'PASS' if passed else 'FAIL'}. Human review is separate.")
    if not passed:
        raise SystemExit(1)


if __name__ == '__main__':
    main()
