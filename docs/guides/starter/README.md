# SensOS Starter Guide — PDF edition

Content source of truth (do not fork claims):

`sensos-ux/docs/SENSOS_STARTER_GUIDE.md`

## Build

```bash
cd docs/guides/starter
latexmk -xelatex -interaction=nonstopmode SensOS_Starter_Guide.tex
```

Output: `SensOS_Starter_Guide.pdf`

Requires TeX Live with `fontspec`, `tikz`, `tcolorbox`, `hyperref`, `listings`, and TeX Gyre fonts.
