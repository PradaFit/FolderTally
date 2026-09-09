# SPDX-License-Identifier: LicenseRef-FolderTally-Noncommercial-1.0
# Copyright (C) 2026 PradaFit

import json
import multiprocessing
import os
import tempfile
import time
import unittest
import contextlib
import io
from pathlib import Path
from unittest.mock import patch

import FolderTally as core
import foldertally_service as service


class ReportTests(unittest.TestCase):
    def setUp(self):
        self.temp = tempfile.TemporaryDirectory(prefix="FolderTally_test_")
        self.addCleanup(self.temp.cleanup)
        self.base = Path(self.temp.name)
        self.source = self.base / "source"
        self.output = self.base / "reports"
        self.source.mkdir()
        self.output.mkdir()
        (self.source / "nested").mkdir()
        (self.source / "empty").mkdir()
        (self.source / "hello.txt").write_bytes(b"hello")
        (self.source / "nested" / "R\u00e9sum\u00e9_\u6f22\U0001f4c1.json").write_bytes(b"{}")

    def test_json_totals_unicode_and_metadata(self):
        result = service.export_report(self.source, self.output, "json")
        data = json.loads(Path(result["path"]).read_text(encoding="utf-8"))
        self.assertEqual(data["total_size_bytes"], 7)
        self.assertEqual(data["counts"]["files"], 2)
        self.assertEqual(data["counts"]["folders"], 2)
        entries = {e["path"]: e for e in data["entries"]}
        self.assertEqual(entries["nested"]["size_bytes"], 2)
        self.assertEqual(entries["."]["size_bytes"], 7)
        self.assertIn("nested\\R\u00e9sum\u00e9_\u6f22\U0001f4c1.json" if os.name == "nt" else "nested/R\u00e9sum\u00e9_\u6f22\U0001f4c1.json", entries)

    def test_text_export(self):
        result = service.export_report(self.source, self.output, "txt")
        text = Path(result["path"]).read_text(encoding="utf-8")
        self.assertIn("Files: 2", text)
        self.assertIn("R\u00e9sum\u00e9_\u6f22\U0001f4c1.json", text)

    def test_pdf_is_parseable_and_names_are_preserved(self):
        from pypdf import PdfReader
        result = service.export_report(self.source, self.output, "pdf")
        reader = PdfReader(result["path"])
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("FolderTally", text)
        self.assertIn("hello.txt", text)
        self.assertIn("\\u6F22", text)
        self.assertIn("\\U0001F4C1", text)
        self.assertTrue(all(float(p.mediabox.width) > 590 for p in reader.pages))

    def test_pdf_multiple_pages_and_long_name(self):
        from pypdf import PdfReader
        for index in range(120):
            (self.source / (f"{index:03d}_" + "long_" * 30 + ".txt")).touch()
        result = service.export_report(self.source, self.output, "pdf")
        reader = PdfReader(result["path"])
        self.assertGreater(len(reader.pages), 3)
        text = "\n".join(page.extract_text() for page in reader.pages)
        self.assertIn("119_long", text)

    def test_pdf_export_does_not_construct_an_xml_parser(self):
        import pyexpat
        with patch.object(pyexpat, 'ParserCreate', side_effect=AssertionError('Unexpected XML parser use')):
            result = service.export_report(self.source, self.output, 'pdf')
        self.assertTrue(Path(result['path']).is_file())

    def test_empty_folder(self):
        result = service.export_report(self.source / "empty", self.output, "json")
        self.assertEqual(result["total"], 0)
        self.assertEqual(result["counts"]["errors"], 0)

    def test_pdf_language_tags_reading_order_and_artifacts(self):
        from pypdf import PdfReader
        import re
        for index in range(120):
            (self.source / f"{index:03d}.txt").touch()
        result = service.export_report(self.source, self.output, "pdf")
        reader = PdfReader(result["path"])
        root = reader.trailer['/Root']
        self.assertEqual(reader.pdf_header, '%PDF-1.7')
        from xml.etree import ElementTree
        metadata = ElementTree.fromstring(root['/Metadata'].get_data())
        description = metadata.find('.//{http://www.w3.org/1999/02/22-rdf-syntax-ns#}Description')
        self.assertEqual(description.get('{http://www.aiim.org/pdfua/ns/id/}part'), '1')
        self.assertEqual(root['/Lang'], 'en-US')
        self.assertTrue(root['/MarkInfo']['/Marked'])
        self.assertTrue(root['/ViewerPreferences']['/DisplayDocTitle'])
        tree = root['/StructTreeRoot']
        document = tree['/K'][0].get_object()
        self.assertEqual(document['/S'], '/Document')
        children = [item.get_object() for item in document['/K']]
        self.assertEqual(children[0]['/S'], '/H1')
        self.assertTrue(all(child['/S'] == '/P' for child in children[1:]))
        parents = tree['/ParentTree']['/Nums']
        self.assertEqual(len(parents), len(reader.pages) * 2)
        total = 0
        for index, page in enumerate(reader.pages):
            for font in page['/Resources']['/Font'].values():
                font = font.get_object()
                self.assertIn('/ToUnicode', font)
                self.assertIn('/FontFile2', font['/FontDescriptor'])
            self.assertEqual(page['/StructParents'], index)
            self.assertEqual(page['/Tabs'], '/S')
            content = page.get_contents().get_data()
            mcids = [int(value) for value in re.findall(rb'/MCID (\d+)', content)]
            self.assertEqual(mcids, list(range(len(mcids))))
            self.assertEqual(len(parents[index * 2 + 1]), len(mcids))
            self.assertIn(b'/Artifact BMC', content)
            self.assertEqual(content.count(b'EMC'), content.count(b'BDC') + content.count(b'BMC'))
            total += len(mcids)
        self.assertEqual(total, len(children))

    def test_pdf_cancel_while_record_is_yielded_closes_spool(self):
        cancelled = False
        original = core.iter_text_lines
        def lines(*args, **kwargs):
            nonlocal cancelled
            iterator = original(*args, **kwargs)
            try:
                for line in iterator:
                    if line.startswith('00000001'):
                        cancelled = True
                    yield line
            finally:
                iterator.close()
        with patch.object(core, 'iter_text_lines', side_effect=lines):
            with self.assertRaises(core.ScanCancelled):
                service.export_report(self.source, self.output, 'pdf', cancelled=lambda: cancelled)
        self.assertEqual(list(self.output.iterdir()), [])

    def test_reports_in_source_exclude_own_staging(self):
        result = service.export_report(self.source, self.source, "json")
        self.assertEqual(result["total"], 7)
        self.assertEqual(result["counts"]["files"], 2)
        self.assertEqual(result["counts"]["excluded"], 1)
        self.assertFalse(list(self.source.glob(".FolderTally_*")))

    def test_existing_output_is_untouched(self):
        existing = self.output / "keep.txt"
        existing.write_text("preserve", encoding="utf-8")
        with self.assertRaises(FileExistsError):
            service.export_report(self.source, self.output, "txt", output_name="keep.txt")
        self.assertEqual(existing.read_text(), "preserve")

    def test_atomic_publish_race_keeps_competing_file(self):
        staged = self.output / "staged.txt"
        final = self.output / "final.txt"
        staged.write_text("new")
        final.write_text("original")
        with self.assertRaises(FileExistsError):
            service.publish_report(staged, final)
        self.assertEqual(final.read_text(), "original")

    def test_write_failure_cleans_only_owned_staging(self):
        existing = self.output / "keep.txt"
        existing.write_text("preserve")
        with patch.object(core, "write_txt", side_effect=OSError("simulated full disk")):
            with self.assertRaises(OSError):
                service.export_report(self.source, self.output, "txt")
        self.assertEqual(list(self.output.iterdir()), [existing])

    def test_cancel_before_scan(self):
        with self.assertRaises(core.ScanCancelled):
            service.export_report(self.source, self.output, "txt", cancelled=lambda: True)
        self.assertFalse(list(self.output.iterdir()))

    def test_cancel_during_scan_closes_iterators(self):
        class Iterator:
            def __init__(self):
                self.inner = os.scandir(self.source)
                self.closed = False
            def __next__(self):
                return next(self.inner)
            def close(self):
                self.closed = True
                self.inner.close()
        Iterator.source = self.source
        iterator = Iterator()
        spool = self.output / "test.jsonl"
        with patch.object(core.os, "scandir", return_value=iterator):
            with self.assertRaises(core.ScanCancelled):
                core.scan_to_spool(self.source, spool, [], cancelled=lambda: True)
        self.assertTrue(iterator.closed)

    def test_cancel_during_export_removes_partial(self):
        stop = False
        def progress(_total, _counts, phase="scanning"):
            nonlocal stop
            stop = phase == "exporting"
        with self.assertRaises(core.ScanCancelled):
            service.export_report(self.source, self.output, "json", progress=progress, cancelled=lambda: stop)
        self.assertFalse(list(self.output.iterdir()))

    def test_access_error_is_reported(self):
        original = os.scandir
        def scandir(path):
            if isinstance(path, int):
                return original(path)
            if Path(path).name == "nested":
                raise PermissionError("synthetic access error")
            return original(path)
        with patch.object(core.os, "scandir", side_effect=scandir):
            result = service.export_report(self.source, self.output, "json")
        self.assertEqual(result["counts"]["errors"], 1)
        self.assertEqual(result["total"], 5)
        self.assertIn("synthetic access error", Path(result["path"]).read_text())

    def test_descent_rechecks_reparse_attributes(self):
        from types import SimpleNamespace
        original = core.os.stat
        def fresh_stat(path, *args, **kwargs):
            info = original(path, *args, **kwargs)
            if not isinstance(path, int) and Path(path).name == 'nested' and kwargs.get('follow_symlinks') is False:
                return SimpleNamespace(st_mode=info.st_mode, st_file_attributes=core.REPARSE_POINT,
                                       st_dev=info.st_dev, st_ino=info.st_ino)
            return info
        with patch.object(core.os, 'stat', side_effect=fresh_stat):
            result = service.export_report(self.source, self.output, 'json')
        self.assertEqual(result['counts']['errors'], 1)
        self.assertEqual(result['total'], 5)
        self.assertIn('traversal refused', Path(result['path']).read_text())

    def test_descent_rejects_paths_outside_root_and_changed_identity(self):
        from types import SimpleNamespace
        root = os.path.normcase(os.path.realpath(self.source))
        with self.assertRaisesRegex(OSError, 'outside'):
            core.checked_scandir(self.output, root)
        info = self.source.stat()
        with self.assertRaisesRegex(OSError, 'after classification'):
            core.checked_scandir(self.source, root, SimpleNamespace(st_dev=info.st_dev, st_ino=-1))

    def test_changed_directory_after_open_closes_iterator(self):
        from types import SimpleNamespace
        from unittest.mock import Mock
        info = self.source.stat()
        changed = SimpleNamespace(st_mode=info.st_mode, st_file_attributes=0, st_dev=info.st_dev, st_ino=-1)
        iterator = Mock()
        root = os.path.normcase(os.path.realpath(self.source))
        with patch.object(core.os, 'stat', side_effect=[info, changed]), patch.object(core.os, 'scandir', return_value=iterator), patch.object(core.os.path, 'realpath', return_value=root):
            with self.assertRaisesRegex(OSError, 'while opening'):
                core.checked_scandir(self.source, root)
        iterator.close.assert_called_once()

    def test_directory_reparse_point_is_never_traversed(self):
        class Entry:
            def is_symlink(self): return False
            def is_junction(self): return False
            def is_dir(self, **_kw): return True
            def stat(self, **_kw):
                class Stat:
                    st_file_attributes = core.REPARSE_POINT
                    st_size = 0
                return Stat()
        self.assertEqual(core.classify_entry(Entry()), ("Reparse Folder", 0, False))

    def test_bad_inputs(self):
        for target, output, fmt, cap in [("", self.output, "txt", 2048),
                                         (self.source, "", "txt", 2048),
                                         (self.source / "missing", self.output, "txt", 2048),
                                         (self.source, self.output, "exe", 2048),
                                         (self.source, self.output, "txt", 128)]:
            with self.subTest(target=target, fmt=fmt, cap=cap), self.assertRaises(ValueError):
                service.validate_request(target, output, fmt, cap)

    def test_no_path_escape_for_report_filename(self):
        for name in ("../escape.txt", "report.exe"):
            with self.subTest(name=name), self.assertRaises(ValueError):
                service.export_report(self.source, self.output, "txt", output_name=name)

    def test_unique_report_names(self):
        names = {service.report_name(self.source, "txt") for _ in range(100)}
        self.assertEqual(len(names), 100)

    @unittest.skipUnless(os.name == "nt", "Windows CLI")
    def test_cli_json_success(self):
        final = self.output / "cli.json"
        args = ["FolderTally.py", str(self.source), "--format", "json", "--output", str(final), "--no-hard-cap"]
        with patch("sys.argv", args), contextlib.redirect_stdout(io.StringIO()):
            self.assertEqual(core.main(), 0)
        self.assertEqual(json.loads(final.read_text(encoding="utf-8"))["total_size_bytes"], 7)

    @unittest.skipUnless(os.name == "nt", "Windows CLI")
    def test_cli_failed_overwrite_preserves_original(self):
        final = self.output / "cli.txt"
        final.write_text("preserve")
        args = ["FolderTally.py", str(self.source), "--output", str(final), "--no-hard-cap", "--overwrite"]
        with patch("sys.argv", args), patch.object(core, "write_txt", side_effect=OSError("synthetic write failure")), \
                contextlib.redirect_stdout(io.StringIO()), contextlib.redirect_stderr(io.StringIO()):
            self.assertEqual(core.main(), 1)
        self.assertEqual(final.read_text(), "preserve")
        self.assertEqual(list(self.output.iterdir()), [final])

    @unittest.skipUnless(os.name == "nt", "Windows Job Object test")
    def test_spawned_worker_with_memory_limit(self):
        context = multiprocessing.get_context("spawn")
        receiver, sender = context.Pipe(duplex=False)
        cancel = context.Event()
        worker = context.Process(target=service.scan_worker, args=(sender, cancel, {
            "target": str(self.source), "destination": str(self.output), "format": "json", "cap": 256}))
        worker.start()
        sender.close()
        messages = []
        deadline = time.monotonic() + 20
        while time.monotonic() < deadline and worker.is_alive():
            try:
                if receiver.poll(0.1):
                    messages.append(receiver.recv())
            except (EOFError, OSError):
                break
        worker.join(timeout=5)
        try:
            while receiver.poll():
                messages.append(receiver.recv())
        except (EOFError, OSError):
            pass
        receiver.close()
        self.assertFalse(worker.is_alive())
        self.assertEqual(worker.exitcode, 0)
        self.assertEqual(messages[-1]["kind"], "complete", messages)
        self.assertEqual(messages[-1]["total"], 7)
        worker.close()


if __name__ == "__main__":
    unittest.main()
