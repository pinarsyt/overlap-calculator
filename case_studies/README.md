# overlap-calculator Case Studies

This directory contains 15 worked case studies, each isolating one
**user-selectable feature** of `overlap-calculator`. Case studies 01–11
ship in three documentation formats — Markdown, LaTeX source, and a
typeset PDF. Case studies 12–15 ship in Markdown and LaTeX source
(PDFs are built separately).

Each case study is intentionally small (**2 samples × 2 light
sources**) so a full run finishes in seconds and the repository stays
lean. The case isolates one knob at a time: light source, plot DPI,
broadening width, Beer–Lambert reference, wavelength grid, sheet
selection, etc.

---

## Layout shared by every case

```text
case_studies/<NN>_<name>/
+-- input.json
+-- submit.py
+-- README.md
+-- README.tex
+-- README.pdf
+-- output/
    +-- cli/
    |   +-- tables/{results,results_timings,descriptor_summary}.*
    |   +-- plots/...
    +-- api/
        +-- analysis_outputs.zip
        +-- tables/...
        +-- plots/...
```

`input.json` is the 2-entry manifest that points at the bundled files
under [`../input/files/`](../input/files/). `submit.py` drives both
the CLI and the HTTP API in one run. The Markdown README is the
narrative for the case; the LaTeX and PDF carry the same content in
typeset form. The `output/` tree is produced once you run
`submit.py`; case study 07 produces no `plots/` directory because it
turns plotting off.

---

## Case study index

If this is your first time using `overlap-calculator`, start with
**Case Study 01** — its **§1 Prerequisites** is the install /
environment / API-startup walkthrough that every other case study
links to instead of repeating.

| Case | Folder | Feature exercised | Inputs | LaTeX | PDF |
| ---- | ------ | ----------------- | ------ | :---: | :---: |
| 01 | [`01_theoretical_only`](01_theoretical_only/README.md) | Canonical TD-DFT-only workflow (anchor) | 2 `.out` | [tex](01_theoretical_only/README.tex) | [pdf](01_theoretical_only/README.pdf) |
| 02 | [`02_experimental_only`](02_experimental_only/README.md) | Measured spectra only | 2 series in 1 `.xlsx` | [tex](02_experimental_only/README.tex) | [pdf](02_experimental_only/README.pdf) |
| 03 | [`03_mixed_theory_experiment`](03_mixed_theory_experiment/README.md) | Theoretical + experimental in one manifest | 2 `.out` + 2 series | [tex](03_mixed_theory_experiment/README.tex) | [pdf](03_mixed_theory_experiment/README.pdf) |
| 04 | [`04_custom_light_source`](04_custom_light_source/README.md) | `--light-source-file` / `light_source_files` | 2 `.out` + 1 CSV | [tex](04_custom_light_source/README.tex) | [pdf](04_custom_light_source/README.pdf) |
| 05 | [`05_default_light_source_selection`](05_default_light_source_selection/README.md) | `--default-light-sources` subset | 2 `.out` | [tex](05_default_light_source_selection/README.tex) | [pdf](05_default_light_source_selection/README.pdf) |
| 06 | [`06_plot_dpi`](06_plot_dpi/README.md) | `--plot-dpi 600` for publication TIFFs | 2 `.out` | [tex](06_plot_dpi/README.tex) | [pdf](06_plot_dpi/README.pdf) |
| 07 | [`07_table_only`](07_table_only/README.md) | `--no-plot-outputs` / `plot_outputs=false` | 2 `.out` | [tex](07_table_only/README.tex) | [pdf](07_table_only/README.pdf) |
| 08 | [`08_broadening_sigma`](08_broadening_sigma/README.md) | `--sigma-ev` (0.30 → 0.20 eV) | 2 `.out` | [tex](08_broadening_sigma/README.tex) | [pdf](08_broadening_sigma/README.pdf) |
| 09 | [`09_beer_lambert_tuning`](09_beer_lambert_tuning/README.md) | `--concentration-m` and `--path-cm` | 2 `.out` | [tex](09_beer_lambert_tuning/README.tex) | [pdf](09_beer_lambert_tuning/README.pdf) |
| 10 | [`10_wavelength_grid`](10_wavelength_grid/README.md) | `--wl-min` / `--wl-max` / `--num-points` | 2 `.out` | [tex](10_wavelength_grid/README.tex) | [pdf](10_wavelength_grid/README.pdf) |
| 11 | [`11_sheet_overrides`](11_sheet_overrides/README.md) | `sheet_name` (CLI) / `sheet_overrides` (API) | 2 series in 1 `.xlsx` | [tex](11_sheet_overrides/README.tex) | [pdf](11_sheet_overrides/README.pdf) |
| 12 | [`12_frequency_resolved_prefactor`](12_frequency_resolved_prefactor/README.md) | `--prefactor-mode frequency-resolved` | 2 `.out` | [tex](12_frequency_resolved_prefactor/README.tex) | — |
| 13 | [`13_marcus_hush_width`](13_marcus_hush_width/README.md) | `--sigma-mode marcus-hush` + `--reorganization-ev` | 2 `.out` | [tex](13_marcus_hush_width/README.tex) | — |
| 14 | [`14_calibration_block`](14_calibration_block/README.md) | `--calibration PATH` (TOML; CLI/library only) | 2 `.out` | [tex](14_calibration_block/README.tex) | — |
| 15 | [`15_vibronic_tabular_branch`](15_vibronic_tabular_branch/README.md) | Vibronic/Franck–Condon spectra via experimental branch | 2 series in 1 `.xlsx` | [tex](15_vibronic_tabular_branch/README.tex) | — |

---

## Bundled inputs

Every case study draws from the same files in
[`../input/files/`](../input/files/):

- 13 Gaussian TD-DFT outputs (the case studies use 2 of them to keep runs short).
- One PhotochemCAD-derived Excel workbook with 8 numeric absorbance series (the case studies use 2 of them).

> **Citation for the experimental workbook.** The bundled experimental
> absorbance data is derived from M. Taniguchi & J. S. Lindsey,
> "Database of absorption and fluorescence spectra of >300 common
> compounds for use in PhotochemCAD", *Photochem. Photobiol.* **94**
> (2018) 290–327. See the project
> [README](../README.md#acknowledgement-of-third-party-data) for the
> full acknowledgement and BibTeX entries (covering both the bundled
> light sources and the experimental workbook).
