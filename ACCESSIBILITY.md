# Accessibility

FolderTally targets Revised Section 508 and WCAG 2.1 Level AA for its Windows desktop interface and generated reports. Full conformance has not been established. No certification or VPAT/ACR is claimed.

## Available features

- Named controls, roles, states, keyboard focus, and status announcements through Qt's Windows accessibility support.
- Tab/Shift+Tab navigation, labeled keyboard shortcuts, visible focus, and an accessible scan-cancellation confirmation.
- System, light, and dark themes; Windows high-contrast preferences take priority.
- Text sizes from 100% to 400%, responsive layouts, and scrolling that follows keyboard focus.
- Desktop PDF 1.7 reports with embedded text fonts, language and title metadata, ordered tags, marked decorative content, and PDF/UA-1 identification.

## Verification and limits

Automated regression tests cover keyboard navigation, focus, preference handling, cancellation, PDF structure, and report contents. Layout checks cover light, dark, and simulated high contrast at all six text sizes and three window sizes. Native Windows UI Automation checks cover named controls, dropdowns, dialogs, exports, and monitor restoration.

Representative desktop reports pass veraPDF 1.30.2's PDF/UA-1 machine checks. Those checks do not establish human reading-order quality or screen-reader usability. Unicode characters outside the bundled font's coverage are written as explicit Unicode escapes in PDF; TXT and JSON retain the original characters. The legacy command-line Print-to-PDF route does not share the desktop PDF accessibility implementation.

Remaining human checks include Narrator and NVDA reading/navigation, actual Windows contrast themes, high-DPI combinations, PDF reading order and spoken output in an accessible reader, and review of all applicable success criteria. Recheck these on the final distributed build. Automated test results are not a whole-product compliance finding.

## Report an accessibility issue

Email pradafitdev@gmail.com with the app version, Windows version, assistive technology and version, text size/theme, and steps to reproduce. Use synthetic folder names and redact screenshots before sharing.

References: [Revised Section 508, Chapter 5](https://www.access-board.gov/ict/#chapter-5-software), [WCAG 2.1](https://www.w3.org/TR/WCAG21/), [WCAG2ICT](https://www.w3.org/TR/wcag2ict/), and [veraPDF validation scope](https://docs.verapdf.org/validation/).
