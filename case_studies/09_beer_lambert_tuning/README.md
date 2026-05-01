# Case Study 09 — Beer–Lambert Tuning

Change the **reference concentration** and **path length** used in the Beer–Lambert step. Both knobs enter the absorptance only through their product, `c · L`. Here we raise the concentration by a factor of 10 (`1e-5 M → 1e-4 M`) and shorten the path by a factor of 10 (`1.0 cm → 0.1 cm`), so the product stays the same.

The user-selectable knobs are:

- CLI: `--concentration-m FLOAT` (mol L⁻¹) and `--path-cm FLOAT` (cm)
- API: form fields `concentration_m=FLOAT` and `path_cm=FLOAT`

The defaults are `1e-5 M` and `1.0 cm`, giving a product of `1e-5 mol L⁻¹ · cm` that keeps `absorptance_max` below ~0.9 for most of the bundled dyes.

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
overlap-calculator analyze --input case_studies/09_beer_lambert_tuning/input.json --out case_studies/09_beer_lambert_tuning/output/cli --default-light-sources AM15G,LEDB4 --concentration-m 1e-4 --path-cm 0.1 --plot-dpi 400
```

After the run, `case_studies/09_beer_lambert_tuning/output/cli/` contains a
`tables/` directory (and a `plots/` directory unless plots were
disabled). The `--default-light-sources` flag pins the bundled sources
to AM1.5G + LED-B4; remove it to compare against the full default set
(`AM15G,LEDB4,LEDB2,LEDB3,CIEFL10`).

---

## 4. Run with the HTTP API

Start the API as documented in
[Case Study 01 §1](../01_theoretical_only/README.md#1-prerequisites)
and verify with `curl http://localhost:8000/health` (or `:8080` if you
started the API via `docker compose`). Then submit the
same uploads in one curl command:

```bash
curl -X POST http://localhost:8000/analyze -F "files=@input/files/slurm-5473089.out" -F "files=@input/files/slurm-5473178.out" -F "default_light_sources=AM15G,LEDB4" -F "concentration_m=1e-4" -F "path_cm=0.1" -F "plot_dpi=400" --output case_studies/09_beer_lambert_tuning/output/api/analysis_outputs.zip
```

Each `-F "files=@..."` is one upload. The form fields mirror the CLI
flags. The response is a ZIP archive saved as
`output/api/analysis_outputs.zip`.

---

## 5. Drive both interfaces from one Python script

Instead of typing the commands above, run [`submit.py`](submit.py) from
the repository root:

```bash
python case_studies/09_beer_lambert_tuning/submit.py
```

The script reads `input.json`, runs the CLI step (writing to
`output/cli/`), then POSTs the same uploads to `/analyze` and unpacks
the response into `output/api/`. If the API is not reachable, it
prints a hint and exits cleanly without failing the CLI step.

---

## 6. Expected output layout

```text
case_studies/09_beer_lambert_tuning/output/
+-- cli/
|   +-- tables/results.{csv,json,xlsx}        (2 samples × 2 light sources = 4 rows (c = 1e-4 M, L = 0.1 cm))
|   +-- tables/results_timings.{csv,json,xlsx}
|   +-- tables/descriptor_summary.{csv,xlsx}
|   +-- tables/ranking_by_light_source__<metric>.{csv,json,xlsx}   (gaussian/lorentzian x absorbed_fraction/shape_overlap)
|   +-- tables/ranking_by_sample__<metric>.{csv,json,xlsx}          (same four metric variants)
|   +-- plots/                                                      (also plots/ranking/by_light_source/<metric>/ and plots/ranking/by_sample/<metric>/)
+-- api/
    +-- analysis_outputs.zip
    +-- tables/...
    +-- plots/...
```

API sample IDs are auto-generated from each upload's `%chk` header,
while the CLI uses the `sample_id` you set in `input.json`. This is
the only cosmetic difference between the two trees; the tables align
row by row otherwise.

---

## 7. Related case studies

- [Case Study 08 — Broadening Sigma](../08_broadening_sigma/README.md)
- [Case Study 10 — Wavelength Grid](../10_wavelength_grid/README.md)
- [Case Study 01 — Theoretical Only](../01_theoretical_only/README.md)
