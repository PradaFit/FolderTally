# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Portable desktop launcher; workers start before the UI is imported."""
import multiprocessing

if __name__ == "__main__":
    multiprocessing.freeze_support()
    from foldertally_desktop import main
    raise SystemExit(main())
