# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

"""Desktop report workflow. No filesystem content is read by the inventory."""

import os
import tempfile
import time
import uuid
from contextlib import closing
from datetime import datetime
from pathlib import Path

import FolderTally as core


def validated_folder(value, label):
    value = str(value).strip().strip('"')
    if not value:
        raise ValueError(f"Choose a {label.lower()}.")
    if value.startswith('\\\\.\\') or '\x00' in value:
        raise ValueError(f"{label} must be a regular folder path.")
    path = Path(core.normalize_path(value))
    if not path.is_dir():
        raise ValueError(f"{label} does not exist or cannot be accessed.")
    return path


def validate_request(target, destination, fmt, ram_cap_mb):
    source = validated_folder(target, "Source folder")
    output = validated_folder(destination, "Report folder")
    if source.is_symlink() or getattr(source.stat(follow_symlinks=False), "st_file_attributes", 0) & core.REPARSE_POINT:
        raise ValueError("Choose the original source folder instead of a link or reparse point.")
    if fmt not in ("txt", "json", "pdf"):
        raise ValueError("Choose TXT, JSON, or PDF.")
    if ram_cap_mb not in (256, 512, 1024, 2048):
        raise ValueError("Choose a supported memory limit.")
    return source, output


def report_name(target, fmt):
    stamp = datetime.now().strftime("%Y%m%d_%H%M%S")
    return f"FolderTally_{core.safe_name(Path(target).name)}_{stamp}_{uuid.uuid4().hex[:8]}.{fmt}"


def publish_report(staged, destination, overwrite=False):
    """Publish on the same volume, without clobbering a competing writer."""
    if overwrite:
        os.replace(staged, destination)
    elif os.name == "nt":
        os.rename(staged, destination)  # Windows fails if the destination exists.
    else:
        os.link(staged, destination)
        Path(staged).unlink()


def write_desktop_pdf(output, spool, target, generated, total, counts, cap, cancelled=None):
    # Only the canvas text API is used. Filenames are never parsed as markup,
    # URLs, images, PDF commands, or executable expressions.
    import reportlab
    from reportlab.pdfbase import pdfmetrics
    from reportlab.pdfbase.ttfonts import TTFont
    from reportlab.pdfgen.canvas import Canvas

    font_name = "FolderTallyVera"
    if font_name not in pdfmetrics.getRegisteredFontNames():
        font_path = Path(reportlab.__file__).parent / "fonts" / "Vera.ttf"
        pdfmetrics.registerFont(TTFont(font_name, str(font_path)))
    font = pdfmetrics.getFont(font_name)
    widths = font.face.charWidths
    canvas = Canvas(str(output), pagesize=(595.28, 841.89), pageCompression=1,
                    pdfVersion=(1, 7), initialFontName=font_name, lang="en-US")
    canvas.setTitle("FolderTally | Folder inventory")
    canvas.setAuthor("FolderTally")
    canvas.setCreator(f"FolderTally {core.VERSION}")
    page = 0
    y = 0
    page_counts = []

    def new_page():
        nonlocal page, y
        if page:
            canvas.showPage()
        page += 1
        page_counts.append(0)
        canvas._code.append("/Artifact BMC")
        canvas.setFillColorRGB(0.07, 0.15, 0.25)
        canvas.rect(0, 767, 596, 75, fill=1, stroke=0)
        canvas.setFillColorRGB(1, 1, 1)
        canvas.setFont(font_name, 19)
        canvas.drawString(36, 802, "FolderTally")
        canvas.setFont(font_name, 9)
        canvas.drawString(36, 782, "FOLDER INVENTORY")
        canvas.setFillColorRGB(0.32, 0.38, 0.45)
        canvas.setFont(font_name, 8)
        canvas.drawString(36, 24, "File metadata only | Detected links are not followed")
        canvas.drawRightString(559, 24, f"Page {page}")
        canvas._code.append("EMC")
        canvas.setFillColorRGB(0.10, 0.16, 0.23)
        canvas.setFont(font_name, 8.5)
        y = 745

    new_page()
    with closing(core.iter_text_lines(spool, target, generated, total, counts, cap, cancelled)) as lines:
        for line in lines:
            if cancelled and cancelled():
                raise core.ScanCancelled()
            # PDF font coverage is finite. Escape unsupported code points so names
            # remain recoverable instead of silently rendering an empty glyph.
            safe = "".join(
                char if ord(char) in widths and ord(char) >= 32 else
                ("    " if char == '\t' else
                 (f"\\u{ord(char):04X}" if ord(char) <= 0xFFFF else f"\\U{ord(char):08X}"))
                for char in line
            )
            pieces = []
            current = []
            width = 0.0
            for char in safe:
                advance = widths.get(ord(char), 600) * 8.5 / 1000
                if width + advance > 523 and current:
                    pieces.append("".join(current))
                    current, width = [], 0.0
                current.append(char)
                width += advance
            pieces.append("".join(current))
            for piece in pieces:
                if y < 49:
                    new_page()
                mcid = page_counts[-1]
                canvas._code.append(f"/P <</MCID {mcid}>> BDC")
                canvas.drawString(36, y, piece)
                canvas._code.append("EMC")
                page_counts[-1] += 1
                y -= 12
    if cancelled and cancelled():
        raise core.ScanCancelled()
    canvas.save()
    from foldertally_pdf_accessibility import tag_report
    tag_report(output, page_counts, cancelled)


def export_report(target, destination, fmt, cap=2048, progress=None, cancelled=None, output_name=None):
    source, report_folder = validate_request(target, destination, fmt, cap)
    name = output_name or report_name(source, fmt)
    if Path(name).name != name or Path(name).suffix.lower() != f".{fmt}":
        raise ValueError("Report filename must be a plain filename with the selected extension.")
    final = report_folder / name
    if final.exists():
        raise FileExistsError("A report with this name already exists. Choose a new filename.")

    def check():
        if cancelled and cancelled():
            raise core.ScanCancelled()

    check()
    started = time.monotonic()
    generated = datetime.now().astimezone().isoformat(timespec="seconds")
    # An owned staging directory prevents failed exports from damaging user
    # files and permits an atomic final rename on the same filesystem.
    with tempfile.TemporaryDirectory(prefix=".FolderTally_", dir=report_folder) as staging:
        staging = Path(staging)
        spool = staging / "inventory.jsonl"
        partial = staging / f"report.{fmt}"
        total, counts = core.scan_to_spool(source, spool, [staging, final], progress, cancelled)
        check()
        if progress:
            progress(total, counts, "exporting")
        writer = {"txt": core.write_txt, "json": core.write_json, "pdf": write_desktop_pdf}[fmt]
        writer(partial, spool, str(source), generated, total, counts, cap, cancelled)
        check()
        publish_report(partial, final)
    return {"path": str(final), "total": total, "counts": counts,
            "elapsed": time.monotonic() - started, "format": fmt}


def scan_worker(connection, cancel_event, request):
    """Only this spawned process receives the Job Object memory limit."""
    last_update = 0.0

    def send_progress(total, counts, phase="scanning"):
        nonlocal last_update
        now = time.monotonic()
        if now - last_update >= 0.15 or phase != "scanning":
            connection.send({"kind": "progress", "total": total,
                             "counts": dict(counts), "phase": phase})
            last_update = now

    try:
        ok, cap_message = core.apply_ram_cap(request["cap"])
        if not ok:
            raise RuntimeError("The memory limit could not be applied. " + cap_message)
        connection.send({"kind": "started"})
        result = export_report(request["target"], request["destination"], request["format"],
                               request["cap"], send_progress, cancel_event.is_set)
        connection.send({"kind": "complete", **result})
    except core.ScanCancelled:
        connection.send({"kind": "cancelled"})
    except MemoryError:
        connection.send({"kind": "error", "message": "The selected memory limit was reached. Try a higher limit or a smaller source folder."})
    except Exception as exc:
        connection.send({"kind": "error", "message": f"{type(exc).__name__}: {exc}"})
    finally:
        connection.close()
