# Case Study 13 — Marcus–Hush Width

Replace the fixed broadening sigma with the classical Marcus–Hush
Gaussian width derived from a reorganization energy and temperature:

```
σ = sqrt(2 · λ · k_B · T)
```

At λ = 0.30 eV and T = 298.15 K this gives σ = 0.12416 eV
(FWHM = 0.29234 eV), which is narrower than the default σ = 0.30 eV.
Each excited state therefore gets a different effective sigma when the
calibration block supplies per-band reorganization energies (see
[Case Study 14](../14_calibration_block/README.md)); without a
calibration all transitions share the same σ derived from
`--reorganization-ev`.

The user-selectable knobs are:

- CLI: `--sigma-mode marcus-hush`, `--reorganization-ev FLOAT`,
  `--temperature-k FLOAT`
- API: form fields `sigma_mode=marcus-hush`, `reorganization_ev=FLOAT`,
  `temperature_k=FLOAT`

> **Physics note.** This is the classical high-temperature Marcus–Hush
> limit. For organic vibrational baths (~1400 cm⁻¹) ℏω >> k_B·T, so
> the result is a first-order estimate rather than a quantitative
> bandshape. For quantitative work use vibronic spectra via the
> experimental/tabular input branch (see
> [Case Study 15](../15_vibronic_tabular_branch/README.md)).

---

## What you will produce

Everything is written under one `output/` directory inside this case study folder:

| Folder | By | Contents |
| --- | --- | --- |
| `output/cli/tables/` | CLI | Result tables (CSV / JSON / XLSX) |
| `output/cli/plots/` | CLI | TIFF plots per sample, light source, and (sample, light) pair |
| `output/api/` | API | Same `tables/` and `plots/` tree, extracted from the ZIP |
| `output/api/analysis_outputs.zip` | API | Raw ZIP response |

Light sources used: **AM1.5G + LED-B4**.

---

## 1. Prerequisites

If you have never run any case study before, follow [Case Study 01 §1
Prerequisites](../01_theoretical_only/README.md#1-prerequisites) once
to install the package, the `requests` library, and either the Python
or Docker option for the HTTP API. Every case study uses the same
environment.

---

## 2. Inputs

The case-study `input.json` lists 2 Gaussian TD-DFT outputs. The manifest uses
relative paths that point at the bundled data under
[`../../input/files/`](../../input/files/), so no files are copied or
duplicated. To swap in your own data, replace `input.json` with a
manifest of the same shape; you do not need to touch `submit.py`.

## 3. Run with the CLI

Open a terminal at the repository root, then run a single command:

```bash
overlap-calculator analyze --input case_studies/13_marcus_hush_width/input.json --out case_studies/13_marcus_hush_width/output/cli --default-light-sources AM15G,LEDB4 --sigma-mode marcus-hush --reorganization-ev 0.30 --temperature-k 298.15 --plot-dpi 400
```

After the run, `case_studies/13_marcus_hush_width/output/cli/` contains
a `tables/` directory and a `plots/` directory. The `sigma_ev` column in
`results.*` shows the resolved Marcus–Hush sigma (≈ 0.12416 eV for the
defaults above). The `run_manifest.json` records `sigma_mode`,
`reorganization_ev`, and `temperature_k` in its `parameters` block.

---

## 4. Run with the HTTP API

Start the API as documented in
[Case Study 01 §1](../01_theoretical_only/README.md#1-prerequisites)
and verify with `curl http://localhost:8000/health` (or `:8080` if you
started the API via `docker compose`). Then submit the
same uploads in one curl command:

```bash
curl -X POST http://localhost:8000/analyze -F "files=@input/files/slurm-2829207.out" -F "files=@input/files/slurm-2829212.out" -F "default_light_sources=AM15G,LEDB4" -F "sigma_mode=marcus-hush" -F "reorganization_ev=0.30" -F "temperature_k=298.15" -F "plot_dpi=400" --output case_studies/13_marcus_hush_width/output/api/analysis_outputs.zip
```

Each `-F "files=@..."` is one upload. The form fields mirror the CLI
flags. The response is a ZIP archive saved as
`output/api/analysis_outputs.zip`.

---

## 5. Drive both interfaces from one Python script

Instead of typing the commands above, run [`submit.py`](submit.py) from
the repository root:

```bash
python case_studies/13_marcus_hush_width/submit.py
```

The script reads `input.json`, runs the CLI step (writing to
`output/cli/`), then POSTs the same uploads to `/analyze` and unpacks
the response into `output/api/`. If the API is not reachable, it
prints a hint and exits cleanly without failing the CLI step.

---

## 6. Expected output layout

```text
case_studies/13_marcus_hush_width/output/
+-- cli/
|   +-- run_manifest.json
|   +-- tables/results.{csv,json,xlsx}        (2 samples × 2 light sources = 4 rows)
|   +-- tables/results_timings.{csv,json,xlsx}
|   +-- tables/descriptor_summary.{csv,xlsx}
|   +-- tables/ranking_by_light_source__<metric>.{csv,json,xlsx}
|   +-- tables/ranking_by_sample__<metric>.{csv,json,xlsx}
|   +-- plots/
+-- api/
    +-- analysis_outputs.zip
    +-- tables/...
    +-- plots/...
```

Inspect `tables/results.csv`: the `sigma_ev` column shows the resolved
Marcus–Hush sigma (≈ 0.12416 eV for λ = 0.30 eV at 298.15 K). The
`sigma_mode` column shows `marcus-hush`.

---

## 7. What to compare

- Compare `gaussian_molar_absorptivity_max` against the default
  σ = 0.30 eV run (Case Study 01 or 08): the narrower Marcus–Hush
  sigma produces taller, narrower peaks.
- Re-run with `--reorganization-ev 0.60` to see how a larger
  reorganization energy widens the band.

---

## 8. Related case studies

- [Case Study 08 — Broadening Sigma](../08_broadening_sigma/README.md)
- [Case Study 12 — Frequency-Resolved Prefactor](../12_frequency_resolved_prefactor/README.md)
- [Case Study 14 — Calibration Block](../14_calibration_block/README.md)
- [Case Study 15 — Vibronic Tabular Branch](../15_vibronic_tabular_branch/README.md)
