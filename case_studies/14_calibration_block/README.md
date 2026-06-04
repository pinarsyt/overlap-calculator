# Case Study 14 — Calibration Block

Apply a TOML calibration before broadening. The calibration block can
shift TD-DFT excitation energies with a linear map, scale oscillator
strengths, and override the broadening width or reorganization energy
per excited state.

The calibration is applied **before** broadening. Wavelength is
recomputed from the calibrated energy via `λ = 1239.841984 / E_cal`
only when the linear energy map is non-identity. The identity
calibration (`a=1`, `b=0`, `α=1`, no band overrides) produces
bit-identical output to running without `--calibration`.

The user-selectable knob is:

- CLI: `--calibration PATH` (path to a TOML file)
- Library: `calibration=Calibration(...)` parameter of `analyze()`

> **Note.** The HTTP API does not accept calibration files. Use the
> CLI or the Python library for this feature.

---

## TOML schema

```toml
[energy]
a = 1.0    # multiplicative factor (default 1.0 = identity)
b = 0.0    # additive shift in eV (default 0.0)

[oscillator]
alpha = 1.0   # scaling factor for all oscillator strengths (default 1.0)

[[band]]
index = 1           # 1-based excited-state index
sigma_ev = 0.25     # width override in eV (optional)
reorganization_ev = 0.40  # Marcus-Hush reorganization energy (optional)
```

All sections and all keys are optional. Omitted keys take identity or
default values.

---

## What you will produce

Everything is written under one `output/` directory inside this case study folder:

| Folder | By | Contents |
| --- | --- | --- |
| `output/cli/tables/` | CLI | Result tables (CSV / JSON / XLSX) |
| `output/cli/plots/` | CLI | TIFF plots per sample, light source, and (sample, light) pair |

Light sources used: **AM1.5G + LED-B4**.

---

## 1. Prerequisites

If you have never run any case study before, follow [Case Study 01 §1
Prerequisites](../01_theoretical_only/README.md#1-prerequisites) once
to install the package and either the Python or Docker option for the
HTTP API. Every case study uses the same environment.

---

## 2. Inputs

The case-study `input.json` lists 2 Gaussian TD-DFT outputs. The manifest uses
relative paths that point at the bundled data under
[`../../input/files/`](../../input/files/), so no files are copied or
duplicated.

The case study includes a `calib.toml` file that leaves energy and
oscillator scaling at their identity values and overrides the width of
the first excited state to `sigma_ev = 0.25` eV:

```toml
[energy]
a = 1.0    # multiplicative factor (identity — no energy scaling)
b = 0.0    # additive shift in eV (identity — no energy shift)

[oscillator]
alpha = 1.0   # scaling factor for all oscillator strengths (identity)

[[band]]
index = 1           # 1-based excited-state index
sigma_ev = 0.25     # width override in eV for the first excited state
```

## 3. Run with the CLI

Open a terminal at the repository root, then run a single command:

```bash
overlap-calculator analyze --input case_studies/14_calibration_block/input.json --out case_studies/14_calibration_block/output/cli --default-light-sources AM15G,LEDB4 --calibration case_studies/14_calibration_block/calib.toml --plot-dpi 400
```

After the run, `case_studies/14_calibration_block/output/cli/` contains
a `tables/` directory and a `plots/` directory. The `run_manifest.json`
at the output root records the full calibration block under
`parameters.calibration`.

---

## 4. HTTP API

The HTTP API does not accept calibration files. Use the CLI or the
Python library for this feature.

---

## 5. Drive the CLI from one Python script

Instead of typing the command above, run [`submit.py`](submit.py) from
the repository root:

```bash
python case_studies/14_calibration_block/submit.py
```

---

## 6. Expected output layout

```text
case_studies/14_calibration_block/output/
+-- cli/
    +-- run_manifest.json
    +-- tables/results.{csv,json,xlsx}        (2 samples × 2 light sources = 4 rows)
    +-- tables/results_timings.{csv,json,xlsx}
    +-- tables/descriptor_summary.{csv,xlsx}
    +-- tables/ranking_by_light_source__<metric>.{csv,json,xlsx}
    +-- tables/ranking_by_sample__<metric>.{csv,json,xlsx}
    +-- plots/
```

The `run_manifest.json` `parameters.calibration` block records:

```json
{
  "energy_a": 1.0,
  "energy_b": 0.0,
  "oscillator_alpha": 1.0,
  "bands": [{"index": 1, "sigma_ev": 0.25, "reorganization_ev": null}]
}
```

Because `a = 1`, `b = 0`, and `alpha = 1` are all identity values, the
only active effect is the per-band width override: the first excited
state is broadened with `sigma_ev = 0.25` eV instead of the run-level
default. Compare `gaussian_molar_absorptivity_max` between this run and
the default run (without `--calibration`) to see the effect of the width
override on peak height.

---

## 7. Related case studies

- [Case Study 08 — Broadening Sigma](../08_broadening_sigma/README.md)
- [Case Study 13 — Marcus–Hush Width](../13_marcus_hush_width/README.md)
- [Case Study 15 — Vibronic Tabular Branch](../15_vibronic_tabular_branch/README.md)
