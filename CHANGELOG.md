# Changelog

All notable changes to this project will be documented in this file.

The format is based on Keep a Changelog, and this project adheres to
Semantic Versioning.

## 1.1.1 - 2026-06-07

### Fixed

- **Run manifest provenance.** `run_manifest.json` now records each input
  series / sheet as a distinct entry. A single Excel/CSV file feeding
  multiple series previously collapsed to one manifest entry; the
  deduplication now keys on the full linkage tuple (source path, sample
  id, series name, sheet name). Each file is still hashed once.

## 1.1.0 - 2026-06-05

### Added

- **Frequency-resolved prefactor mode.** The new `--prefactor-mode
  frequency-resolved` flag (CLI) / `prefactor_mode` parameter (library)
  keeps the wavenumber factor inside the integrand,
  `ε(ν) = Σ P fᵢ (ν/νᵢ) gᵢ(ν − νᵢ)`, rather than using the default
  integrated-intensity convention. The two modes differ in peak height and
  position by O((σ/νᵢ)²), below ~2 % over 200–800 nm, and grow into the
  NIR. Use `constant` (default) for the validated visible range; use
  `frequency-resolved` for NIR bands.

- **Marcus–Hush broadening width.** The new `--sigma-mode marcus-hush`
  flag pairs with `--reorganization-ev FLOAT` and `--temperature-k FLOAT`
  to derive a classical high-temperature Marcus–Hush Gaussian width
  `σ = sqrt(2·λ·k_B·T)` per transition. At λ = 0.30 eV, T = 298.15 K this
  yields σ = 0.12416 eV (FWHM 0.29234 eV). This is the classical
  high-temperature limit; for organic vibrational baths where
  ℏω >> k_B·T it is a first-order estimate.

- **Calibration block.** A TOML file supplied via `--calibration PATH`
  (CLI and library) applies a linear energy map `E_cal = a·E + b`,
  an oscillator-strength scaling `f_cal = α·f`, and optional per-band
  sigma / reorganization-energy overrides before broadening. Wavelength
  is recomputed from the calibrated energy via `λ = 1239.841984 / E_cal`
  only when the energy map is non-identity. The identity calibration
  (a=1, b=0, α=1, no band overrides) produces bit-identical output to
  running without `--calibration`.

- **Public Python API.** `overlap_calculator/__init__.py` now exports a
  stable, typed public surface: `analyze`, `analyze_inputs`,
  `export_results`, `prepare_output_dir`, `build_extinction_spectrum`,
  `compute_absorbance`, `compute_absorptance`, `shape_overlap`,
  `integrate_light_flux`, `integrate_absorbed_flux`, `load_light_sources`,
  `marcus_hush_sigma_ev`, `Calibration`, `load_calibration`,
  `apply_calibration`, `build_run_manifest`, `write_run_manifest`,
  `__version__`.

- **Run manifest provenance.** Every `analyze` run writes
  `run_manifest.json` in the output root (alongside `tables/` and
  `plots/`). Fields: `software_version`, `git_commit` (null when
  unavailable), `generated_at_utc` (ISO-8601 UTC), `parameters` (the
  full resolved runtime parameter set including the calibration block),
  `light_sources`, `inputs` (one entry per source file with `sample_id`,
  `input_type`, `source_path`, `series_name`, `sheet_name`, and SHA-256
  of the file), `results_count`, `skipped_count`. Result table rows now
  also carry `prefactor_mode`, `sigma_mode`, and `software_version`
  columns.

- **Four new case studies** (12–15) in `case_studies/`: frequency-resolved
  prefactor, Marcus–Hush width, calibration block, and vibronic/tabular
  input branch.

---

## 1.0.0 - 2026-05-01

Initial public release of `overlap-calculator`, a reproducible batch
toolkit for quantifying the spectral overlap between molecular
absorption spectra and reference light sources.

### Added

- **Dual-input pipeline.** Theoretical (Gaussian TD-DFT `.out`/`.log`)
  and experimental (CSV, XLSX, XLS) spectra are treated as equal
  first-class inputs and can be mixed freely in the same run.
  Multi-sheet Excel workbooks are supported via the `sheet_name`
  field of the manifest, and via the `sheet_overrides` form field on
  the HTTP API.
- **Broadening comparison.** Every TD-DFT spectrum is reconstructed
  with both **Gaussian** and **Lorentzian** line shapes in a single
  pass, emitting `gaussian_*`, `lorentzian_*`, and `delta_*` columns
  side by side.
- **Overlap metrics.** Per `(sample, light_source)` pair, the
  pipeline reports `absorbed_flux`, `absorbed_fraction`, and
  `shape_overlap`, each with explicit unit metadata
  (`absorption_unit`, `light_source_unit`, `absorbed_flux_unit`).
- **Bundled reference light sources.**
  - `AM15G` — NREL ASTM G-173 AM1.5G global reference solar spectrum.
  - `LEDB1`, `LEDB2`, `LEDB3`, `LEDB4` — CIE 015:2018 reference LED illuminants.
  - `CIEFL10` — CIE 015:2018 reference fluorescent illuminant FL10.
- **Custom light sources.** Arbitrary two-column CSV spectra are
  accepted via `--light-source-file` (CLI) or `light_source_files`
  (HTTP).
- **Sample identity.** `sample_id` is derived from the Gaussian
  `%chk=<name>.chk` directive for TD-DFT inputs (falling back to the
  file stem), and from `<series_name>` for experimental inputs (the
  series column name itself), keeping labels meaningful even for
  queue-system artefacts such as `slurm-5473089.out`.
- **CLI (Typer).** Three subcommands: `generate-input`, `analyze`,
  `version`. Full control over broadening σ, wavelength grid,
  Beer–Lambert reference `c`/`L`, default light-source set, and plot
  emission.
- **HTTP API (Flask).** `GET /health` liveness probe and
  `POST /analyze` multipart endpoint returning a ZIP of all results.
  Per-request sigma, grid, Beer–Lambert, light-source, and
  `sheet_overrides` overrides are all form-controllable.
- **Exports.** Per-sample `results.{csv,json,xlsx}`, per-sample
  timings, a curated `descriptor_summary.{csv,xlsx}`, and
  `skipped_inputs.{csv,json}` whenever any input is rejected.
- **Ranking outputs.** Two grouped ranking tables — one ordering
  every sample under each light source, the other ordering every
  light source for each sample — are emitted in CSV / JSON / XLSX
  for all four overlap metrics (`gaussian_absorbed_fraction`,
  `lorentzian_absorbed_fraction`, `gaussian_shape_overlap`,
  `lorentzian_shape_overlap`) so users can choose between the
  Beer–Lambert "absorbed-fraction" interpretation and the
  intensity-independent "shape-overlap" interpretation without
  re-running the pipeline. Each metric also produces TIFF bar charts
  under `plots/ranking/by_light_source/<metric>/` and
  `plots/ranking/by_sample/<metric>/`. Toggleable via
  `--ranking-outputs / --no-ranking-outputs` on the CLI and the
  `ranking_outputs` form field on the API; default on.
- **Plots.** 600 dpi TIFFs in grouped folders (`absorption/`,
  `light_source/`, `overlap/`, `overlays/`, `ranking/`), including
  both absolute and max-normalised variants and combined
  Gaussian+Lorentzian panels with the geometric overlap area
  `min(α, Î)` shaded — visually identical to the integrand of the
  reported `shape_overlap` metric `∫ min(α̂, Î) dλ / ∫ Î dλ`.
- **Configuration.** `pydantic-settings` with the `GAUSS_` prefix;
  a local `.env` is honoured. Documented in
  [docs/MANUAL.md §10](docs/MANUAL.md#10-configuration-and-environment-variables).
- **Packaging and deployment.** `pyproject.toml`-based installable
  package, reproducible `environment.yml`, `Dockerfile` (non-root
  runtime user, port 8000), and `docker-compose.yml` (host port
  8080 → container 8000, `/health` healthcheck, environment
  scaffolding).
- **Tests.** pytest suite covering the TD-DFT parser, input
  generation (with multi-sheet Excel fixtures), light-source loader,
  spectrum/metric math, analyzer batch-skip behaviour, export, CLI
  wiring, and API form-field parsing.
- **Continuous integration.** GitHub Actions workflow running
  `ruff`, `mypy --strict`, and `pytest` on every push and pull
  request, with a `CHANGELOG.md` touch-check on PRs. A separate
  release workflow builds distribution artefacts and drafts a
  GitHub Release on version tags.
- **Documentation.** User manual in Markdown, LaTeX, and PDF
  (`docs/MANUAL.{md,tex,pdf}`), HTML quickstart (`docs/index.html`),
  a Postman collection with distinct Local and Docker-Compose
  request sections, and three reproducible worked examples under
  `case_studies/`.
- **License.** Released under the **GNU General Public License v3.0
  or later** (see [LICENSE](LICENSE)).

### Third-party data

Bundled CIE LED (`LEDB1`, `LEDB2`, `LEDB3`, `LEDB4`) and fluorescent
(`CIEFL10`) illuminants are derived from *CIE 015:2018 Colorimetry,
4th Edition* (International Commission on Illumination; see
[README.md](README.md#acknowledgement-of-third-party-data) for full
citations). The `AM15G` spectrum is the ASTM G-173-03 AM1.5 global
reference distributed by the U.S. National Renewable Energy
Laboratory (NREL).
