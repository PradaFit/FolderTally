# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Compatibility entry point for the Windows accessibility smoke test."""
from pathlib import Path
import subprocess
import sys


def main():
    if len(sys.argv) != 2:
        raise SystemExit("Usage: python tools/smoke_portable.py path/to/FolderTally.exe")
    script = Path(__file__).with_name("smoke_accessible.ps1")
    subprocess.run(["pwsh", "-NoProfile", "-File", str(script), "-Exe", sys.argv[1]], check=True)


if __name__ == "__main__":
    main()
