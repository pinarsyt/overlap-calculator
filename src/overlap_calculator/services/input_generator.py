from __future__ import annotations

import json
import logging
import re
from collections.abc import Mapping
from pathlib import Path

import pandas as pd

from overlap_calculator.exceptions import InputError
from overlap_calculator.models import AnalysisInput, AnalysisSkip
from overlap_calculator.parsers.experimental import list_experimental_series
from overlap_calculator.parsers.td import extract_chk_name
from overlap_calculator.utils.errors import ErrorCode, format_error
from overlap_calculator.utils.logging import format_log

LOGGER = logging.getLogger(__name__)
_ROUTE_TD = re.compile(r"(?i)#\s*.*\btd\b")


def _is_tddft_output(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if _ROUTE_TD.search(line):
                    return True
                if "Excited State" in line:
                    return True
    except OSError as exc:
        raise InputError(format_error(ErrorCode.INPUT, f"Failed to read file: {path}")) from exc
    return False


def _relativize(path: Path, base_dir: Path) -> str:
    try:
        return path.relative_to(base_dir).as_posix()
    except ValueError:
        return path.as_posix()


def _build_scan_skip(path: Path, reason: str) -> AnalysisSkip:
    return AnalysisSkip(sample_id=path.stem, td_path=str(path), reason=reason)


def _experimental_sheet_candidates(path: Path, sheet_override: str | None) -> list[str | None]:
    if sheet_override is not None or path.suffix.lower() not in {".xlsx", ".xls"}:
        return [sheet_override]

    try:
        sheet_names = pd.ExcelFile(path).sheet_names
    except (OSError, ValueError) as exc:
        raise InputError(
            format_error(ErrorCode.INPUT, f"Failed to read experimental file: {path}")
        ) from exc
    if not sheet_names:
        return [None]
    return [None, *sheet_names[1:]]


def generate_inputs_with_skips(
    files_dir: Path,
    sheet_overrides: Mapping[Path, str] | None = None,
) -> tuple[list[AnalysisInput], list[AnalysisSkip]]:
    if not files_dir.exists():
        raise InputError(format_error(ErrorCode.INPUT, f"Files directory not found: {files_dir}"))

    theoretical_files = sorted([path for path in files_dir.rglob("*.out") if path.is_file()])
    experimental_files = sorted(
        [
            path
            for path in files_dir.rglob("*")
            if path.is_file() and path.suffix.lower() in {".csv", ".xlsx", ".xls"}
        ]
    )
    files = theoretical_files + experimental_files
    if not files:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                f"No supported files found under: {files_dir}. "
                "Allowed: .out, .csv, .xlsx, .xls",
            )
        )

    td_files: list[AnalysisInput] = []
    skipped_inputs: list[AnalysisSkip] = []
    for path in theoretical_files:
        if _is_tddft_output(path):
            td_files.append(
                AnalysisInput(
                    input_type="theoretical",
                    source_path=str(path),
                    sample_id=extract_chk_name(path) or path.stem,
                )
            )
        else:
            skipped_inputs.append(
                _build_scan_skip(path, "INPUT_SKIPPED: file is not a TD-DFT output (likely OPT).")
            )

    experimental_inputs: list[AnalysisInput] = []
    for path in experimental_files:
        sheet_override = sheet_overrides.get(path) if sheet_overrides else None
        selected_sheet = sheet_override
        try:
            series_names: list[str] = []
            last_error: InputError | None = None
            for sheet_candidate in _experimental_sheet_candidates(path, sheet_override):
                try:
                    series_names = list_experimental_series(path, sheet_name=sheet_candidate)
                except InputError as exc:
                    last_error = exc
                    if sheet_override is not None:
                        raise
                    continue
                selected_sheet = sheet_candidate
                break
            if not series_names and last_error is not None:
                raise last_error
        except InputError as exc:
            skipped_inputs.append(
                _build_scan_skip(path, f"INPUT_SKIPPED: failed to read experimental file ({exc})")
            )
            continue
        if not series_names:
            skipped_inputs.append(
                _build_scan_skip(path, "INPUT_SKIPPED: experimental file has no numeric series.")
            )
            continue
        for series_name in series_names:
            sample_id = series_name
            experimental_inputs.append(
                AnalysisInput(
                    input_type="experimental",
                    source_path=str(path),
                    sample_id=sample_id,
                    series_name=series_name,
                    sheet_name=selected_sheet,
                )
            )

    selected_inputs = td_files + experimental_inputs
    if not selected_inputs:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                f"No analyzable TD-DFT/experimental files found under: {files_dir}",
            )
        )

    log_message = format_log(
        "scan",
        "inputs",
        total=len(files),
        theoretical=len(td_files),
        experimental_series=len(experimental_inputs),
        selected=len(selected_inputs),
        skipped=len(skipped_inputs),
        root=files_dir,
    )
    if skipped_inputs:
        LOGGER.warning(log_message)
    else:
        LOGGER.info(log_message)
    return selected_inputs, skipped_inputs


def generate_inputs(files_dir: Path) -> list[AnalysisInput]:
    inputs, _skipped = generate_inputs_with_skips(files_dir)
    return inputs


def generate_input_json(files_dir: Path, out_path: Path) -> list[AnalysisInput]:
    items, skipped_inputs = generate_inputs_with_skips(files_dir)

    out_dir = out_path.parent
    out_dir.mkdir(parents=True, exist_ok=True)

    payload = [
        {
            "input_type": item.input_type,
            "sample_id": item.sample_id,
            "source_path": _relativize(Path(item.source_path), out_dir),
            "series_name": item.series_name,
            "sheet_name": item.sheet_name,
        }
        for item in items
    ]
    out_path.write_text(json.dumps(payload, indent=2), encoding="utf-8")

    LOGGER.info(format_log("write", "input_json", path=out_path, items=len(items)))

    skipped_path = out_path.with_name("skipped_inputs.json")
    if skipped_inputs:
        skipped_payload = [
            {
                "sample_id": skip.sample_id,
                "source_path": _relativize(Path(skip.td_path), out_dir),
                "reason": skip.reason,
            }
            for skip in skipped_inputs
        ]
        skipped_path.write_text(json.dumps(skipped_payload, indent=2), encoding="utf-8")
        LOGGER.warning(
            format_log(
                "write",
                "input_json_skipped",
                path=skipped_path,
                skipped=len(skipped_inputs),
            )
        )
    elif skipped_path.exists():
        skipped_path.unlink()
    return items
