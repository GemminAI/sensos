# SensOS Starter Guide — PDF build / validation report

**Date:** 2026-08-22  
**Repository:** `GemminAI/sensos`  
**Task:** PDF production only (no app/installer/Technical Guide changes)

## Deliverables

| File | Role |
| --- | --- |
| `docs/guides/starter/SensOS_Starter_Guide.tex` | LaTeX source |
| `docs/guides/starter/SensOS_Starter_Guide.pdf` | Official PDF edition |
| `docs/guides/starter/.latexmkrc` | Reproducible `latexmk` config (XeLaTeX) |
| `docs/guides/starter/README.md` | Build instructions |

## Content source of truth

Markdown (unchanged by this task):

`/Users/tomonam3/GemminAI/sensos-ux/docs/SENSOS_STARTER_GUIDE.md`

No substantive claims were invented or softened for the PDF. Support boundary preserved:

- Linux installer: supported
- Ubuntu 24.04: verified
- macOS / Apple Silicon: not supported by this installer
- Windows: not supported by this installer

## Build

```bash
cd docs/guides/starter
latexmk -xelatex -interaction=nonstopmode SensOS_Starter_Guide.tex
```

**Result:** success — 12 pages, A4, ~74–76 KB.

**Engine / fonts:** XeLaTeX + TeX Gyre Heros / TeX Gyre Cursor (TeX Live 2026 paths).

## Validation checklist

| Check | Result |
| --- | --- |
| Compiles without errors | PASS |
| Missing references | PASS (none) |
| Missing Unicode glyphs (final) | PASS (after replacing unsupported ↔ / ≥) |
| Clickable TOC | PASS |
| PDF bookmarks | PASS (hyperref + bookmark) |
| PDF metadata Title/Author/Subject/Keywords | PASS |
| Support boundary text present | PASS |
| Install / Launch commands present verbatim | PASS |
| HANKO intents ACCEPT/REJECT/OVERRIDE/ESCALATE | PASS |
| “What this guide deliberately skips” present | PASS |
| Public URLs (sensos / sensos-ux / sensos-docs / sensos.org) | PASS in extracted text |
| Private repo URLs / NVS-KERNEL-IP | PASS — not present |
| Markdown section coverage | PASS (all `##` sections represented) |
| Overfull boxes | 0 after final line-break fix (was 1 minor) |

## Integrity note

ASCII flow arrows (`↓`, `→`) and some fenced diagram lines are rendered as TikZ diagrams rather than monospace ASCII. Meaning is preserved; no new architecture was introduced.

## Final quality test

> If someone who has never used SensOS downloads this PDF, can they understand what SensOS is, install it on the currently supported platform, launch it, and understand Goal → Harness → Run → Trajectory without the Technical Guide?

**Yes** — Install → Launch → Start Building is the primary path; Studio is marked ADVANCED.
