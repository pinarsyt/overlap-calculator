from __future__ import annotations

import logging
import re
import time
from pathlib import Path
from typing import cast

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from overlap_calculator.exceptions import OutputError
from overlap_calculator.models import AnalysisSkip, RunResult
from overlap_calculator.plotting.plots import (
    plot_absorptance_absolute,
    plot_absorptance_normalized,
    plot_absorption_overlay,
    plot_light_source_spectrum,
    plot_overlap_absolute,
    plot_overlap_normalized,
    plot_ranking_bars,
)
from overlap_calculator.utils.errors import ErrorCode, format_error
from overlap_calculator.utils.logging import format_log

LOGGER = logging.getLogger(__name__)

_METHODS: tuple[str, str] = ("gaussian", "lorentzian")
_RANKING_METRICS: tuple[str, ...] = (
    "gaussian_absorbed_fraction",
    "lorentzian_absorbed_fraction",
    "gaussian_shape_overlap",
    "lorentzian_shape_overlap",
)
_RANKING_METRIC_BAR_COLORS: dict[str, str] = {
    "gaussian_absorbed_fraction": "#0f766e",
    "lorentzian_absorbed_fraction": "#db2777",
    "gaussian_shape_overlap": "#1d4ed8",
    "lorentzian_shape_overlap": "#b45309",
}


def _ranking_metric_pretty(metric: str, sample_unit: str | None = None) -> str:
    method, _, family = metric.partition("_")
    method_pretty = method.capitalize()
    if family == "absorbed_fraction":
        if sample_unit:
            return f"{method_pretty} absorbed fraction ({sample_unit})"
        return f"{method_pretty} absorbed fraction"
    if family == "shape_overlap":
        return f"{method_pretty} spectral shape overlap"
    return metric


def _safe_plot_stem(value: str) -> str:
    cleaned: list[str] = []
    for char in value:
        if char.isalnum() or char in {"-", "_"}:
            cleaned.append(char)
        else:
            cleaned.append("_")
    return "".join(cleaned)


def _sample_sort_key(sample_id: str) -> tuple[object, ...]:
    parts = re.split(r"(\d+)", sample_id)
    key: list[object] = []
    for part in parts:
        if not part:
            continue
        if part.isdigit():
            key.append((0, int(part)))
        else:
            key.append((1, part.lower()))
    return tuple(key)


def _pair_key(result: RunResult) -> tuple[str, str]:
    return (result.sample_id, result.light_source_name)


def _group_by_method(results: list[RunResult]) -> dict[tuple[str, str], dict[str, RunResult]]:
    grouped: dict[tuple[str, str], dict[str, RunResult]] = {}
    for result in results:
        pair = _pair_key(result)
        grouped.setdefault(pair, {})[result.broadening_method] = result
    return grouped


def _group_absorptance_by_sample(
    results: list[RunResult],
) -> dict[str, dict[str, RunResult]]:
    grouped: dict[str, dict[str, RunResult]] = {}
    for result in results:
        grouped.setdefault(result.sample_id, {}).setdefault(result.broadening_method, result)
    return grouped


def _row_for_pair(
    sample_id: str,
    light_source_name: str,
    by_method: dict[str, RunResult],
) -> dict[str, object]:
    representative = next(iter(by_method.values()))
    row: dict[str, object] = {
        "source_type": representative.source_type,
        "sample_id": sample_id,
        "light_source_name": light_source_name,
        "sigma_ev": representative.sigma_ev,
        "prefactor_mode": representative.prefactor_mode,
        "sigma_mode": representative.sigma_mode,
        "software_version": representative.software_version,
        "absorption_unit": representative.absorption_unit,
        "light_source_unit": representative.light_source_unit,
        "absorbed_flux_unit": representative.absorbed_flux_unit,
        "reference_concentration_molar": representative.reference_concentration_molar,
        "reference_path_cm": representative.reference_path_cm,
        "light_flux_total": representative.light_flux_total,
        "td_method_basis": representative.td.method_basis if representative.td else None,
        "td_solvent": representative.td.solvent if representative.td else None,
    }
    for method in _METHODS:
        result = by_method.get(method)
        if result is None:
            continue
        prefix = method
        row[f"{prefix}_lambda_max_nm"] = result.lambda_max_nm
        row[f"{prefix}_molar_absorptivity_max"] = result.molar_absorptivity_max
        row[f"{prefix}_absorptance_max"] = result.absorptance_max
        row[f"{prefix}_absorbed_flux"] = result.absorbed_flux
        row[f"{prefix}_absorbed_fraction"] = result.absorbed_fraction
        row[f"{prefix}_shape_overlap"] = result.shape_overlap
    if "gaussian" in by_method and "lorentzian" in by_method:
        g = by_method["gaussian"]
        lorentz = by_method["lorentzian"]
        row["delta_absorbed_flux"] = g.absorbed_flux - lorentz.absorbed_flux
        row["delta_absorbed_fraction"] = g.absorbed_fraction - lorentz.absorbed_fraction
        row["delta_shape_overlap"] = g.shape_overlap - lorentz.shape_overlap
        row["abs_delta_absorbed_fraction"] = abs(
            g.absorbed_fraction - lorentz.absorbed_fraction
        )
    return row


def _ranking_pair_records(
    sorted_pairs: list[tuple[str, str]],
    grouped: dict[tuple[str, str], dict[str, RunResult]],
) -> list[dict[str, object]]:
    records: list[dict[str, object]] = []
    for sample_id, light_source_name in sorted_pairs:
        by_method = grouped[(sample_id, light_source_name)]
        representative = next(iter(by_method.values()))
        record: dict[str, object] = {
            "sample_id": sample_id,
            "light_source_name": light_source_name,
            "source_type": representative.source_type,
            "absorption_unit": representative.absorption_unit,
            "light_source_unit": representative.light_source_unit,
        }
        for method in _METHODS:
            result = by_method.get(method)
            if result is None:
                record[f"{method}_absorbed_fraction"] = float("nan")
                record[f"{method}_shape_overlap"] = float("nan")
            else:
                record[f"{method}_absorbed_fraction"] = float(result.absorbed_fraction)
                record[f"{method}_shape_overlap"] = float(result.shape_overlap)
        records.append(record)
    return records


def _ranking_rows_by_light_source(
    pair_records: list[dict[str, object]],
    metric: str,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in pair_records:
        light = str(record["light_source_name"])
        grouped.setdefault(light, []).append(record)
    rows: list[dict[str, object]] = []
    for light in sorted(grouped.keys()):
        bucket = sorted(
            grouped[light],
            key=lambda item: (
                -_safe_metric_value(item, metric)
                if np.isfinite(_safe_metric_value(item, metric))
                else float("inf"),
                _sample_sort_key(str(item["sample_id"])),
            ),
        )
        for rank, record in enumerate(bucket, start=1):
            row = {
                "light_source_name": light,
                "rank": rank,
                "sample_id": record["sample_id"],
                "source_type": record["source_type"],
                "absorption_unit": record["absorption_unit"],
                "light_source_unit": record["light_source_unit"],
            }
            for column in (
                "gaussian_absorbed_fraction",
                "lorentzian_absorbed_fraction",
                "gaussian_shape_overlap",
                "lorentzian_shape_overlap",
            ):
                row[column] = record[column]
            rows.append(row)
    return rows


def _ranking_rows_by_sample(
    pair_records: list[dict[str, object]],
    metric: str,
) -> list[dict[str, object]]:
    grouped: dict[str, list[dict[str, object]]] = {}
    for record in pair_records:
        sample = str(record["sample_id"])
        grouped.setdefault(sample, []).append(record)
    rows: list[dict[str, object]] = []
    for sample in sorted(grouped.keys(), key=_sample_sort_key):
        bucket = sorted(
            grouped[sample],
            key=lambda item: (
                -_safe_metric_value(item, metric)
                if np.isfinite(_safe_metric_value(item, metric))
                else float("inf"),
                str(item["light_source_name"]),
            ),
        )
        for rank, record in enumerate(bucket, start=1):
            row = {
                "sample_id": sample,
                "rank": rank,
                "light_source_name": record["light_source_name"],
                "source_type": record["source_type"],
                "absorption_unit": record["absorption_unit"],
                "light_source_unit": record["light_source_unit"],
            }
            for column in (
                "gaussian_absorbed_fraction",
                "lorentzian_absorbed_fraction",
                "gaussian_shape_overlap",
                "lorentzian_shape_overlap",
            ):
                row[column] = record[column]
            rows.append(row)
    return rows


def _safe_metric_value(record: dict[str, object], metric: str) -> float:
    value = record.get(metric)
    if value is None:
        return float("nan")
    try:
        return float(cast(float, value))
    except (TypeError, ValueError):
        return float("nan")


def _write_table_set(df: pd.DataFrame, tables_dir: Path, stem: str) -> None:
    df.to_csv(tables_dir / f"{stem}.csv", index=False)
    df.to_json(tables_dir / f"{stem}.json", orient="records", indent=2)
    df.to_excel(tables_dir / f"{stem}.xlsx", index=False)


def _export_rankings(
    pair_records: list[dict[str, object]],
    tables_dir: Path,
    plots_dir: Path | None,
    plot_dpi: int,
) -> None:
    if not pair_records:
        return

    representative_unit = next(
        (
            str(record["absorption_unit"])
            for record in pair_records
            if record.get("absorption_unit")
        ),
        None,
    )

    for metric in _RANKING_METRICS:
        rows_by_light = _ranking_rows_by_light_source(pair_records, metric)
        rows_by_sample = _ranking_rows_by_sample(pair_records, metric)
        if rows_by_light:
            df_light = pd.DataFrame(rows_by_light)
            _write_table_set(
                df_light,
                tables_dir,
                f"ranking_by_light_source__{metric}",
            )
        if rows_by_sample:
            df_sample = pd.DataFrame(rows_by_sample)
            _write_table_set(
                df_sample,
                tables_dir,
                f"ranking_by_sample__{metric}",
            )

        if plots_dir is None:
            continue

        bar_color = _RANKING_METRIC_BAR_COLORS.get(metric, "#0f766e")
        y_label = _ranking_metric_pretty(metric, sample_unit=representative_unit)
        ranking_root = plots_dir / "ranking"
        light_dir = ranking_root / "by_light_source" / metric
        sample_dir = ranking_root / "by_sample" / metric
        light_dir.mkdir(parents=True, exist_ok=True)
        sample_dir.mkdir(parents=True, exist_ok=True)

        light_buckets: dict[str, list[dict[str, object]]] = {}
        for row in rows_by_light:
            light_buckets.setdefault(str(row["light_source_name"]), []).append(row)
        for light_name, bucket in light_buckets.items():
            labels = [str(row["sample_id"]) for row in bucket]
            values = [_safe_metric_value(row, metric) for row in bucket]
            stem = _safe_plot_stem(light_name)
            plot_ranking_bars(
                labels=labels,
                values=values,
                out_path=light_dir / f"{stem}.tiff",
                dpi=plot_dpi,
                title=(
                    f"Sample ranking under {light_name} — "
                    f"{_ranking_metric_pretty(metric)}"
                ),
                y_label=y_label,
                x_label="Sample",
                bar_color=bar_color,
            )

        sample_buckets: dict[str, list[dict[str, object]]] = {}
        for row in rows_by_sample:
            sample_buckets.setdefault(str(row["sample_id"]), []).append(row)
        for sample_id, bucket in sample_buckets.items():
            labels = [str(row["light_source_name"]) for row in bucket]
            values = [_safe_metric_value(row, metric) for row in bucket]
            stem = _safe_plot_stem(sample_id)
            plot_ranking_bars(
                labels=labels,
                values=values,
                out_path=sample_dir / f"{stem}.tiff",
                dpi=plot_dpi,
                title=(
                    f"Light-source ranking for {sample_id} — "
                    f"{_ranking_metric_pretty(metric)}"
                ),
                y_label=y_label,
                x_label="Light source",
                bar_color=bar_color,
            )


def _timing_rows_wide(
    results: list[RunResult],
    plot_ms_by_pair: dict[tuple[str, str], float],
) -> list[dict[str, object]]:
    grouped = _group_by_method(results)
    rows: list[dict[str, object]] = []
    for (sample_id, light_source_name), by_method in grouped.items():
        pair_plot_ms = plot_ms_by_pair.get((sample_id, light_source_name), 0.0)
        representative = next(iter(by_method.values()))
        row: dict[str, object] = {
            "source_type": representative.source_type,
            "sample_id": sample_id,
            "light_source_name": light_source_name,
            "plot_ms": pair_plot_ms,
        }
        total_pair_ms = 0.0
        for method in _METHODS:
            result = by_method.get(method)
            if result is None:
                continue
            total_sample_ms = float(result.timings_ms.get("total_sample_ms", 0.0) or 0.0)
            row[f"{method}_parse_tddft_ms"] = result.timings_ms.get("parse_tddft_ms")
            row[f"{method}_broadening_ms"] = result.timings_ms.get("broadening_ms")
            row[f"{method}_light_source_ms"] = result.timings_ms.get("light_source_ms")
            row[f"{method}_integrals_ms"] = result.timings_ms.get("integrals_ms")
            row[f"{method}_total_sample_ms"] = total_sample_ms
            total_pair_ms += total_sample_ms
        row["total_pair_ms"] = total_pair_ms
        row["total_with_plot_ms"] = total_pair_ms + pair_plot_ms
        rows.append(row)
    return rows


def export_results(
    results: list[RunResult],
    out_dir: Path,
    make_plots: bool = True,
    skipped_items: list[AnalysisSkip] | None = None,
    plot_dpi: int = 400,
    make_rankings: bool = True,
) -> None:
    if not results:
        raise OutputError(format_error(ErrorCode.OUTPUT, "No results available for export."))

    tables_dir = out_dir / "tables"
    plots_dir = out_dir / "plots"
    try:
        tables_dir.mkdir(parents=True, exist_ok=True)
        if make_plots:
            plots_dir.mkdir(parents=True, exist_ok=True)
    except OSError as exc:
        raise OutputError(
            format_error(ErrorCode.OUTPUT, f"Failed to create output directory: {out_dir}")
        ) from exc

    grouped = _group_by_method(results)
    sorted_pairs = sorted(
        grouped.keys(),
        key=lambda pair: (_sample_sort_key(pair[0]), pair[1]),
    )
    rows: list[dict[str, object]] = [
        _row_for_pair(sample_id, light_source_name, grouped[(sample_id, light_source_name)])
        for (sample_id, light_source_name) in sorted_pairs
    ]

    try:
        LOGGER.info(format_log("export", "results", out_dir=tables_dir, rows=len(rows)))
        results_df = pd.DataFrame(rows)

        plot_ms_by_pair: dict[tuple[str, str], float] = {}
        total_plots_ms = 0.0
        if make_plots:
            plot_ms_by_pair, total_plots_ms = _export_plots(results, plots_dir, plot_dpi=plot_dpi)
            LOGGER.info(
                format_log(
                    "export",
                    "plots_timings",
                    out_dir=plots_dir,
                    total_plots_ms=round(total_plots_ms, 3),
                )
            )

        timing_rows = _timing_rows_wide(results, plot_ms_by_pair)
        timings_df = pd.DataFrame(timing_rows)

        results_df.to_csv(tables_dir / "results.csv", index=False)
        results_df.to_json(tables_dir / "results.json", orient="records", indent=2)
        results_df.to_excel(tables_dir / "results.xlsx", index=False)
        timings_df.to_csv(tables_dir / "results_timings.csv", index=False)
        timings_df.to_json(tables_dir / "results_timings.json", orient="records", indent=2)
        timings_df.to_excel(tables_dir / "results_timings.xlsx", index=False)

        sort_columns = [
            column
            for column in (
                "gaussian_absorbed_fraction",
                "lorentzian_absorbed_fraction",
                "gaussian_absorbed_flux",
            )
            if column in results_df.columns
        ]
        summary_df = (
            results_df.sort_values(by=sort_columns, ascending=[False] * len(sort_columns))
            if sort_columns
            else results_df.copy()
        ).reset_index(drop=True)
        summary_df.insert(0, "rank", range(1, len(summary_df) + 1))
        summary_df.to_csv(tables_dir / "descriptor_summary.csv", index=False)
        summary_df.to_excel(tables_dir / "descriptor_summary.xlsx", index=False)

        if make_rankings:
            pair_records = _ranking_pair_records(sorted_pairs, grouped)
            ranking_plots_dir = plots_dir if make_plots else None
            _export_rankings(
                pair_records,
                tables_dir=tables_dir,
                plots_dir=ranking_plots_dir,
                plot_dpi=plot_dpi,
            )
            LOGGER.info(
                format_log(
                    "export",
                    "rankings",
                    out_dir=tables_dir,
                    metrics=",".join(_RANKING_METRICS),
                    plots="enabled" if ranking_plots_dir is not None else "disabled",
                )
            )

        if skipped_items:
            skipped_rows = [
                {"sample_id": item.sample_id, "reason": item.reason}
                for item in skipped_items
            ]
            skipped_df = pd.DataFrame(skipped_rows)
            skipped_df.to_csv(tables_dir / "skipped_inputs.csv", index=False)
            skipped_df.to_json(tables_dir / "skipped_inputs.json", orient="records", indent=2)
            LOGGER.warning(
                format_log(
                    "export",
                    "skipped_inputs",
                    count=len(skipped_items),
                    out_dir=tables_dir,
                )
            )

    except Exception as exc:
        raise OutputError(
            format_error(
                ErrorCode.OUTPUT,
                f"Failed to export results: {type(exc).__name__}: {exc}",
            )
        ) from exc


def _export_plots(
    results: list[RunResult],
    plots_dir: Path,
    plot_dpi: int,
) -> tuple[dict[tuple[str, str], float], float]:
    absorption_dir = plots_dir / "absorption"
    light_source_dir = plots_dir / "light_source"
    overlap_dir = plots_dir / "overlap"
    overlay_dir = plots_dir / "overlays"
    for directory in (absorption_dir, light_source_dir, overlap_dir, overlay_dir):
        directory.mkdir(parents=True, exist_ok=True)

    plot_ms_by_pair: dict[tuple[str, str], float] = {}
    total_plots_ms = 0.0

    sample_groups = _group_absorptance_by_sample(results)
    sorted_sample_ids = sorted(sample_groups.keys(), key=_sample_sort_key)
    for sample_id in sorted_sample_ids:
        method_curves: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
        for method in _METHODS:
            result = sample_groups[sample_id].get(method)
            if result is None:
                continue
            method_curves[method] = (
                np.array(result.wavelengths_nm, dtype=np.float64),
                np.array(result.absorptance, dtype=np.float64),
            )
        if not method_curves:
            continue
        stem = _safe_plot_stem(sample_id)
        started = time.perf_counter()
        plot_absorptance_absolute(
            method_curves,
            absorption_dir / f"{stem}__absolute.tiff",
            dpi=plot_dpi,
            title=f"Absorptance (absolute) - {sample_id}",
        )
        plot_absorptance_normalized(
            method_curves,
            absorption_dir / f"{stem}__normalized.tiff",
            dpi=plot_dpi,
            title=f"Absorptance (normalized) - {sample_id}",
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        total_plots_ms += elapsed_ms

    light_by_name: dict[str, RunResult] = {}
    for item in results:
        light_by_name.setdefault(item.light_source_name, item)
    for light_name, item in light_by_name.items():
        wavelengths = np.array(item.wavelengths_nm, dtype=np.float64)
        intensity = np.array(item.light_intensity, dtype=np.float64)
        started = time.perf_counter()
        plot_light_source_spectrum(
            wavelengths,
            intensity,
            light_source_dir / f"{_safe_plot_stem(light_name)}.tiff",
            dpi=plot_dpi,
            title=f"Light Source - {light_name}",
        )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        total_plots_ms += elapsed_ms

    pair_groups = _group_by_method(results)
    for (sample_id, light_source_name), by_method in pair_groups.items():
        representative = next(iter(by_method.values()))
        light_wavelengths = np.array(representative.wavelengths_nm, dtype=np.float64)
        light_intensity = np.array(representative.light_intensity, dtype=np.float64)
        method_absorptance: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
        for method in _METHODS:
            result = by_method.get(method)
            if result is None:
                continue
            method_absorptance[method] = (
                np.array(result.wavelengths_nm, dtype=np.float64),
                np.array(result.absorptance, dtype=np.float64),
            )
        if not method_absorptance:
            continue
        stem = f"{_safe_plot_stem(sample_id)}__{_safe_plot_stem(light_source_name)}"
        started = time.perf_counter()
        plot_overlap_absolute(
            method_absorptance,
            light_wavelengths,
            light_intensity,
            light_unit=representative.light_source_unit,
            out_path=overlap_dir / f"{stem}__combined__absolute.tiff",
            dpi=plot_dpi,
            title=f"Overlap (combined, absolute) - {sample_id} vs {light_source_name}",
        )
        plot_overlap_normalized(
            method_absorptance,
            light_wavelengths,
            light_intensity,
            overlap_dir / f"{stem}__combined__normalized.tiff",
            dpi=plot_dpi,
            title=f"Overlap (combined, normalized) - {sample_id} vs {light_source_name}",
        )
        for method, curve in method_absorptance.items():
            single = {method: curve}
            plot_overlap_absolute(
                single,
                light_wavelengths,
                light_intensity,
                light_unit=representative.light_source_unit,
                out_path=overlap_dir / f"{stem}__{method}__absolute.tiff",
                dpi=plot_dpi,
                title=f"Overlap ({method}, absolute) - {sample_id} vs {light_source_name}",
            )
            plot_overlap_normalized(
                single,
                light_wavelengths,
                light_intensity,
                overlap_dir / f"{stem}__{method}__normalized.tiff",
                dpi=plot_dpi,
                title=f"Overlap ({method}, normalized) - {sample_id} vs {light_source_name}",
            )
        elapsed_ms = (time.perf_counter() - started) * 1000.0
        total_plots_ms += elapsed_ms
        plot_ms_by_pair[(sample_id, light_source_name)] = (
            plot_ms_by_pair.get((sample_id, light_source_name), 0.0) + elapsed_ms
        )

    for method in _METHODS:
        spectra: list[tuple[str, NDArray[np.float64], NDArray[np.float64]]] = []
        for sample_id in sorted_sample_ids:
            result = sample_groups[sample_id].get(method)
            if result is None:
                continue
            spectra.append(
                (
                    sample_id,
                    np.array(result.wavelengths_nm, dtype=np.float64),
                    np.array(result.absorptance, dtype=np.float64),
                )
            )
        if len(spectra) > 1:
            spectra_normalized = []
            for sample_id, wavelengths, absorptance in spectra:
                peak = max(float(np.max(absorptance)), 1e-12)
                spectra_normalized.append((sample_id, wavelengths, absorptance / peak))
            started = time.perf_counter()
            plot_absorption_overlay(
                spectra,
                overlay_dir / f"absorptance_overlay__{method}__absolute.tiff",
                dpi=plot_dpi,
                title=f"Absorptance Overlay — absolute ({method})",
                y_label="Absorptance α(λ)",
            )
            plot_absorption_overlay(
                spectra_normalized,
                overlay_dir / f"absorptance_overlay__{method}__normalized.tiff",
                dpi=plot_dpi,
                title=f"Absorptance Overlay — normalized ({method})",
                y_label="α(λ) / max(α)",
            )
            elapsed_ms = (time.perf_counter() - started) * 1000.0
            total_plots_ms += elapsed_ms

    return plot_ms_by_pair, total_plots_ms


def prepare_output_dir(out_dir: Path, clean: bool) -> None:
    if not clean:
        LOGGER.info(format_log("cleanup", "output_dir_skipped", out_dir=out_dir))
        return
    if not out_dir.exists():
        LOGGER.info(format_log("cleanup", "output_dir_missing", out_dir=out_dir))
        return
    try:
        for file_path in out_dir.rglob("*"):
            if file_path.is_file():
                file_path.unlink()
        LOGGER.info(format_log("cleanup", "output_dir", out_dir=out_dir))
    except OSError as exc:
        raise OutputError(
            format_error(ErrorCode.OUTPUT, f"Failed to clean output directory: {out_dir}")
        ) from exc
