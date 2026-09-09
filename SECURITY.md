# Security

## Supported version

Security fixes are intended for the current 1.x code line. Older prototypes and superseded portable builds are not maintained. Version 1.0.0 is being prepared; no release date or response-time guarantee is implied.

## Private reporting

Send vulnerability reports to **pradafitdev@gmail.com**. Do not post exploit details, credentials, personal inventories, or private paths in public issues. Include the affected version or EXE SHA-256, Windows version, impact, and minimal steps using synthetic data. Do not send a runnable exploit or user report bundle unless requested through that private channel.

## Boundaries

FolderTally inventories metadata using your account's permissions. It is not an antivirus, forensic snapshot, or sandbox for hostile filesystems. Detected links and reparse points are not followed, and directory opening includes fresh checks. Path-based checks cannot eliminate all races when another process changes directories or ancestors concurrently. Avoid actively hostile trees.

No account, telemetry, update service, or application network client is included. The application writes reports, temporary scan files, and three display preferences. Reports can expose filenames and folder names. Keep the portable runtime folder in a location that untrusted users cannot modify. Replacing a DLL changes the code that runs; use replacements you trust.

The EXE is unsigned. A checksum detects a change relative to a trusted checksum, but is not a publisher signature. No test or scan proves the absence of vulnerabilities.

## Known dependency limitation

The current Python 3.14.7 runtime includes Expat 2.8.2. Upstream Expat 2.8.3 and 2.8.4 contain additional security fixes, tracked in [CPython's update issue](https://github.com/python/cpython/issues/156723). The PDF library imports Expat, so the component is present in the portable package.

FolderTally does not accept XML documents or external PDFs. Its desktop export creates its own PDF and fixed metadata; a regression check confirms that this route does not construct an Expat XML parser. That limits exposure but does not patch the library. A fixed, compatible runtime or a separately reviewed removal of this dependency is needed before treating this item as resolved. Do not describe this build as free of known vulnerable components.
