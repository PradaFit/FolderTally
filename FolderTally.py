# SPDX-License-Identifier: GPL-3.0-only
# Copyright (C) 2026 PradaFit

import argparse
import ctypes
import html
import json
import mimetypes
import os
import re
import shutil
import subprocess
import sys
import tempfile
import time
import uuid
from datetime import datetime
from pathlib import Path

PROGRAM = "FolderTally"
VERSION = "1.0.0"
MAX_RAM_MB = 2048
REPARSE_POINT = 0x00000400
_JOB_HANDLE = None


class GUID(ctypes.Structure):
    _fields_ = [
        ("Data1", ctypes.c_ulong),
        ("Data2", ctypes.c_ushort),
        ("Data3", ctypes.c_ushort),
        ("Data4", ctypes.c_ubyte * 8),
    ]


class IO_COUNTERS(ctypes.Structure):
    _fields_ = [
        ("ReadOperationCount", ctypes.c_ulonglong),
        ("WriteOperationCount", ctypes.c_ulonglong),
        ("OtherOperationCount", ctypes.c_ulonglong),
        ("ReadTransferCount", ctypes.c_ulonglong),
        ("WriteTransferCount", ctypes.c_ulonglong),
        ("OtherTransferCount", ctypes.c_ulonglong),
    ]


class PROCESS_MEMORY_COUNTERS_EX(ctypes.Structure):
    _fields_ = [
        ("cb", ctypes.c_ulong),
        ("PageFaultCount", ctypes.c_ulong),
        ("PeakWorkingSetSize", ctypes.c_size_t),
        ("WorkingSetSize", ctypes.c_size_t),
        ("QuotaPeakPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPagedPoolUsage", ctypes.c_size_t),
        ("QuotaPeakNonPagedPoolUsage", ctypes.c_size_t),
        ("QuotaNonPagedPoolUsage", ctypes.c_size_t),
        ("PagefileUsage", ctypes.c_size_t),
        ("PeakPagefileUsage", ctypes.c_size_t),
        ("PrivateUsage", ctypes.c_size_t),
    ]


class JOBOBJECT_BASIC_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("PerProcessUserTimeLimit", ctypes.c_longlong),
        ("PerJobUserTimeLimit", ctypes.c_longlong),
        ("LimitFlags", ctypes.c_ulong),
        ("MinimumWorkingSetSize", ctypes.c_size_t),
        ("MaximumWorkingSetSize", ctypes.c_size_t),
        ("ActiveProcessLimit", ctypes.c_ulong),
        ("Affinity", ctypes.c_size_t),
        ("PriorityClass", ctypes.c_ulong),
        ("SchedulingClass", ctypes.c_ulong),
    ]


class JOBOBJECT_EXTENDED_LIMIT_INFORMATION(ctypes.Structure):
    _fields_ = [
        ("BasicLimitInformation", JOBOBJECT_BASIC_LIMIT_INFORMATION),
        ("IoInfo", IO_COUNTERS),
        ("ProcessMemoryLimit", ctypes.c_size_t),
        ("JobMemoryLimit", ctypes.c_size_t),
        ("PeakProcessMemoryUsed", ctypes.c_size_t),
        ("PeakJobMemoryUsed", ctypes.c_size_t),
    ]


class DOCINFOW(ctypes.Structure):
    _fields_ = [
        ("cbSize", ctypes.c_int),
        ("lpszDocName", ctypes.c_wchar_p),
        ("lpszOutput", ctypes.c_wchar_p),
        ("lpszDatatype", ctypes.c_wchar_p),
        ("fwType", ctypes.c_ulong),
    ]


class SIZE(ctypes.Structure):
    _fields_ = [("cx", ctypes.c_long), ("cy", ctypes.c_long)]


class Frame:
    __slots__ = ("path", "rel", "depth", "iterator", "subtotal", "size_offset")

    def __init__(self, path, rel, depth, iterator, size_offset):
        self.path = path
        self.rel = rel
        self.depth = depth
        self.iterator = iterator
        self.subtotal = 0
        self.size_offset = size_offset


def guid_from_string(value):
    return GUID.from_buffer_copy(uuid.UUID(value).bytes_le)


def get_downloads_folder():
    fallback = Path.home() / "Downloads"
    if os.name != "nt":
        return fallback
    shell32 = ctypes.WinDLL("shell32", use_last_error=True)
    ole32 = ctypes.WinDLL("ole32", use_last_error=True)
    folder_id = guid_from_string("374DE290-123F-4565-9164-39C4925E467B")
    out = ctypes.c_void_p()
    shell32.SHGetKnownFolderPath.argtypes = [
        ctypes.POINTER(GUID),
        ctypes.c_ulong,
        ctypes.c_void_p,
        ctypes.POINTER(ctypes.c_void_p),
    ]
    shell32.SHGetKnownFolderPath.restype = ctypes.c_long
    ole32.CoTaskMemFree.argtypes = [ctypes.c_void_p]
    ole32.CoTaskMemFree.restype = None
    ole32.CoInitializeEx.argtypes = [ctypes.c_void_p, ctypes.c_ulong]
    ole32.CoInitializeEx.restype = ctypes.c_long
    ole32.CoUninitialize.argtypes = []
    ole32.CoUninitialize.restype = None
    initialized = ole32.CoInitializeEx(None, 0x2) >= 0
    try:
        result = shell32.SHGetKnownFolderPath(ctypes.byref(folder_id), 0, None, ctypes.byref(out))
        if result == 0 and out.value:
            path = Path(ctypes.wstring_at(out.value))
            return path
        return fallback
    finally:
        if out.value:
            ole32.CoTaskMemFree(out)
        if initialized:
            ole32.CoUninitialize()


def apply_ram_cap(megabytes):
    global _JOB_HANDLE
    if os.name != "nt":
        return False, "Windows Job Objects are unavailable."
    if not 256 <= megabytes <= MAX_RAM_MB:
        return False, "RAM cap must be between 256 and 2048 MiB."
    kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
    kernel32.CreateJobObjectW.argtypes = [ctypes.c_void_p, ctypes.c_wchar_p]
    kernel32.CreateJobObjectW.restype = ctypes.c_void_p
    kernel32.SetInformationJobObject.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_void_p,
        ctypes.c_ulong,
    ]
    kernel32.SetInformationJobObject.restype = ctypes.c_int
    kernel32.AssignProcessToJobObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    kernel32.AssignProcessToJobObject.restype = ctypes.c_int
    kernel32.GetCurrentProcess.argtypes = []
    kernel32.GetCurrentProcess.restype = ctypes.c_void_p
    kernel32.CloseHandle.argtypes = [ctypes.c_void_p]
    kernel32.CloseHandle.restype = ctypes.c_int
    job = kernel32.CreateJobObjectW(None, None)
    if not job:
        return False, f"CreateJobObjectW failed with Win32 error {ctypes.get_last_error()}."
    desired_limit = megabytes * 1024 * 1024
    current_commit = 64 * 1024 * 1024
    memory_info = PROCESS_MEMORY_COUNTERS_EX()
    memory_info.cb = ctypes.sizeof(memory_info)
    get_memory_info = getattr(kernel32, "K32GetProcessMemoryInfo", None)
    if get_memory_info:
        get_memory_info.argtypes = [
            ctypes.c_void_p,
            ctypes.POINTER(PROCESS_MEMORY_COUNTERS_EX),
            ctypes.c_ulong,
        ]
        get_memory_info.restype = ctypes.c_int
        if get_memory_info(
            kernel32.GetCurrentProcess(),
            ctypes.byref(memory_info),
            ctypes.sizeof(memory_info),
        ):
            current_commit = int(memory_info.PrivateUsage)
    effective_limit = max(64 * 1024 * 1024, desired_limit - current_commit)
    info = JOBOBJECT_EXTENDED_LIMIT_INFORMATION()
    info.BasicLimitInformation.LimitFlags = 0x00000100 | 0x00000200
    info.ProcessMemoryLimit = effective_limit
    info.JobMemoryLimit = effective_limit
    ok = kernel32.SetInformationJobObject(
        job,
        9,
        ctypes.byref(info),
        ctypes.sizeof(info),
    )
    if not ok:
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        return False, f"SetInformationJobObject failed with Win32 error {error}."
    ok = kernel32.AssignProcessToJobObject(job, kernel32.GetCurrentProcess())
    if not ok:
        error = ctypes.get_last_error()
        kernel32.CloseHandle(job)
        return False, f"AssignProcessToJobObject failed with Win32 error {error}."
    _JOB_HANDLE = job
    allowance_mib = effective_limit // (1024 * 1024)
    return True, f"{megabytes} MiB ceiling active with a {allowance_mib} MiB post-attach job allowance."


def human_size(value):
    units = ("B", "KiB", "MiB", "GiB", "TiB", "PiB")
    number = float(value)
    for unit in units:
        if number < 1024 or unit == units[-1]:
            if unit == "B":
                return f"{int(number)} B"
            return f"{number:.2f} {unit}"
        number /= 1024
    return f"{value} B"


def normalize_path(value):
    expanded = os.path.expandvars(os.path.expanduser(value))
    return os.path.abspath(os.path.normpath(expanded))


def safe_name(value):
    cleaned = re.sub(r'[<>:"/\\|?*\x00-\x1f]+', "_", value).strip(" .")
    return (cleaned or "root")[:80]


def resolve_output(target, fmt, output_arg):
    downloads = get_downloads_folder()
    timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    base = f"{PROGRAM}_{safe_name(os.path.basename(os.path.normpath(target)))}_{timestamp}.{fmt}"
    if not output_arg:
        downloads.mkdir(parents=True, exist_ok=True)
        return downloads / base
    raw = os.path.expandvars(os.path.expanduser(output_arg))
    candidate = Path(raw)
    if candidate.exists() and candidate.is_dir():
        return candidate / base
    if raw.endswith(("\\", "/")):
        candidate.mkdir(parents=True, exist_ok=True)
        return candidate / base
    if candidate.suffix.lower() != f".{fmt}":
        candidate = candidate.with_suffix(f".{fmt}")
    candidate.parent.mkdir(parents=True, exist_ok=True)
    return candidate


def same_path(a, b):
    return os.path.normcase(os.path.abspath(a)) == os.path.normcase(os.path.abspath(b))


def write_record(fp, depth, kind, size, rel_path, error="", patchable=False):
    head = f'[{depth},{json.dumps(kind, ensure_ascii=False)},"'.encode("utf-8")
    offset = fp.tell() + len(head)
    size_text = f"{size:020d}" if not patchable else "00000000000000000000"
    tail = (
        '",'
        + json.dumps(rel_path, ensure_ascii=False)
        + ","
        + json.dumps(error or "", ensure_ascii=False)
        + "]\n"
    ).encode("utf-8")
    fp.write(head)
    fp.write(size_text.encode("ascii"))
    fp.write(tail)
    return offset


def patch_size(fp, offset, size):
    if size < 0 or size >= 10**20:
        raise OverflowError("Folder size exceeds the supported 20-digit byte field.")
    end = fp.tell()
    fp.seek(offset)
    fp.write(f"{size:020d}".encode("ascii"))
    fp.seek(end)


def classify_entry(entry):
    is_link = entry.is_symlink()
    junction_method = getattr(entry, "is_junction", None)
    is_junction = bool(junction_method()) if junction_method else False
    st = entry.stat(follow_symlinks=False)
    attrs = getattr(st, "st_file_attributes", 0)
    is_reparse = bool(attrs & REPARSE_POINT)
    if is_link:
        return "Symlink", int(st.st_size), False
    if is_junction:
        return "Junction", int(st.st_size), False
    if entry.is_dir(follow_symlinks=False):
        if is_reparse and junction_method is None:
            return "Reparse Folder", int(st.st_size), False
        return "Folder", 0, True
    if entry.is_file(follow_symlinks=False):
        if is_reparse:
            return "Reparse File", int(st.st_size), False
        return "File", int(st.st_size), False
    if is_reparse:
        return "Reparse Point", int(st.st_size), False
    return "Other", int(st.st_size), False


def scan_to_spool(target, spool_path, excluded_paths):
    normalized_excludes = {os.path.normcase(os.path.abspath(p)) for p in excluded_paths}
    counts = {
        "files": 0,
        "folders": 0,
        "links_and_reparse_points": 0,
        "other": 0,
        "errors": 0,
        "excluded": 0,
    }
    with open(spool_path, "w+b") as fp:
        try:
            root_iterator = os.scandir(target)
            root_error = ""
        except OSError as exc:
            root_iterator = None
            root_error = f"{type(exc).__name__}: {exc}"
        root_offset = write_record(fp, 0, "Folder", 0, ".", root_error, patchable=True)
        if root_iterator is None:
            counts["errors"] += 1
            patch_size(fp, root_offset, 0)
            fp.flush()
            return 0, counts
        stack = [Frame(target, "", 0, root_iterator, root_offset)]
        while stack:
            frame = stack[-1]
            try:
                entry = next(frame.iterator)
            except StopIteration:
                frame.iterator.close()
                patch_size(fp, frame.size_offset, frame.subtotal)
                stack.pop()
                if stack:
                    stack[-1].subtotal += frame.subtotal
                continue
            except OSError as exc:
                counts["errors"] += 1
                rel_error = frame.rel or "."
                write_record(
                    fp,
                    frame.depth + 1,
                    "Error",
                    0,
                    rel_error,
                    f"{type(exc).__name__}: {exc}",
                )
                frame.iterator.close()
                patch_size(fp, frame.size_offset, frame.subtotal)
                stack.pop()
                if stack:
                    stack[-1].subtotal += frame.subtotal
                continue
            entry_abs = os.path.abspath(entry.path)
            if os.path.normcase(entry_abs) in normalized_excludes:
                counts["excluded"] += 1
                continue
            rel = os.path.join(frame.rel, entry.name) if frame.rel else entry.name
            try:
                kind, size, traversable = classify_entry(entry)
            except OSError as exc:
                counts["errors"] += 1
                write_record(
                    fp,
                    frame.depth + 1,
                    "Error",
                    0,
                    rel,
                    f"{type(exc).__name__}: {exc}",
                )
                continue
            if traversable:
                counts["folders"] += 1
                try:
                    child_iterator = os.scandir(entry.path)
                except OSError as exc:
                    counts["errors"] += 1
                    write_record(
                        fp,
                        frame.depth + 1,
                        "Folder",
                        0,
                        rel,
                        f"{type(exc).__name__}: {exc}",
                    )
                    continue
                offset = write_record(
                    fp,
                    frame.depth + 1,
                    "Folder",
                    0,
                    rel,
                    "",
                    patchable=True,
                )
                stack.append(
                    Frame(
                        entry.path,
                        rel,
                        frame.depth + 1,
                        child_iterator,
                        offset,
                    )
                )
                continue
            write_record(fp, frame.depth + 1, kind, size, rel)
            if kind in ("File", "Reparse File"):
                frame.subtotal += size
                counts["files"] += 1
            elif kind in ("Symlink", "Junction", "Reparse Folder", "Reparse Point"):
                counts["links_and_reparse_points"] += 1
            else:
                counts["other"] += 1
        fp.flush()
        fp.seek(root_offset)
        total_text = fp.read(20).decode("ascii")
        return int(total_text), counts


def iter_records(spool_path):
    with open(spool_path, "rb") as fp:
        for raw in fp:
            depth, kind, size_text, rel_path, error = json.loads(raw.decode("utf-8"))
            yield int(depth), kind, int(size_text), rel_path, error


def type_fields(kind, rel_path):
    if kind == "Folder":
        return "", None, None
    if kind in ("Symlink", "Junction", "Reparse Folder", "Reparse Point", "Other", "Error"):
        return Path(rel_path).suffix.lower(), None, None
    extension = Path(rel_path).suffix.lower()
    mime_type, encoding = mimetypes.guess_type(rel_path, strict=False)
    return extension, mime_type, encoding


def header_lines(target, generated, total_size, counts, ram_cap_mb):
    return [
        f"{PROGRAM} {VERSION}",
        f"Target: {target}",
        f"Generated: {generated}",
        f"Total file size: {human_size(total_size)} ({total_size} bytes)",
        f"Files: {counts['files']}",
        f"Folders: {counts['folders']}",
        f"Links and reparse points: {counts['links_and_reparse_points']}",
        f"Other entries: {counts['other']}",
        f"Errors: {counts['errors']}",
        f"Excluded report/temp files: {counts['excluded']}",
        f"RAM cap: {ram_cap_mb} MiB",
        "Link policy: symbolic links, junctions, and nonstandard directory reparse points are listed but not traversed.",
        "",
    ]


def iter_text_lines(spool_path, target, generated, total_size, counts, ram_cap_mb):
    for line in header_lines(target, generated, total_size, counts, ram_cap_mb):
        yield line
    index = 0
    for depth, kind, size, rel_path, error in iter_records(spool_path):
        index += 1
        extension, mime_type, encoding = type_fields(kind, rel_path)
        indent = "  " * depth
        details = [f"Type={kind}", f"Size={human_size(size)}", f"Bytes={size}"]
        if extension:
            details.append(f"Extension={extension}")
        if mime_type:
            details.append(f"MIME={mime_type}")
        if encoding:
            details.append(f"Encoding={encoding}")
        if error:
            details.append(f"Error={error}")
        yield f"{index:08d} | {indent}{rel_path} | " + " | ".join(details)


def write_txt(output_path, spool_path, target, generated, total_size, counts, ram_cap_mb):
    with open(output_path, "w", encoding="utf-8", newline="\n") as out:
        for line in iter_text_lines(
            spool_path,
            target,
            generated,
            total_size,
            counts,
            ram_cap_mb,
        ):
            out.write(line)
            out.write("\n")


def entry_object(depth, kind, size, rel_path, error):
    extension, mime_type, encoding = type_fields(kind, rel_path)
    return {
        "path": rel_path,
        "depth": depth,
        "kind": kind,
        "size_bytes": size,
        "size_human": human_size(size),
        "extension": extension or None,
        "mime_type": mime_type,
        "encoding": encoding,
        "error": error or None,
    }


def write_json(output_path, spool_path, target, generated, total_size, counts, ram_cap_mb):
    prefix = {
        "program": PROGRAM,
        "version": VERSION,
        "target": target,
        "generated": generated,
        "total_size_bytes": total_size,
        "total_size_human": human_size(total_size),
        "counts": counts,
        "ram_cap_mib": ram_cap_mb,
        "link_policy": "Symbolic links, junctions, and nonstandard directory reparse points are listed but not traversed.",
    }
    with open(output_path, "w", encoding="utf-8", newline="\n") as out:
        out.write("{\n")
        items = list(prefix.items())
        for key, value in items:
            out.write("  ")
            out.write(json.dumps(key, ensure_ascii=False))
            out.write(": ")
            out.write(json.dumps(value, ensure_ascii=False, separators=(",", ":")))
            out.write(",\n")
        out.write('  "entries": [\n')
        first = True
        for record in iter_records(spool_path):
            if not first:
                out.write(",\n")
            out.write("    ")
            out.write(
                json.dumps(
                    entry_object(*record),
                    ensure_ascii=False,
                    separators=(",", ":"),
                )
            )
            first = False
        out.write("\n  ]\n}\n")


def write_pdf_gdi(output_path, lines):
    if os.name != "nt":
        raise OSError("Windows GDI is unavailable.")
    gdi32 = ctypes.WinDLL("gdi32", use_last_error=True)
    printer_name = "Microsoft Print to PDF"
    gdi32.CreateDCW.argtypes = [
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_wchar_p,
        ctypes.c_void_p,
    ]
    gdi32.CreateDCW.restype = ctypes.c_void_p
    gdi32.DeleteDC.argtypes = [ctypes.c_void_p]
    gdi32.DeleteDC.restype = ctypes.c_int
    gdi32.GetDeviceCaps.argtypes = [ctypes.c_void_p, ctypes.c_int]
    gdi32.GetDeviceCaps.restype = ctypes.c_int
    gdi32.CreateFontW.argtypes = [
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_ulong,
        ctypes.c_wchar_p,
    ]
    gdi32.CreateFontW.restype = ctypes.c_void_p
    gdi32.SelectObject.argtypes = [ctypes.c_void_p, ctypes.c_void_p]
    gdi32.SelectObject.restype = ctypes.c_void_p
    gdi32.DeleteObject.argtypes = [ctypes.c_void_p]
    gdi32.DeleteObject.restype = ctypes.c_int
    gdi32.SetBkMode.argtypes = [ctypes.c_void_p, ctypes.c_int]
    gdi32.SetBkMode.restype = ctypes.c_int
    gdi32.GetTextExtentPoint32W.argtypes = [
        ctypes.c_void_p,
        ctypes.c_wchar_p,
        ctypes.c_int,
        ctypes.POINTER(SIZE),
    ]
    gdi32.GetTextExtentPoint32W.restype = ctypes.c_int
    gdi32.TextOutW.argtypes = [
        ctypes.c_void_p,
        ctypes.c_int,
        ctypes.c_int,
        ctypes.c_wchar_p,
        ctypes.c_int,
    ]
    gdi32.TextOutW.restype = ctypes.c_int
    gdi32.StartDocW.argtypes = [ctypes.c_void_p, ctypes.POINTER(DOCINFOW)]
    gdi32.StartDocW.restype = ctypes.c_int
    gdi32.EndDoc.argtypes = [ctypes.c_void_p]
    gdi32.EndDoc.restype = ctypes.c_int
    gdi32.AbortDoc.argtypes = [ctypes.c_void_p]
    gdi32.AbortDoc.restype = ctypes.c_int
    gdi32.StartPage.argtypes = [ctypes.c_void_p]
    gdi32.StartPage.restype = ctypes.c_int
    gdi32.EndPage.argtypes = [ctypes.c_void_p]
    gdi32.EndPage.restype = ctypes.c_int
    hdc = gdi32.CreateDCW("WINSPOOL", printer_name, None, None)
    if not hdc:
        raise OSError(f"{printer_name} is unavailable or disabled.")
    font = None
    old_font = None
    started_doc = False
    page_started = False
    try:
        dpi_x = gdi32.GetDeviceCaps(hdc, 88)
        dpi_y = gdi32.GetDeviceCaps(hdc, 90)
        width = gdi32.GetDeviceCaps(hdc, 8)
        height = gdi32.GetDeviceCaps(hdc, 10)
        font_height = -max(8, round(8.5 * dpi_y / 72))
        font = gdi32.CreateFontW(
            font_height,
            0,
            0,
            0,
            400,
            0,
            0,
            0,
            1,
            0,
            0,
            0,
            0x31,
            "Consolas",
        )
        if not font:
            raise OSError("Could not create the PDF report font.")
        old_font = gdi32.SelectObject(hdc, font)
        gdi32.SetBkMode(hdc, 1)
        extent = SIZE()
        if not gdi32.GetTextExtentPoint32W(hdc, "M", 1, ctypes.byref(extent)):
            raise OSError("Could not measure the PDF report font.")
        margin_x = max(1, round(dpi_x * 0.35))
        margin_y = max(1, round(dpi_y * 0.35))
        char_width = max(1, extent.cx)
        line_height = max(1, round(abs(font_height) * 1.3))
        max_chars = max(40, (width - 2 * margin_x) // char_width)
        info = DOCINFOW()
        info.cbSize = ctypes.sizeof(DOCINFOW)
        info.lpszDocName = PROGRAM
        info.lpszOutput = str(output_path)
        info.lpszDatatype = None
        info.fwType = 0
        if gdi32.StartDocW(hdc, ctypes.byref(info)) <= 0:
            raise OSError("Microsoft Print to PDF could not start the document.")
        started_doc = True
        if gdi32.StartPage(hdc) <= 0:
            raise OSError("Microsoft Print to PDF could not start the first page.")
        page_started = True
        y = margin_y
        for line in lines:
            text = line.expandtabs(4)
            pieces = [text[i : i + max_chars] for i in range(0, len(text), max_chars)] or [""]
            for piece in pieces:
                if y + line_height > height - margin_y:
                    if gdi32.EndPage(hdc) <= 0:
                        raise OSError("Microsoft Print to PDF could not end a page.")
                    page_started = False
                    if gdi32.StartPage(hdc) <= 0:
                        raise OSError("Microsoft Print to PDF could not start a new page.")
                    page_started = True
                    y = margin_y
                if piece and not gdi32.TextOutW(hdc, margin_x, y, piece, len(piece)):
                    raise OSError("Microsoft Print to PDF could not render report text.")
                y += line_height
        if page_started:
            if gdi32.EndPage(hdc) <= 0:
                raise OSError("Microsoft Print to PDF could not end the final page.")
            page_started = False
        if gdi32.EndDoc(hdc) <= 0:
            raise OSError("Microsoft Print to PDF could not finalize the document.")
        started_doc = False
    except Exception:
        if page_started:
            gdi32.EndPage(hdc)
        if started_doc:
            gdi32.AbortDoc(hdc)
        raise
    finally:
        if old_font:
            gdi32.SelectObject(hdc, old_font)
        if font:
            gdi32.DeleteObject(font)
        gdi32.DeleteDC(hdc)
    for _ in range(100):
        if output_path.exists() and output_path.stat().st_size > 0:
            return
        time.sleep(0.05)
    raise OSError("Microsoft Print to PDF did not create the output file.")


def find_edge():
    candidates = []
    found = shutil.which("msedge")
    if found:
        candidates.append(found)
    for variable in ("ProgramFiles(x86)", "ProgramFiles", "LOCALAPPDATA"):
        root = os.environ.get(variable)
        if not root:
            continue
        if variable == "LOCALAPPDATA":
            candidates.append(os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"))
        else:
            candidates.append(os.path.join(root, "Microsoft", "Edge", "Application", "msedge.exe"))
    for candidate in candidates:
        if candidate and os.path.isfile(candidate):
            return candidate
    return None


def write_pdf_edge(output_path, lines):
    edge = find_edge()
    if not edge:
        raise OSError("Microsoft Edge is unavailable for the PDF fallback.")
    temp_dir = Path(tempfile.mkdtemp(prefix="FolderTally_PDF_"))
    html_path = temp_dir / "report.html"
    profile_dir = temp_dir / "edge-profile"
    try:
        with open(html_path, "w", encoding="utf-8", newline="\n") as out:
            out.write(
                '<!doctype html><meta charset="utf-8"><title>FolderTally</title>'
                '<style>@page{size:A4;margin:10mm}body{font-family:Consolas,"Courier New",monospace;'
                'font-size:8pt;line-height:1.25;white-space:pre-wrap;overflow-wrap:anywhere}</style><body>'
            )
            for line in lines:
                out.write(html.escape(line))
                out.write("\n")
            out.write("</body>")
        args = [
            edge,
            "--headless",
            "--disable-gpu",
            "--no-first-run",
            "--no-pdf-header-footer",
            f"--user-data-dir={profile_dir}",
            f"--print-to-pdf={output_path}",
            html_path.resolve().as_uri(),
        ]
        result = subprocess.run(
            args,
            stdin=subprocess.DEVNULL,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            shell=False,
        )
        if result.returncode != 0 or not output_path.exists() or output_path.stat().st_size == 0:
            raise OSError("Edge PDF fallback failed to create the output file.")
    finally:
        shutil.rmtree(temp_dir, ignore_errors=True)


def write_pdf(output_path, spool_path, target, generated, total_size, counts, ram_cap_mb):
    factory = lambda: iter_text_lines(
        spool_path,
        target,
        generated,
        total_size,
        counts,
        ram_cap_mb,
    )
    first_error = None
    try:
        write_pdf_gdi(output_path, factory())
        return "Microsoft Print to PDF"
    except Exception as exc:
        first_error = exc
        try:
            if output_path.exists():
                output_path.unlink()
        except OSError:
            pass
    try:
        write_pdf_edge(output_path, factory())
        return "Microsoft Edge fallback"
    except Exception as exc:
        raise OSError(f"PDF creation failed. GDI: {first_error}. Edge: {exc}") from exc


def positive_ram_cap(value):
    try:
        number = int(value)
    except ValueError as exc:
        raise argparse.ArgumentTypeError("RAM cap must be an integer.") from exc
    if not 256 <= number <= MAX_RAM_MB:
        raise argparse.ArgumentTypeError("RAM cap must be between 256 and 2048 MiB.")
    return number


def build_parser():
    parser = argparse.ArgumentParser(
        prog=PROGRAM,
        description="Fast recursive Windows 11 folder inventory with per-folder totals.",
    )
    parser.add_argument("target", help="Folder to scan.")
    parser.add_argument(
        "-f",
        "--format",
        choices=("txt", "json", "pdf"),
        default="txt",
        help="Output format. Default: txt.",
    )
    parser.add_argument(
        "-o",
        "--output",
        help="Output file or directory. Default: Windows Downloads folder.",
    )
    parser.add_argument(
        "--ram-cap-mb",
        type=positive_ram_cap,
        default=MAX_RAM_MB,
        help="Hard committed-memory cap from 256 to 2048 MiB. Default: 2048.",
    )
    parser.add_argument(
        "--overwrite",
        action="store_true",
        help="Allow replacing an existing custom output file.",
    )
    parser.add_argument(
        "--no-hard-cap",
        action="store_true",
        help="Run without the Windows Job Object memory cap.",
    )
    return parser


def main():
    parser = build_parser()
    args = parser.parse_args()
    if os.name != "nt":
        parser.error(f"{PROGRAM} is built for Windows 11.")
    target = normalize_path(args.target)
    if not os.path.isdir(target):
        parser.error(f"Target is not an accessible folder: {target}")
    output_path = resolve_output(target, args.format, args.output)
    output_path = output_path.resolve()
    if output_path.exists() and not args.overwrite:
        parser.error(f"Output already exists. Use --overwrite to replace it: {output_path}")
    if same_path(target, output_path):
        parser.error("Output file cannot be the target folder.")
    if args.no_hard_cap:
        cap_message = "Hard memory cap disabled by command line."
    else:
        ok, cap_message = apply_ram_cap(args.ram_cap_mb)
        if not ok:
            parser.error(cap_message + " Use --no-hard-cap only if you accept losing the hard cap.")
    mimetypes.init()
    spool_handle = tempfile.NamedTemporaryFile(
        prefix="FolderTally_",
        suffix=".jsonl",
        delete=False,
    )
    spool_path = Path(spool_handle.name)
    spool_handle.close()
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    print(f"{PROGRAM} {VERSION}")
    print(f"Target: {target}")
    print(f"Format: {args.format.upper()}")
    print(f"Output: {output_path}")
    print(f"Memory: {cap_message}")
    print("Scanning...")
    try:
        total_size, counts = scan_to_spool(
            target,
            spool_path,
            [str(output_path), str(spool_path)],
        )
        print(f"Total file size: {human_size(total_size)} ({total_size} bytes)")
        print(f"Files: {counts['files']} | Folders: {counts['folders']} | Errors: {counts['errors']}")
        if output_path.exists() and args.overwrite:
            output_path.unlink()
        if args.format == "txt":
            write_txt(
                output_path,
                spool_path,
                target,
                generated,
                total_size,
                counts,
                args.ram_cap_mb,
            )
            backend = "UTF-8 text"
        elif args.format == "json":
            write_json(
                output_path,
                spool_path,
                target,
                generated,
                total_size,
                counts,
                args.ram_cap_mb,
            )
            backend = "streaming JSON"
        else:
            backend = write_pdf(
                output_path,
                spool_path,
                target,
                generated,
                total_size,
                counts,
                args.ram_cap_mb,
            )
        print(f"Done: {output_path}")
        print(f"Writer: {backend}")
        if counts["errors"]:
            print("Some entries could not be read. Their errors are recorded in the report.")
        return 0
    except KeyboardInterrupt:
        print("Cancelled.", file=sys.stderr)
        try:
            if output_path.exists():
                output_path.unlink()
        except OSError:
            pass
        return 130
    except MemoryError:
        print("Stopped because the configured RAM cap was reached.", file=sys.stderr)
        try:
            if output_path.exists():
                output_path.unlink()
        except OSError:
            pass
        return 3
    except Exception as exc:
        print(f"Error: {type(exc).__name__}: {exc}", file=sys.stderr)
        try:
            if output_path.exists():
                output_path.unlink()
        except OSError:
            pass
        return 1
    finally:
        try:
            spool_path.unlink()
        except OSError:
            pass


if __name__ == "__main__":
    raise SystemExit(main())
