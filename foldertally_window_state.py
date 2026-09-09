# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Bounded display preferences. No scan paths or report history."""
import json
import os
from pathlib import Path
import stat
import tempfile


def preferences_path():
    base = os.environ.get("LOCALAPPDATA")
    if not base or not Path(base).is_absolute():
        return None
    return Path(base) / "PradaFit" / "FolderTally" / "window.json"


def _regular_directory(path):
    info = path.stat(follow_symlinks=False)
    return stat.S_ISDIR(info.st_mode) and not getattr(info, "st_file_attributes", 0) & 0x400


THEMES = ("system", "light", "dark")
TEXT_SIZES = (100, 125, 150, 200, 300, 400)


def clean_preferences(data):
    data = data if isinstance(data, dict) else {}
    monitor = data.get("monitor", "")
    theme = data.get("theme", "system")
    size = data.get("text_size", 100)
    return {
        "monitor": monitor if isinstance(monitor, str) and len(monitor) <= 128 else "",
        "theme": theme if isinstance(theme, str) and theme in THEMES else "system",
        "text_size": size if type(size) is int and size in TEXT_SIZES else 100,
    }


def load_preferences(path):
    if path is None:
        return clean_preferences(None)
    try:
        info = path.stat(follow_symlinks=False)
        if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400 or info.st_size > 2048:
            return clean_preferences(None)
        with path.open("rb") as stream:
            data = json.loads(stream.read(2049).decode("utf-8"))
        return clean_preferences(data)
    except (OSError, ValueError, UnicodeError):
        return clean_preferences(None)


def load_monitor(path):
    return load_preferences(path)["monitor"]


def save_preferences(path, values):
    if (path is None or not isinstance(values, dict)
            or type(values.get("text_size")) is not int
            or values != clean_preferences(values)):
        return False
    temporary = None
    try:
        # Refuse redirected parent directories rather than writing through a
        # link. The normal per-user application directory remains supported.
        for directory in reversed(path.parent.parents):
            if directory.exists() and not _regular_directory(directory):
                return False
        path.parent.mkdir(parents=True, exist_ok=True)
        if not _regular_directory(path.parent):
            return False
        if path.exists():
            info = path.stat(follow_symlinks=False)
            if not stat.S_ISREG(info.st_mode) or getattr(info, "st_file_attributes", 0) & 0x400:
                return False
        with tempfile.NamedTemporaryFile(mode="w", encoding="utf-8", prefix=".window-", suffix=".tmp", dir=path.parent, delete=False) as stream:
            temporary = Path(stream.name)
            json.dump(values, stream, ensure_ascii=True)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
        temporary = None
        return True
    except OSError:
        return False
    finally:
        if temporary is not None:
            try:
                temporary.unlink(missing_ok=True)
            except OSError:
                pass  # A failed preference write must not prevent shutdown.


def save_monitor(path, name):
    if not isinstance(name, str) or not 0 < len(name) <= 128:
        return False
    values = load_preferences(path)
    values["monitor"] = name
    return save_preferences(path, values)


def choose_monitor(names, saved, fallback):
    if saved in names:
        return saved
    if fallback in names:
        return fallback
    return names[0] if names else ""


def centered_frame(work, size):
    """Coordinates are logical pixels and may have negative origins."""
    left, top, width, height = work
    frame_width, frame_height = size
    return left + max(0, (width - frame_width) // 2), top + max(0, (height - frame_height) // 2)
