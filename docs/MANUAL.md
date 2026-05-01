# overlap-calculator User Manual

`overlap-calculator` is a Python package for reproducible batch analysis of
the spectral overlap between a molecular absorption spectrum and a
reference light source. It treats two input families as equal first-class
citizens in the same run:

- **Theoretical** — Gaussian TD-DFT `.out` / `.log` files.
- **Experimental** — tabular spectra as **CSV** (`.csv`), **Excel
  workbook** (`.xlsx`), or **legacy Excel** (`.xls`), with multi-sheet
  and multi-series selection.

Every TD-DFT spectrum is broadened with both **Gaussian** and
**Lorentzian** line shapes, and the tool reports per-light-source
absorbed-flux, absorbed-fraction, and shape-overlap metrics together
with publication-grade TIFF plots.

This manual covers installation, CLI and HTTP API usage, the input and
output schemas, the physical assumptions and exact formulas, and the
environment configuration. For worked end-to-end examples on real data,
see [case_studies/](../case_studies/).

---

## Table of Contents

1. [Overview and Workflow](#1-overview-and-workflow)
2. [Installation](#2-installation)
3. [Quick Start](#3-quick-start)
4. [Command-Line Interface](#4-command-line-interface)
5. [HTTP API](#5-http-api)
6. [Input Format](#6-input-format)
7. [Output Schema](#7-output-schema)
8. [Bundled Light Sources](#8-bundled-light-sources)
9. [Methodology](#9-methodology)
10. [Configuration and Environment Variables](#10-configuration-and-environment-variables)
11. [Troubleshooting](#11-troubleshooting)
12. [Citation and License](#12-citation-and-license)

---

## 1. Overview and Workflow

```
 Gaussian TD-DFT (.out)  ─►  excited states (E, λ, f)
                                     │
                                     ▼                   ┌─── Gaussian broadening ──┐
 Experimental (.csv/.xlsx) ─►  A(λ) ──►  ε(λ),  α(λ)     │                           │
                                     │                   └─── Lorentzian broadening ─┘
                                     ▼
                         × each reference light source
                                     │
                                     ▼
           absorbed_flux, absorbed_fraction, shape_overlap
                                     │
                                     ▼
         results.{csv,json,xlsx}, descriptor_summary.*, skipped_inputs.*,
         absorption / light_source / overlap / overlays TIFF plots
```

Pipeline stages:

1. **Input resolution** — A JSON manifest can be supplied directly or
   auto-generated from a directory of raw files; experimental inputs
   expand one row per numeric series column.
2. **Parsing** — Regex-based TD-DFT parser for `.out` files; pandas-based
   wavelength/signal loader for tabular spectra.
3. **Spectrum reconstruction** — Extinction ε(λ) from TD-DFT states via
   oscillator-strength weighting on a shared wavelength grid; experimental
   signals are treated as absorbance directly.
4. **Beer–Lambert** — α(λ) = 1 − 10^(−A(λ)) with configurable reference
   concentration and path length.
5. **Overlap metrics** — Per (sample, light source, broadening) triplet.
6. **Export** — Tabular (CSV/JSON/XLSX), descriptor summary, skip report,
   and TIFF plots.

---

## 2. Installation

### Requirements

- Python **3.12.x**
- Optional: Conda (recommended) or Docker

### Conda (recommended)

```bash
conda env create -f environment.yml
conda activate overlap-calculator
pip install -e .
```

### venv / pip

```bash
python -m venv .venv
source .venv/bin/activate          # Linux / macOS
# Windows PowerShell: .venv\Scripts\Activate.ps1
# Windows CMD:        .venv\Scripts\activate.bat
pip install -e .
```

### Docker

The Docker image exposes the Flask API on port `8000` *inside* the
container. To keep it from clashing with a native Flask instance on
the host (which uses port `8000` directly), publish it on host port
`8080`:

```bash
docker build -t overlap-calculator .
docker run --rm -p 8080:8000 overlap-calculator
curl http://localhost:8080/health
```

### Docker Compose

For a managed runtime (restart policy, healthcheck, pre-populated
`GAUSS_*` environment), use the bundled compose file. It uses the
same **host port `8080`** mapping as `docker run` above, so the
native instance on `8000` and either docker variant on `8080` can
run side by side:

```bash
docker compose up -d            # starts the `overlap-calculator` service
curl http://localhost:8080/health
docker compose down
```

The compose service uses a Python-stdlib healthcheck against
`/health` and restarts unless explicitly stopped. All runtime
settings in [§10](#10-configuration-and-environment-variables) can
be overridden via the `environment:` block or an adjacent `.env`
file.

### Verify the install

```bash
overlap-calculator version
overlap-calculator --help
```

---

## 3. Quick Start

Drop any combination of the supported input files into `input/files/` —
TD-DFT outputs, CSV spectra, and Excel workbooks can live side by side in
the same directory:

```
input/files/
├── slurm-5473089.out        # Gaussian TD-DFT output (theoretical)
├── dye_panel.xlsx           # Excel workbook, one or more sheets (experimental)
└── uv_vis_run3.csv          # CSV spectrum (experimental)
```

Then run the two-step pipeline:

```bash
# 1. Build the manifest (auto-discovers .out, .csv, .xlsx, .xls)
overlap-calculator generate-input --files-dir input/files --out input/input.json

# 2. Run the full analysis
overlap-calculator analyze --input input/input.json --out output
```

Results land under `output/tables/` and `output/plots/` (see
[§7 Output Schema](#7-output-schema)).

---

## 4. Command-Line Interface

The package installs a single entry point, `overlap-calculator`, with
three subcommands.

### 4.1 `generate-input`

Scans a directory of `.out`/`.csv`/`.xlsx`/`.xls` files and produces a
JSON manifest that enumerates both theoretical `.out` inputs and every
numeric series column in experimental tables.

```
overlap-calculator generate-input --files-dir PATH [--out PATH] [--log-level LEVEL] [--log-format FORMAT]
```

| Flag            | Default            | Description                                         |
| --------------- | ------------------ | --------------------------------------------------- |
| `--files-dir`   | `input/files`      | Directory containing TD-DFT and experimental files  |
| `--out`         | `input/input.json` | Output manifest path                                |
| `--log-level`   | `INFO`             | `DEBUG`, `INFO`, `WARNING`, `ERROR`, `CRITICAL`     |
| `--log-format`  | `text`             | `text` or `json`                                    |

### 4.2 `analyze`

Runs the full pipeline on a manifest and writes all exports.

```
overlap-calculator analyze --input PATH [--out PATH] [--sigma-ev FLOAT] [--wl-min FLOAT] [--wl-max FLOAT] [--num-points INT] [--concentration-m FLOAT] [--path-cm FLOAT] [--default-light-sources STR] [--light-source-file PATH]... [--plot-outputs / --no-plot-outputs] [--plot-dpi INT] [--ranking-outputs / --no-ranking-outputs] [--log-level LEVEL] [--log-format FORMAT]
```

| Flag                       | Default                          | Description                                         |
| -------------------------- | -------------------------------- | --------------------------------------------------- |
| `--input`                  | `input/input.json`               | Manifest JSON (see [§6](#6-input-format))           |
| `--out`                    | `output`                         | Output directory (created if absent)                |
| `--sigma-ev`               | `0.30`                           | Broadening standard deviation in eV                 |
| `--wl-min`                 | `200.0`                          | Lower bound of the wavelength grid, nm              |
| `--wl-max`                 | `800.0`                          | Upper bound of the wavelength grid, nm              |
| `--num-points`             | `10000`                          | Number of grid points between `wl-min` and `wl-max` |
| `--concentration-m`        | `1e-5`                           | Beer–Lambert reference concentration, mol L⁻¹       |
| `--path-cm`                | `1.0`                            | Beer–Lambert reference path length, cm              |
| `--default-light-sources`  | `AM15G,LEDB4,LEDB2,LEDB3,CIEFL10`| Comma-separated list of bundled light sources       |
| `--light-source-file`      | *(none)*                         | Repeatable path to a custom light-source CSV        |
| `--plot-outputs`           | on                               | Emit TIFF plots. Disable with `--no-plot-outputs`   |
| `--plot-dpi`               | `400`                            | TIFF plot resolution; use `600` for larger publication exports |
| `--ranking-outputs`        | on                               | Emit grouped ranking tables and bar charts (gaussian/lorentzian × `absorbed_fraction` / `shape_overlap`). Disable with `--no-ranking-outputs` |
| `--log-level`              | `INFO`                           | Logging verbosity                                   |
| `--log-format`             | `text`                           | `text` or `json`                                    |

### 4.3 `version`

Prints the installed package version.

```bash
overlap-calculator version
```

---

## 5. HTTP API

A Flask-based REST API exposes the same pipeline for bulk uploads.

The examples in this section use port `8000`, which is the **native
Flask** port (started with `python -m overlap_calculator.api.app`).
If you run the same API under **Docker** (either `docker run -p
8080:8000` or `docker compose up`), use port `8080` instead — the
request bodies are otherwise identical.

### 5.1 Endpoints

| Method | Path        | Purpose                                      |
| ------ | ----------- | -------------------------------------------- |
| GET    | `/health`   | Liveness probe — returns `{"status":"ok"}`    |
| POST   | `/analyze`  | Multipart upload; returns a ZIP of results    |

`POST /analyze` accepts the following form fields:

| Form field                | Type               | Description                                                          |
| ------------------------- | ------------------ | -------------------------------------------------------------------- |
| `files`                   | file[] *(req.)*    | Mixed `.out`/`.csv`/`.xlsx`/`.xls` inputs                            |
| `light_source_files`      | file[] (optional)  | Custom light-source CSVs                                             |
| `light_source_csv`        | file (optional)    | Back-compat alias for a single custom light-source CSV                |
| `sigma_ev`                | float (optional)   | Broadening σ, eV (default `0.30`)                                    |
| `wl_min`, `wl_max`        | float (optional)   | Wavelength window bounds, nm                                          |
| `num_points`              | int (optional)     | Grid size (default `10000`)                                          |
| `concentration_m`         | float (optional)   | Beer–Lambert reference concentration (default `1e-5`)                |
| `path_cm`                 | float (optional)   | Beer–Lambert reference path length (default `1.0`)                   |
| `default_light_sources`   | str (optional)     | Comma-separated bundled-source list                                   |
| `plot_outputs`            | bool (optional)    | Enable / disable plot generation                                      |
| `plot_dpi`                | int (optional)     | TIFF plot resolution (default `400`; use `600` for larger exports)    |
| `ranking_outputs`         | bool (optional)    | Enable / disable grouped ranking tables and bar charts (default `true`) |
| `sheet_overrides`         | str (optional)     | JSON object `{"<original-filename>": "<sheet-name>"}` forcing a specific sheet for uploaded `.xlsx`/`.xls` workbooks |

Response: `application/zip` containing every file
`overlap-calculator analyze` would have written. Uploads are processed in
a per-request workspace and are not persisted on the server.

### 5.2 Example

```bash
curl -X POST http://localhost:8000/analyze \
  -F "files=@input/files/theoretical.out" \
  -F "files=@input/files/experimental.xlsx" \
  -F "sigma_ev=0.25" \
  -F "plot_dpi=400" \
  -F "ranking_outputs=true" \
  -F "default_light_sources=AM15G,LEDB4" \
  --output analysis_outputs.zip
```

To force a specific sheet in a multi-sheet workbook, add a
`sheet_overrides` form field whose value is a JSON object keyed by the
original filename:

```bash
curl -X POST http://localhost:8000/analyze \
  -F "files=@input/files/dye_panel.xlsx" \
  -F 'sheet_overrides={"dye_panel.xlsx":"raw"}' \
  --output analysis_outputs.zip
```

Filenames that do not appear in the map use the same auto-discovery as
`generate-input`: the first sheet with a wavelength column and at least
one numeric signal column is selected.

A Postman collection is provided at
[docs/postman_collection.json](postman_collection.json).

---

## 6. Input Format

### 6.1 Accepted input files

`overlap-calculator` accepts two input families in the same run. Both are
first-class: a single manifest can mix them freely, and the pipeline
produces identical downstream columns, plots, and overlap metrics.

| Family         | Extensions                | Parser                                  | Notes                                                                 |
| -------------- | ------------------------- | --------------------------------------- | --------------------------------------------------------------------- |
| Theoretical    | `.out`, `.log`            | Regex-based Gaussian TD-DFT parser       | File must contain a TD route and `Excited State` lines                |
| Experimental   | `.csv`                    | `pandas.read_csv`                        | One wavelength column + one or more numeric signal columns            |
| Experimental   | `.xlsx`, `.xls`           | `pandas.read_excel` (`openpyxl` / `xlrd`) | Multi-sheet workbooks supported via `sheet_name`; `generate-input` auto-selects the first analyzable sheet |

Bulk uploads via the HTTP API share the same matrix (see
`GAUSS_UPLOAD_ALLOWED_EXTS` in [§10](#10-configuration-and-environment-variables)).

### 6.2 Manifest (`input.json`)

```json
[
  {
    "input_type": "theoretical",
    "sample_id": "B1",
    "source_path": "files/slurm-5473089.out",
    "series_name": null,
    "sheet_name": null
  },
  {
    "input_type": "experimental",
    "sample_id": "channel_A",
    "source_path": "files/dye_panel.xlsx",
    "series_name": "channel_A",
    "sheet_name": "raw"
  }
]
```

| Field          | Required | Description                                                                     |
| -------------- | -------- | ------------------------------------------------------------------------------- |
| `input_type`   | yes      | `"theoretical"` (TD-DFT `.out`) or `"experimental"` (tabular spectrum)          |
| `sample_id`    | yes      | Unique sample identifier; used in filenames and result rows                     |
| `source_path`  | yes      | Path to the raw file; resolved relative to the manifest, then to the CWD        |
| `series_name`  | exp.     | Column name of the numeric series in a tabular file                             |
| `sheet_name`   | exp.     | Sheet name for `.xlsx`/`.xls` inputs; in hand-written manifests, omit or `null` to read the first workbook sheet |

`generate-input` fills these automatically. The `sample_id` is derived
as follows:

- **Theoretical (`.out`)** — if the Gaussian route contains a
  `%chk=<name>.chk` line, the checkpoint stem is used (e.g.
  `%chk=B1_td.chk` → `sample_id = "B1_td"`). This keeps human-meaningful
  molecule labels even when the raw files are queue-system artefacts
  such as `slurm-5473089.out`. If no `%chk` line is present, the file
  stem is used as a fallback.
- **Experimental** — one manifest entry is produced per numeric series
  column, with `sample_id = "<series_name>"` (the series column name
  itself, so `Coumarin_1` rather than a long file-stem prefix).

If a manifest is supplied by hand and `sample_id` is omitted, the same
resolution rule is applied at analysis time.

### 6.3 Experimental data template

The same column layout applies to CSV, XLSX, and XLS files.

**CSV (`.csv`)**

```csv
wavelength_nm,sample_A,sample_B
300,0.12,0.08
310,0.15,0.10
320,0.18,0.14
```

**Excel workbook (`.xlsx` / `.xls`)**

The first row is interpreted as the header. Any numeric columns beside
the wavelength axis are treated as independent samples:

| wavelength_nm | channel_A | channel_B | channel_C |
| ------------: | --------: | --------: | --------: |
| 300           | 0.12      | 0.08      | 0.05      |
| 310           | 0.15      | 0.10      | 0.07      |
| 320           | 0.18      | 0.14      | 0.09      |

Multi-sheet workbooks are fully supported. During `generate-input`, if
no sheet override is supplied, the workbook sheets are scanned in order
and the first sheet with a wavelength column and at least one numeric
signal column is selected. In a hand-written manifest, if `sheet_name`
is omitted from an entry (or set to `null`), analysis reads the first
workbook sheet. To force a specific sheet, edit the generated manifest
entry or author it by hand:

```json
{
  "input_type": "experimental",
  "sample_id": "channel_A",
  "source_path": "files/dye_panel.xlsx",
  "series_name": "channel_A",
  "sheet_name": "raw"
}
```

**Shared requirements (both formats)**

- Exactly one wavelength column; accepted aliases (case-insensitive):
  `wavelength`, `wavelength_nm`, `lambda`, `wl`, `nm`. If no named
  wavelength column is found, the first numeric column is used.
- One or more numeric signal columns. Each signal is interpreted as
  absorbance `A(λ)` and fed directly to the Beer–Lambert absorptance
  definition (§[9.2](#92-beerlambert-absorptance)).
- Rows with non-numeric or missing values in either the wavelength or
  signal column are dropped silently; a series must retain at least 10
  valid rows to be analysed.

### 6.4 Custom light sources

A custom light source is a two-column CSV with a wavelength column and a
single numeric intensity column. The filename stem becomes the
`light_source_name` in the results table.

---

## 7. Output Schema

All exports are written to the `--out` directory.

```
output/
├── tables/
│   ├── results.{csv,json,xlsx}
│   ├── results_timings.{csv,json,xlsx}
│   ├── descriptor_summary.{csv,xlsx}
│   ├── ranking_by_light_source__<metric>.{csv,json,xlsx}    # 4 metric variants
│   ├── ranking_by_sample__<metric>.{csv,json,xlsx}           # 4 metric variants
│   └── skipped_inputs.{csv,json}         # emitted only if any inputs were skipped
└── plots/
    ├── absorption/<sample>__absolute.tiff
    ├── absorption/<sample>__normalized.tiff
    ├── light_source/<light>.tiff
    ├── overlap/<sample>__<light>__combined__{absolute,normalized}.tiff
    ├── overlap/<sample>__<light>__<method>__{absolute,normalized}.tiff
    ├── overlays/absorptance_overlay__<method>__{absolute,normalized}.tiff
    ├── ranking/by_light_source/<metric>/<light>.tiff         # bar chart per light source
    └── ranking/by_sample/<metric>/<sample>.tiff              # bar chart per sample
```

`<metric>` cycles through the four overlap descriptors:
`gaussian_absorbed_fraction`, `lorentzian_absorbed_fraction`,
`gaussian_shape_overlap`, `lorentzian_shape_overlap`. The ranking
tables and plots can be suppressed with `--no-ranking-outputs`
(CLI) or `ranking_outputs=false` (API).

### 7.1 `results.*` columns

One row per `(sample_id, light_source_name)` pair. Shared columns:

| Column                          | Description                                                       |
| ------------------------------- | ----------------------------------------------------------------- |
| `source_type`                   | `theoretical` or `experimental`                                   |
| `sample_id`                     | Unique sample identifier                                          |
| `light_source_name`             | `AM15G`, `LEDB1`, `LEDB2`, `LEDB3`, `LEDB4`, `CIEFL10`, or custom stem |
| `sigma_ev`                      | Broadening σ used, eV (theoretical inputs only)                   |
| `light_flux_total`              | ∫ I(λ) dλ over the working grid                                   |
| `reference_concentration_molar` | Beer–Lambert c used, mol L⁻¹                                      |
| `reference_path_cm`             | Beer–Lambert L used, cm                                           |
| `absorption_unit`               | Unit of ε / A in the exported row                                 |
| `light_source_unit`             | Unit of I(λ) (e.g. `W m^-2 nm^-1` for AM1.5G, `relative` for LEDs)|
| `absorbed_flux_unit`            | Unit of the absorbed-flux integral                                |
| `td_method_basis`               | Route metadata from the TD-DFT file (null for experimental)       |
| `td_solvent`                    | PCM solvent from the TD-DFT file (null for experimental)          |

Per-broadening columns (prefixes `gaussian_` and `lorentzian_`):

| Suffix                       | Meaning                                                      |
| ---------------------------- | ------------------------------------------------------------ |
| `lambda_max_nm`              | Peak wavelength of the broadened absorptance                 |
| `molar_absorptivity_max`     | Peak ε in M⁻¹ cm⁻¹ (theoretical only)                        |
| `absorptance_max`            | Peak Beer–Lambert α(λ)                                       |
| `absorbed_flux`              | ∫ α(λ) · I(λ) dλ                                             |
| `absorbed_fraction`          | `absorbed_flux / light_flux_total`, bounded to [0, 1]        |
| `shape_overlap`              | Dimensionless shape comparator on max-normalised spectra     |

Broadening deltas (Gaussian − Lorentzian):
`delta_absorbed_flux`, `delta_absorbed_fraction`, `delta_shape_overlap`,
`abs_delta_absorbed_fraction`.

### 7.2 `descriptor_summary.*`

A condensed table of the most actionable per-sample descriptors across
all light sources, suitable as a starting point for ranking.

### 7.3 `ranking_by_light_source__<metric>.*` and `ranking_by_sample__<metric>.*`

Two complementary grouped rankings answer the two practical questions
that arise from a multi-sample, multi-light-source run:

* **`ranking_by_light_source__<metric>.{csv,json,xlsx}`** — within each
  light source, samples are ordered from the highest to the lowest
  value of the chosen overlap metric. Use this to ask: *"Given this
  light source, which molecule absorbs (or matches in shape) best?"*
* **`ranking_by_sample__<metric>.{csv,json,xlsx}`** — within each
  sample, light sources are ordered the same way. Use this to ask:
  *"For this molecule, which light source gives the strongest overlap?"*

Each table is emitted four times — once per `<metric>` —
covering both broadening methods (`gaussian_*`, `lorentzian_*`) and
both metric families (`absorbed_fraction`, `shape_overlap`):

| `<metric>`                       | Sorts by                                                                                  |
| -------------------------------- | ----------------------------------------------------------------------------------------- |
| `gaussian_absorbed_fraction`     | Beer–Lambert absorbed fraction with Gaussian broadening; intensity-weighted               |
| `lorentzian_absorbed_fraction`   | Beer–Lambert absorbed fraction with Lorentzian broadening; intensity-weighted             |
| `gaussian_shape_overlap`         | Shape-only correlation (intensity-independent) under Gaussian broadening                  |
| `lorentzian_shape_overlap`       | Shape-only correlation (intensity-independent) under Lorentzian broadening                |

Both interpretations are reported because they answer different
scientific questions: `absorbed_fraction` tracks the fraction of
incident photons that are actually absorbed under the chosen
Beer–Lambert reference (`c`, `L`) and is the right figure of merit
for photocatalysis, photovoltaic action, or photo-excitation yield;
`shape_overlap` is a brightness-independent spectral matching score,
appropriate when comparing differently-scaled illuminants on equal
footing.

Each row carries a `rank` column (1 = best within the group) and
all four metric columns side by side, so the file can be re-sorted
client-side without rerunning the pipeline. Companion bar charts
are written to `plots/ranking/by_light_source/<metric>/<light>.tiff`
and `plots/ranking/by_sample/<metric>/<sample>.tiff`; titles and
axis labels embed the chosen metric and the Beer–Lambert reference
conditions to keep the figures unambiguous.

### 7.4 `skipped_inputs.*`

Emitted whenever at least one input was rejected. The `tables/skipped_inputs.{csv,json}` rows carry `sample_id` and `reason` columns. The manifest-side `input/skipped_inputs.json` produced by `generate-input` additionally carries the resolved `source_path`. Each `reason` string is prefixed with the stage at which the input was skipped (`INPUT_SKIPPED` / `INPUT_ERROR` / `ANALYSIS_ERROR`) followed by the error message.

### 7.5 `results_timings.*`

One row per `(sample_id, light_source_name)` pair. Shared columns: `source_type`, `sample_id`, `light_source_name`, `plot_ms`. Each broadening method contributes a 5-column block: `gaussian_parse_tddft_ms`, `gaussian_broadening_ms`, `gaussian_light_source_ms`, `gaussian_integrals_ms`, `gaussian_total_sample_ms` (and the same `lorentzian_*` quintuplet). The row ends with `total_pair_ms` (sum of both methods' `total_sample_ms`) and `total_with_plot_ms` (`total_pair_ms + plot_ms`).

### 7.6 Plots

TIFF plots are emitted at 400 dpi by default and include both absolute
and max-normalised variants. Use `--plot-dpi 600` on the CLI or
`plot_dpi=600` in the API when larger publication-resolution files are
worth the additional disk and transfer size.

| Directory                                | Content                                                                              |
| ---------------------------------------- | ------------------------------------------------------------------------------------ |
| `absorption/`                            | Per-sample absorptance spectra, both broadenings overlaid                            |
| `light_source/`                          | Each reference light source in isolation                                             |
| `overlap/<combined>`                     | (sample, light) overlap — both broadenings on one axes                               |
| `overlap/<method>`                       | (sample, light) overlap — single broadening                                          |
| `overlays/`                              | Multi-sample absorptance overlays for each broadening                                |
| `ranking/by_light_source/<metric>/`      | Bar chart per light source ranking samples by `<metric>` (descending)                |
| `ranking/by_sample/<metric>/`            | Bar chart per sample ranking light sources by `<metric>` (descending)                |

The overlap plots shade the geometric overlap area `min(α(λ), Î(λ))`
(absolute panel) and `min(α̂(λ), Î(λ))` (normalised panel). The shaded
region in the normalised panel is exactly the integrand of
`shape_overlap`, so the figure and the numerical metric report the
same quantity: the area under the lower of the two curves at every
wavelength. The ranking bar charts annotate each
bar with its numerical metric value and embed the metric name and
Beer–Lambert reference conditions in the y-axis label and title.

---

## 8. Bundled Light Sources

| Name      | Source                                                                   | Unit                   |
| --------- | ------------------------------------------------------------------------ | ---------------------- |
| `AM15G`   | NREL ASTM G-173 AM1.5G reference solar spectrum                          | W m⁻² nm⁻¹             |
| `LEDB1`   | CIE 15 illuminant LED-B1 (opt-in; not in default set)                    | relative (shape only)  |
| `LEDB2`   | CIE 15 illuminant LED-B2                                                 | relative (shape only)  |
| `LEDB3`   | CIE 15 illuminant LED-B3                                                 | relative               |
| `LEDB4`   | CIE 15 illuminant LED-B4                                                 | relative               |
| `CIEFL10` | CIE 15 fluorescent illuminant FL10                                       | relative               |

Unit policy: because `AM15G` carries an absolute spectral irradiance,
`absorbed_flux` for AM1.5G has units of W m⁻²; for the relative CIE LED /
FL sources `absorbed_flux_unit` is `relative_integral` and only the
`absorbed_fraction` and `shape_overlap` metrics are directly comparable.

**Third-party spectral data.** The `LEDB1`, `LEDB2`, `LEDB3`, `LEDB4`, and
`CIEFL10` spectra are official **CIE** data sets derived from
*CIE 015:2018 Colorimetry, 4th Edition* (International Commission
on Illumination, <https://cie.co.at/>). The `AM15G` spectrum is the
ASTM G-173-03 AM1.5 global reference distributed by the U.S.
National Renewable Energy Laboratory (NREL). See
[§12](#12-citation-and-license) for full citations and BibTeX
entries.

---

## 9. Methodology

### 9.1 Extinction spectrum from TD-DFT

Each excited state *i* contributes a normalised line profile in
wavenumber space `ν̃ = 10⁷ / λ[nm]` (cm⁻¹):

$$g_i(\tilde\nu) \;=\; \frac{1}{\sigma\sqrt{2\pi}} \exp\!\Bigl(-\frac{(\tilde\nu - \tilde\nu_i)^2}{2\sigma^2}\Bigr)$$

$$l_i(\tilde\nu) \;=\; \frac{1}{\pi}\frac{\gamma}{(\tilde\nu - \tilde\nu_i)^2 + \gamma^2},\qquad \gamma = \sqrt{2\ln 2}\,\sigma \;\approx\; 1.1774\,\sigma$$

with `σ` in cm⁻¹ obtained from the CLI `--sigma-ev` via
`σ_cm⁻¹ = σ_eV · 8065.544`. Here `σ` is the Gaussian standard deviation
(FWHM_G = 2√(2 ln 2)·σ ≈ 2.3548·σ); the Lorentzian half-width-at-half-maximum
`γ` is set to √(2 ln 2)·σ so that **both line shapes share the same FWHM**
under a given `--sigma-ev` value. This keeps the Gaussian–Lorentzian
sensitivity comparison a pure line-shape probe and removes the
implicit width discrepancy that would otherwise bias the `delta_*`
columns. Both profiles are normalised in cm⁻¹: `∫ p(ν̃) dν̃ = 1`. The
molar extinction coefficient is then

$$\varepsilon(\lambda) \;=\; 2.315\times 10^{8}\;\sum_i f_i \, \text{profile}_i\bigl(\tilde\nu(\lambda)\bigr)\quad [\text{M}^{-1}\,\text{cm}^{-1}]$$

where the prefactor comes from the integrated-absorption /
oscillator-strength relation
`∫ ε dν̃ = 2.315·10⁸ · Σ fᵢ`.

### 9.2 Beer–Lambert absorptance

$$A(\lambda) \;=\; \varepsilon(\lambda)\,c\,L,\qquad
  \alpha(\lambda) \;=\; 1 - 10^{-A(\lambda)}$$

with defaults `c = 1·10⁻⁵ M`, `L = 1 cm` (overridable via
`--concentration-m` / `--path-cm`). For experimental inputs the
user-provided signal is treated as absorbance `A` directly and fed to the
same `α` definition without the Beer–Lambert conversion.

### 9.3 Light-overlap metrics

`absorbed_flux` — overlap integral of absorptance and light intensity:

$$\int \alpha(\lambda)\, I(\lambda)\, d\lambda$$

`light_flux_total` — total emitted light flux on the working grid:

$$\int I(\lambda)\, d\lambda$$

`absorbed_fraction` — bounded ratio in `[0, 1]`:

$$\frac{\int \alpha(\lambda)\, I(\lambda)\, d\lambda}{\int I(\lambda)\, d\lambda}$$

`shape_overlap` — strength-independent envelope comparator on
max-normalised shapes `α̂`, `Î`, defined as the geometric overlap area
under the lower of the two profiles, normalised by the area under
the light-source shape:

$$\frac{\int \min\!\bigl(\hat{\alpha}(\lambda),\, \hat{I}(\lambda)\bigr)\, d\lambda}{\int \hat{I}(\lambda)\, d\lambda}$$

This is the classical spectral-overlap-area definition: at every
wavelength the integrand follows whichever of the two normalised
profiles is smaller, so the shaded region in a normalised overlap
plot directly equals the numerator and is bounded above by the lower
curve at all points.

`shape_overlap` lets LED / FL sources (which carry relative
intensities) still be compared meaningfully because it removes the
dependence on absolute spectral strength.

### 9.4 Choosing between `absorbed_fraction` and `shape_overlap`

The two scalar overlap descriptors answer different questions and are
**both** emitted in the ranking tables and bar charts so that no single
metric is forced on the user:

* **`absorbed_fraction`** is the right figure of merit when the
  application cares about the **number of photons (or the energy)
  actually absorbed** under a defined Beer–Lambert reference state
  `(c, L)` — for example, photocatalytic turnover under a given
  illuminant, photovoltaic action spectra, or photo-excitation yield.
  It folds in *both* spectral overlap and the absolute spectral
  intensity of the light source: a brighter source over the absorbing
  band is rewarded.
* **`shape_overlap`** is intensity-independent and answers the
  brightness-blind question *"how well does the light source's
  spectral envelope match the molecule's absorption envelope?"* It
  is the appropriate descriptor when the spectra under comparison
  carry incompatible intensity units (e.g. `W m⁻² nm⁻¹` for AM1.5G
  versus `relative` for the CIE LED templates) and the reader needs
  a fair side-by-side ordering.

Each descriptor is reported under both Gaussian and Lorentzian
broadening (§9.1), so the four ranking tables together expose the
full sensitivity surface to the line-shape choice.

### 9.5 Skip policy

An input is diverted to `skipped_inputs.*` when:

- the `.out` file lacks a TD route (`# … TD…`) or any `Excited State`
  line — tagged `INPUT_SKIPPED: file is not a TD-DFT output`;
- an experimental file cannot be read or has no numeric signal column —
  tagged `INPUT_SKIPPED: failed to read experimental file` /
  `INPUT_SKIPPED: experimental file has no numeric series`;
- parsing fails at analysis time — tagged
  `ANALYSIS_ERROR: Failed to parse …`.

---

## 10. Configuration and Environment Variables

All settings are read via `pydantic-settings` with the `GAUSS_` prefix;
a `.env` file in the working directory is honoured.

| Variable                           | Default                             | Purpose                                         |
| ---------------------------------- | ----------------------------------- | ----------------------------------------------- |
| `GAUSS_LOG_LEVEL`                  | `INFO`                              | Logging verbosity                               |
| `GAUSS_LOG_FORMAT`                 | `text`                              | `text` or `json` (structured)                   |
| `GAUSS_PLOT_OUTPUTS`               | `true`                              | Emit TIFF plots                                 |
| `GAUSS_PLOT_DPI`                   | `400`                               | Default TIFF plot resolution                    |
| `GAUSS_RANKING_OUTPUTS`            | `true`                              | Emit grouped ranking tables and bar charts      |
| `GAUSS_SIGMA_EV`                   | `0.30`                              | Default broadening σ                            |
| `GAUSS_WAVELENGTH_MIN_NM`          | `200.0`                             | Default grid lower bound, nm                    |
| `GAUSS_WAVELENGTH_MAX_NM`          | `800.0`                             | Default grid upper bound, nm                    |
| `GAUSS_WAVELENGTH_POINTS`          | `10000`                             | Default number of grid points                   |
| `GAUSS_REFERENCE_CONCENTRATION_MOLAR` | `1e-5`                           | Beer–Lambert reference concentration             |
| `GAUSS_REFERENCE_PATH_CM`          | `1.0`                               | Beer–Lambert reference path length               |
| `GAUSS_DEFAULT_LIGHT_SOURCES`      | `AM15G,LEDB4,LEDB2,LEDB3,CIEFL10`   | Default bundled-source list                     |
| `GAUSS_UPLOAD_MAX_MB`              | `50`                                | API upload size cap                             |
| `GAUSS_UPLOAD_ALLOWED_EXTS`        | `.out,.log,.csv,.xlsx,.xls`         | Accepted upload extensions                      |

CLI flags override environment variables when both are supplied.

---

## 11. Troubleshooting

**No output generated**
Inspect `output/tables/skipped_inputs.*` first and re-run with
`--log-level DEBUG`. A common cause is a `.out` file that is an OPT job,
not a TD-DFT job, and therefore contains no `Excited State` blocks.

**`ParseError` on an experimental file**
Confirm that one column is a wavelength axis (alias list above) and at
least one other column is numeric. Non-numeric / date-formatted columns
are dropped silently.

**Custom light source is ignored**
Check that the file has exactly one wavelength column and one numeric
intensity column. The filename stem becomes the `light_source_name`; if
that name collides with a bundled source the custom file wins.

**CLI options seem outdated**
After switching branches, re-install the package: `pip install -e .`.

**Unexpected absorbed_fraction near 0 for a CIE LED source**
Check that the molecule's λ_max falls within the LED emission band.
`shape_overlap` is often more informative than `absorbed_fraction` for
narrow-band relative sources.

---

## 12. Citation and License

If you use `overlap-calculator` in published work, please cite the
concept DOI below. It resolves to the latest archived release on
Zenodo, so the citation stays valid across versions without needing
an update.

> Seyitdanlıoğlu, P. *overlap-calculator: Batch spectral-overlap analysis
> between TD-DFT / experimental absorption and reference light sources.*
> Zenodo. <https://doi.org/10.5281/zenodo.19944515>

BibTeX:

```bibtex
@software{seyitdanlioglu_overlap_calculator,
  author    = {Seyitdanlıoğlu, Pınar},
  title     = {{overlap-calculator}: Batch spectral-overlap analysis
               between TD-DFT / experimental absorption and reference
               light sources},
  year      = {2026},
  publisher = {Zenodo},
  doi       = {10.5281/zenodo.19944515},
  url       = {https://doi.org/10.5281/zenodo.19944515}
}
```

### Acknowledgement of third-party data

The bundled CIE LED illuminants (`LEDB1`, `LEDB2`, `LEDB3`, `LEDB4`)
and fluorescent illuminant (`CIEFL10`) are official **CIE** data
sets derived from *CIE 015:2018 Colorimetry, 4th Edition*. The
`AM15G` spectrum is the ASTM G-173-03 AM1.5 global reference
distributed by the U.S. National Renewable Energy Laboratory (NREL).
The bundled experimental absorbance workbook
(`input/files/organic_uvvis_photochemcad_dataset.xlsx`) is derived
from the **PhotochemCAD** spectral database. If you use
`overlap-calculator` in published work, please cite the data sets
alongside the software:

> CIE (2018). *Relative spectral power distributions of illuminants
> representing typical LED lamps, 1 nm spacing.* International
> Commission on Illumination, Vienna, AT.
> DOI: [10.25039/CIE.DS.dhcw57sd](https://doi.org/10.25039/CIE.DS.dhcw57sd)

> CIE (2018). *Relative spectral power distributions of illuminants
> representing typical fluorescent lamps, 1 nm wavelength steps.*
> International Commission on Illumination, Vienna, AT.
> DOI: [10.25039/CIE.DS.54hy6srn](https://doi.org/10.25039/CIE.DS.54hy6srn)

> CIE (2018). *CIE 015:2018 Colorimetry, 4th Edition.*
> International Commission on Illumination, Vienna, AT.
> <https://cie.co.at/publications/colorimetry-4th-edition/>

> NREL. *Reference Air Mass 1.5 Spectra (ASTM G-173-03).* U.S.
> National Renewable Energy Laboratory.
> <https://www.nrel.gov/grid/solar-resource/spectra-am1.5.html>

> Taniguchi, M., & Lindsey, J. S. (2018). Database of absorption and
> fluorescence spectra of >300 common compounds for use in PhotochemCAD.
> *Photochemistry and Photobiology*, **94**(2), 290–327.
> DOI: [10.1111/php.12860](https://doi.org/10.1111/php.12860)

BibTeX:

```bibtex
@techreport{cie_led_illuminants_2018,
  author      = {{International Commission on Illumination}},
  title       = {Relative spectral power distributions of illuminants
                 representing typical {LED} lamps, 1\,nm spacing},
  institution = {CIE Central Bureau},
  address     = {Vienna, AT},
  year        = {2018},
  doi         = {10.25039/CIE.DS.dhcw57sd},
  url         = {https://doi.org/10.25039/CIE.DS.dhcw57sd}
}

@techreport{cie_fl_illuminants_2018,
  author      = {{International Commission on Illumination}},
  title       = {Relative spectral power distributions of illuminants
                 representing typical fluorescent lamps, 1\,nm wavelength steps},
  institution = {CIE Central Bureau},
  address     = {Vienna, AT},
  year        = {2018},
  doi         = {10.25039/CIE.DS.54hy6srn},
  url         = {https://doi.org/10.25039/CIE.DS.54hy6srn}
}

@techreport{cie_015_2018,
  author      = {{International Commission on Illumination}},
  title       = {{CIE} 015:2018 Colorimetry, 4th Edition},
  institution = {CIE Central Bureau},
  address     = {Vienna, AT},
  year        = {2018},
  isbn        = {978-3-902842-13-8}
}

@misc{nrel_am15g,
  author       = {{National Renewable Energy Laboratory}},
  title        = {Reference Air Mass 1.5 Spectra ({ASTM} {G-173-03})},
  howpublished = {\url{https://www.nrel.gov/grid/solar-resource/spectra-am1.5.html}},
  institution  = {U.S. Department of Energy}
}

@article{taniguchi_lindsey_photochemcad_2018,
  author  = {Taniguchi, Masahiko and Lindsey, Jonathan S.},
  title   = {Database of Absorption and Fluorescence Spectra of
             {>}300 Common Compounds for Use in {PhotochemCAD}},
  journal = {Photochemistry and Photobiology},
  volume  = {94},
  number  = {2},
  pages   = {290--327},
  year    = {2018},
  doi     = {10.1111/php.12860},
  url     = {https://doi.org/10.1111/php.12860}
}
```

Please consult the CIE at <https://cie.co.at/> for the authoritative
reference tables and the latest errata.

`overlap-calculator` is released under the **GNU General Public License
v3.0 or later** (see [LICENSE](../LICENSE)).
