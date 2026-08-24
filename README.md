# FolderTally

**Python folder size analyzer, disk usage scanner, and recursive directory inventory tool for Windows 11.**

FolderTally scans a folder recursively and builds a detailed inventory of its files and subfolders. It calculates folder sizes, records file metadata, identifies extensions and MIME types, and exports the results to TXT, JSON, or PDF.

It is designed for Windows users who need a straightforward way to inspect disk usage, audit directory contents, document large folder structures, or generate file inventory reports without installing third-party Python packages.

## Features

* Recursive folder and file scanning
* Calculates total size for every scanned folder
* Reports individual file sizes in bytes and human-readable units
* Detects file extensions and MIME types
* Exports reports as TXT, JSON, or PDF
* Lists symbolic links, junctions, and Windows reparse points without traversing them
* Records inaccessible files and folders instead of silently skipping errors
* Uses a disk-backed temporary scan file to reduce memory pressure during large scans
* Configurable Windows Job Object memory limit
* Supports memory limits from 256 MiB to 2048 MiB
* Defaults to a 2048 MiB RAM ceiling
* Saves reports to the Windows Downloads folder by default
* Supports custom report paths and directories
* Supports safe overwrite control
* Uses Microsoft Print to PDF for PDF reports
* Falls back to Microsoft Edge for PDF generation if needed
* No third-party Python packages required

## Why FolderTally?

Windows can show the size of a folder through File Explorer, but that does not provide a complete recursive inventory that can be saved and processed later.

FolderTally produces a structured report containing the folder hierarchy, file sizes, directory totals, file types, MIME information, and scan errors.

It can be useful for:

* Disk usage analysis
* Storage audits
* Large directory investigation
* File inventory generation
* Backup planning
* Data migration preparation
* Folder cleanup
* Archive analysis
* Server and workstation documentation
* Identifying where storage is being consumed
* Exporting filesystem data for scripts or other tools

## Requirements

* Windows 11
* Python 3
* No external Python packages

TXT and JSON reports use Python's standard library only.

For PDF reports, FolderTally attempts to use:

1. Microsoft Print to PDF
2. Microsoft Edge as a fallback

PDF export is the only feature that depends on those Windows components being available.

## Installation

Clone or download this repository, then make sure Python is available from Command Prompt, PowerShell, or Windows Terminal.

Check Python:

```powershell
python --version
```

FolderTally does not require `pip install` or a `requirements.txt` file because it uses Python standard-library modules.

## Basic Usage

Run FolderTally and provide the folder you want to scan:

```powershell
python FolderTally.py "C:\Users\YourName\Documents"
```

By default, FolderTally creates a TXT report in your Windows Downloads folder.

Example output filename:

```text
FolderTally_Documents_20260823_173000.txt
```

## Export Formats

FolderTally supports three report formats:

* `txt`
* `json`
* `pdf`

### TXT Report

```powershell
python FolderTally.py "D:\Projects" --format txt
```

TXT reports are designed for quick inspection, searching, archiving, and sharing.

### JSON Report

```powershell
python FolderTally.py "D:\Projects" --format json
```

JSON output is useful when FolderTally data needs to be processed by another Python script, PowerShell script, application, database importer, or automation workflow.

### PDF Report

```powershell
python FolderTally.py "D:\Projects" --format pdf
```

FolderTally first attempts to generate the PDF through Microsoft Print to PDF. If that fails, it attempts to use Microsoft Edge in headless mode.

## Custom Output Location

Use `-o` or `--output` to choose where the report should be written.

```powershell
python FolderTally.py "D:\Projects" --output "D:\Reports"
```

You can also specify a complete output filename:

```powershell
python FolderTally.py "D:\Projects" --format json --output "D:\Reports\projects.json"
```

If only a directory is provided, FolderTally automatically generates the report filename.

## Memory Limit

FolderTally can apply a Windows Job Object memory limit to the running process.

The default RAM ceiling is:

```text
2048 MiB
```

Set a different limit with:

```powershell
python FolderTally.py "D:\Data" --ram-cap-mb 1024
```

Supported range:

```text
256 MiB to 2048 MiB
```

The memory limit can be disabled:

```powershell
python FolderTally.py "D:\Data" --no-hard-cap
```

Disabling the hard cap removes the Windows Job Object memory restriction for that run.

## Command-Line Options

```text
usage: FolderTally [-h]
                   [-f {txt,json,pdf}]
                   [-o OUTPUT]
                   [--ram-cap-mb RAM_CAP_MB]
                   [--overwrite]
                   [--no-hard-cap]
                   target
```

### `target`

Folder that FolderTally will recursively scan.

```powershell
python FolderTally.py "C:\Users\YourName\Downloads"
```

### `-f`, `--format`

Select the output format.

```powershell
python FolderTally.py "D:\Data" --format json
```

Available formats:

```text
txt
json
pdf
```

Default:

```text
txt
```

### `-o`, `--output`

Choose a custom output file or directory.

```powershell
python FolderTally.py "D:\Data" -o "D:\Reports"
```

### `--ram-cap-mb`

Set the hard memory ceiling.

```powershell
python FolderTally.py "D:\Data" --ram-cap-mb 512
```

Valid range:

```text
256 to 2048 MiB
```

### `--overwrite`

Allow FolderTally to replace an existing custom output file.

```powershell
python FolderTally.py "D:\Data" --format json --output "D:\Reports\data.json" --overwrite
```

Without this option, FolderTally will stop instead of replacing an existing report.

### `--no-hard-cap`

Run without the Windows Job Object memory cap.

```powershell
python FolderTally.py "D:\Data" --no-hard-cap
```

## Example Commands

Scan a folder and create the default TXT report:

```powershell
python FolderTally.py "C:\Users\YourName\Documents"
```

Create a JSON disk usage report:

```powershell
python FolderTally.py "D:\Projects" -f json
```

Create a PDF folder inventory:

```powershell
python FolderTally.py "D:\Archive" -f pdf
```

Save the report to another directory:

```powershell
python FolderTally.py "D:\Projects" -o "D:\Reports"
```

Create a JSON report with a 1 GiB memory ceiling:

```powershell
python FolderTally.py "D:\Projects" -f json --ram-cap-mb 1024
```

Overwrite an existing report:

```powershell
python FolderTally.py "D:\Projects" -f json -o "D:\Reports\projects.json" --overwrite
```

## What FolderTally Records

Each filesystem entry can include information such as:

* Relative path
* Tree depth
* Entry type
* Size in bytes
* Human-readable size
* File extension
* MIME type
* Encoding information when detected by Python's MIME database
* Filesystem access errors

Folder entries also contain the accumulated size of files below that folder.

The report header includes:

* FolderTally version
* Target directory
* Report generation time
* Total file size
* File count
* Folder count
* Link and reparse point count
* Other entry count
* Error count
* Excluded temporary or report file count
* Configured RAM ceiling

## Symbolic Links, Junctions, and Reparse Points

FolderTally does not recursively follow symbolic links, junctions, or nonstandard directory reparse points.

They are included in the inventory, but their targets are not traversed.

This behavior helps keep a scan inside the intended directory tree and avoids recursive filesystem paths caused by links or junctions.

## Error Handling

FolderTally is designed to continue scanning when individual filesystem entries cannot be accessed.

Errors such as permission failures are recorded in the generated report so the affected path can be reviewed afterward.

If the configured memory ceiling is reached, FolderTally stops and reports the condition rather than intentionally continuing without the configured limit.

## TXT Output

TXT reports provide a readable recursive directory inventory.

Example:

```text
00000001 | . | Type=Folder | Size=4.82 GiB | Bytes=5175435591
00000002 |   Projects | Type=Folder | Size=2.10 GiB | Bytes=2254857830
00000003 |     example.zip | Type=File | Size=128.34 MiB | Bytes=134574080 | Extension=.zip | MIME=application/zip
```

Actual values depend on the scanned directory.

## JSON Output

JSON reports contain machine-readable metadata and an `entries` array.

Each entry follows a structure similar to:

```json
{
  "path": "Projects\\example.zip",
  "depth": 2,
  "kind": "File",
  "size_bytes": 134574080,
  "size_human": "128.34 MiB",
  "extension": ".zip",
  "mime_type": "application/zip",
  "encoding": null,
  "error": null
}
```

This makes FolderTally suitable for additional processing, filtering, automation, reporting, or integration with other tools.

## How It Works

FolderTally uses Python's `os.scandir()` to walk the target directory.

Instead of keeping the entire directory inventory in memory, scan records are written to a temporary disk-backed JSONL spool file. Folder sizes are updated as each directory finishes scanning.

After the scan is complete, the spool data is streamed into the selected TXT, JSON, or PDF report format.

On Windows, the optional hard memory ceiling is implemented with Windows Job Objects through Python's `ctypes` interface.

## Project Goals

FolderTally is intended to stay focused on filesystem inventory and folder size analysis.

The main goals are:

* Accurate recursive directory reporting
* Predictable memory usage
* Useful machine-readable output
* Useful human-readable output
* Safe handling of Windows filesystem links
* Minimal dependencies
* Straightforward command-line operation

## License

FolderTally is licensed under the **GNU General Public License v3.0**.

See the [`LICENSE`](LICENSE) file for the complete license terms.

If you modify or redistribute FolderTally, make sure your use and distribution comply with the GPLv3 license.

## Disclaimer

FolderTally reports filesystem information available to the account running the program.

Files or directories that Windows does not permit the process to access may be reported as errors.

Review generated reports before sharing them if the scanned directory contains sensitive filenames, directory names, or filesystem information.
