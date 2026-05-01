from __future__ import annotations

from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from overlap_calculator.exceptions import InputError
from overlap_calculator.utils.errors import ErrorCode, format_error

_WL_ALIASES = ("wavelength", "wavelength_nm", "lambda", "wl", "nm")


def _normalize_col(name: str) -> str:
    return name.strip().lower().replace(" ", "_")


def _read_table(path: Path, sheet_name: str | None = None) -> pd.DataFrame:
    suffix = path.suffix.lower()
    try:
        if suffix in {".xlsx", ".xls"}:
            effective_sheet: str | int = sheet_name if sheet_name is not None else 0
            return pd.read_excel(path, sheet_name=effective_sheet)
        if suffix == ".csv":
            return pd.read_csv(path)
    except (OSError, ValueError) as exc:
        raise InputError(
            format_error(ErrorCode.INPUT, f"Failed to read experimental file: {path}")
        ) from exc
    raise InputError(
        format_error(
            ErrorCode.INPUT,
            f"Unsupported experimental extension: {suffix}. Allowed: .csv, .xlsx, .xls",
        )
    )


def _find_wavelength_column(frame: pd.DataFrame) -> str:
    for column in frame.columns:
        normalized = _normalize_col(str(column))
        if normalized in _WL_ALIASES:
            return str(column)
    first_col = str(frame.columns[0])
    values = pd.to_numeric(frame[first_col], errors="coerce").dropna()
    if values.size > 0:
        return first_col
    raise InputError(
        format_error(
            ErrorCode.INPUT,
            "Experimental data must include a wavelength column (e.g. wavelength, wavelength_nm).",
        )
    )


def _prepare_series(
    frame: pd.DataFrame,
    wavelength_col: str,
    series_col: str,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    wavelengths = pd.to_numeric(frame[wavelength_col], errors="coerce")
    values = pd.to_numeric(frame[series_col], errors="coerce")
    valid = wavelengths.notna() & values.notna()
    wl = wavelengths[valid].to_numpy(dtype=np.float64)
    yy = values[valid].to_numpy(dtype=np.float64)
    if wl.size < 10:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                f"Experimental series '{series_col}' has insufficient numeric rows.",
            )
        )
    if np.any(wl <= 0):
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                f"Experimental series '{series_col}' has non-positive wavelengths.",
            )
        )
    if np.any(yy < 0):
        yy = np.clip(yy, a_min=0.0, a_max=None)
    order = np.argsort(wl)
    return wl[order], yy[order]


def load_experimental_series(
    path: Path,
    series_name: str | None = None,
    sheet_name: str | None = None,
) -> tuple[str, NDArray[np.float64], NDArray[np.float64]]:
    frame = _read_table(path, sheet_name=sheet_name)
    if frame.empty:
        raise InputError(format_error(ErrorCode.INPUT, f"Experimental file is empty: {path}"))
    wavelength_col = _find_wavelength_column(frame)
    candidate_cols = [
        str(col)
        for col in frame.columns
        if str(col) != wavelength_col and pd.to_numeric(frame[col], errors="coerce").notna().any()
    ]
    if not candidate_cols:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                f"Experimental file has no numeric intensity/absorbance columns: {path}",
            )
        )
    selected = series_name or candidate_cols[0]
    if selected not in frame.columns:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                f"Series '{selected}' not found in experimental file: {path}",
            )
        )
    wl, yy = _prepare_series(frame, wavelength_col, selected)
    return selected, wl, yy


def list_experimental_series(path: Path, sheet_name: str | None = None) -> list[str]:
    frame = _read_table(path, sheet_name=sheet_name)
    if frame.empty:
        return []
    wavelength_col = _find_wavelength_column(frame)
    names: list[str] = []
    for column in frame.columns:
        name = str(column)
        if name == wavelength_col:
            continue
        numeric = pd.to_numeric(frame[name], errors="coerce")
        if numeric.notna().any():
            names.append(name)
    return names
