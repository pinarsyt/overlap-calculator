from __future__ import annotations

import math
from pathlib import Path

import numpy as np
import pandas as pd
from numpy.typing import NDArray

from overlap_calculator.exceptions import InputError
from overlap_calculator.models import ExcitedState
from overlap_calculator.utils.errors import ErrorCode, format_error

VALID_BROADENING_METHODS = {"gaussian", "lorentzian"}
BUILTIN_LIGHT_SOURCES: dict[str, str] = {
    "AM15G": "light_source_am15g.csv",
}
LED_MASTER_FILE = "CIE_illum_LEDs_1nm.csv"
LED_COLUMN_INDEX: dict[str, int] = {
    "LEDB1": 1,
    "LEDB2": 2,
    "LEDB3": 3,
    "LEDB4": 4,
}
FL_MASTER_FILE = "CIE_illum_FLs_1nm.csv"
FL_COLUMN_INDEX: dict[str, int] = {
    "CIEFL10": 10,
}
LIGHT_SOURCE_UNITS: dict[str, str] = {
    "AM15G": "W m^-2 nm^-1",
    "LEDB1": "relative",
    "LEDB2": "relative",
    "LEDB3": "relative",
    "LEDB4": "relative",
    "CIEFL10": "relative",
}

EV_PER_CM1 = 1.0 / 8065.544
CM1_PER_EV = 8065.544
EPSILON_PREFACTOR_M_1_CM_2 = 2.315e8
REFERENCE_CONCENTRATION_MOLAR = 1.0e-5
REFERENCE_PATH_CM = 1.0
GAUSSIAN_STD_TO_HWHM = math.sqrt(2.0 * math.log(2.0))


def ev_to_cm1(ev: float) -> float:
    return ev * CM1_PER_EV


def nm_to_cm1(nm: NDArray[np.float64]) -> NDArray[np.float64]:
    return 1.0e7 / nm


def validate_broadening_method(method: str) -> str:
    normalized = method.strip().lower()
    if normalized not in VALID_BROADENING_METHODS:
        allowed = ", ".join(sorted(VALID_BROADENING_METHODS))
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                f"Invalid broadening method: {method}. Allowed: {allowed}",
            )
        )
    return normalized


def validate_sigma_ev(sigma_ev: float) -> float:
    if sigma_ev <= 0:
        raise InputError(format_error(ErrorCode.INPUT, "sigma_ev must be > 0."))
    return sigma_ev


def validate_wavelength_grid(
    wavelength_min_nm: float,
    wavelength_max_nm: float,
    num_points: int,
) -> tuple[float, float, int]:
    if wavelength_min_nm <= 0 or wavelength_max_nm <= 0:
        raise InputError(format_error(ErrorCode.INPUT, "Wavelength bounds must be > 0."))
    if wavelength_min_nm >= wavelength_max_nm:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                "wavelength_min_nm must be smaller than wavelength_max_nm.",
            )
        )
    if num_points < 50:
        raise InputError(format_error(ErrorCode.INPUT, "num_points must be >= 50."))
    return wavelength_min_nm, wavelength_max_nm, num_points


def build_extinction_spectrum(
    excited_states: list[ExcitedState],
    method: str,
    sigma_ev: float,
    wavelength_min_nm: float,
    wavelength_max_nm: float,
    num_points: int,
) -> tuple[NDArray[np.float64], NDArray[np.float64]]:
    method = validate_broadening_method(method)
    sigma_ev = validate_sigma_ev(sigma_ev)
    wl_min, wl_max, points = validate_wavelength_grid(
        wavelength_min_nm, wavelength_max_nm, num_points
    )
    wavelengths_nm = np.linspace(wl_min, wl_max, points, dtype=np.float64)
    nu_grid_cm1 = nm_to_cm1(wavelengths_nm)
    sigma_cm1 = ev_to_cm1(sigma_ev)

    epsilon = np.zeros_like(wavelengths_nm)
    for state in excited_states:
        if state.wavelength_nm <= 0:
            continue
        nu_center_cm1 = 1.0e7 / state.wavelength_nm
        f = state.oscillator_strength
        if method == "gaussian":
            profile = np.exp(
                -0.5 * ((nu_grid_cm1 - nu_center_cm1) / sigma_cm1) ** 2
            ) / (sigma_cm1 * math.sqrt(2.0 * math.pi))
        else:
            gamma_cm1 = GAUSSIAN_STD_TO_HWHM * sigma_cm1
            profile = (gamma_cm1 / math.pi) / (
                (nu_grid_cm1 - nu_center_cm1) ** 2 + gamma_cm1**2
            )
        epsilon += EPSILON_PREFACTOR_M_1_CM_2 * f * profile
    return wavelengths_nm, epsilon


def compute_absorbance(
    epsilon: NDArray[np.float64],
    concentration_molar: float = REFERENCE_CONCENTRATION_MOLAR,
    path_cm: float = REFERENCE_PATH_CM,
) -> NDArray[np.float64]:
    return epsilon * concentration_molar * path_cm


def compute_absorptance(
    absorbance: NDArray[np.float64],
) -> NDArray[np.float64]:
    return 1.0 - np.power(10.0, -absorbance)


def _data_dir() -> Path:
    return Path(__file__).resolve().parents[1] / "data"


def load_light_source_csv(
    source_path: Path,
    source_name: str | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64], str]:
    resolved_name = source_name or source_path.stem
    try:
        frame = pd.read_csv(source_path)
    except (OSError, ValueError) as exc:
        raise InputError(
            format_error(ErrorCode.INPUT, f"Failed to read light source CSV: {source_path}")
        ) from exc
    required = {"wavelength_nm", "intensity"}
    if not required.issubset(frame.columns):
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                "Light source CSV must contain columns: wavelength_nm,intensity",
            )
        )

    wavelengths = frame["wavelength_nm"].to_numpy(dtype=np.float64)
    intensity = frame["intensity"].to_numpy(dtype=np.float64)
    if wavelengths.size < 2:
        raise InputError(format_error(ErrorCode.INPUT, "Light source CSV must have >=2 rows."))
    if np.any(wavelengths <= 0):
        raise InputError(format_error(ErrorCode.INPUT, "Light source wavelengths must be > 0."))
    if np.any(intensity < 0):
        raise InputError(format_error(ErrorCode.INPUT, "Light source intensity must be >= 0."))

    order = np.argsort(wavelengths)
    return wavelengths[order], intensity[order], resolved_name


def _load_led_from_master(led_name: str) -> tuple[NDArray[np.float64], NDArray[np.float64], str]:
    source_path = _data_dir() / LED_MASTER_FILE
    try:
        frame = pd.read_csv(source_path, header=None)
    except (OSError, ValueError) as exc:
        raise InputError(
            format_error(ErrorCode.INPUT, f"Failed to read LED source CSV: {source_path}")
        ) from exc

    column_index = LED_COLUMN_INDEX[led_name]
    required_columns = max(0, column_index) + 1
    if frame.shape[1] < required_columns:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                (
                    f"LED source file {source_path} does not contain required column index "
                    f"{column_index} for {led_name}."
                ),
            )
        )

    wavelengths = pd.to_numeric(frame.iloc[:, 0], errors="coerce").to_numpy(dtype=np.float64)
    intensity = pd.to_numeric(frame.iloc[:, column_index], errors="coerce").to_numpy(
        dtype=np.float64
    )
    valid = np.isfinite(wavelengths) & np.isfinite(intensity)
    wavelengths = wavelengths[valid]
    intensity = intensity[valid]

    if wavelengths.size < 2:
        raise InputError(format_error(ErrorCode.INPUT, "LED source data must have >=2 rows."))
    if np.any(wavelengths <= 0):
        raise InputError(format_error(ErrorCode.INPUT, "LED source wavelengths must be > 0."))
    if np.any(intensity < 0):
        raise InputError(format_error(ErrorCode.INPUT, "LED source intensity must be >= 0."))

    order = np.argsort(wavelengths)
    return wavelengths[order], intensity[order], led_name


def _load_fl_from_master(fl_name: str) -> tuple[NDArray[np.float64], NDArray[np.float64], str]:
    source_path = _data_dir() / FL_MASTER_FILE
    try:
        frame = pd.read_csv(source_path, header=None)
    except (OSError, ValueError) as exc:
        raise InputError(
            format_error(ErrorCode.INPUT, f"Failed to read FL source CSV: {source_path}")
        ) from exc

    column_index = FL_COLUMN_INDEX[fl_name]
    required_columns = max(0, column_index) + 1
    if frame.shape[1] < required_columns:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                (
                    f"FL source file {source_path} does not contain required column index "
                    f"{column_index} for {fl_name}."
                ),
            )
        )

    wavelengths = pd.to_numeric(frame.iloc[:, 0], errors="coerce").to_numpy(dtype=np.float64)
    intensity = pd.to_numeric(frame.iloc[:, column_index], errors="coerce").to_numpy(
        dtype=np.float64
    )
    valid = np.isfinite(wavelengths) & np.isfinite(intensity)
    wavelengths = wavelengths[valid]
    intensity = intensity[valid]

    if wavelengths.size < 2:
        raise InputError(format_error(ErrorCode.INPUT, "FL source data must have >=2 rows."))
    if np.any(wavelengths <= 0):
        raise InputError(format_error(ErrorCode.INPUT, "FL source wavelengths must be > 0."))
    if np.any(intensity < 0):
        raise InputError(format_error(ErrorCode.INPUT, "FL source intensity must be >= 0."))

    order = np.argsort(wavelengths)
    return wavelengths[order], intensity[order], fl_name


def load_light_sources(
    default_names: list[str] | None = None,
    custom_paths: list[Path] | None = None,
) -> dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]]:
    names = default_names or ["AM15G", "LEDB2", "LEDB3", "LEDB4", "CIEFL10"]
    loaded: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]] = {}
    for name in names:
        key = name.strip().upper()
        if key in LED_COLUMN_INDEX:
            wl, intensity, resolved = _load_led_from_master(key)
            loaded[resolved] = (wl, intensity)
            continue
        if key in FL_COLUMN_INDEX:
            wl, intensity, resolved = _load_fl_from_master(key)
            loaded[resolved] = (wl, intensity)
            continue

        filename = BUILTIN_LIGHT_SOURCES.get(key)
        if filename is None:
            allowed = ", ".join(sorted(BUILTIN_LIGHT_SOURCES.keys()))
            led_allowed = ", ".join(sorted(LED_COLUMN_INDEX.keys()))
            fl_allowed = ", ".join(sorted(FL_COLUMN_INDEX.keys()))
            raise InputError(
                format_error(
                    ErrorCode.INPUT,
                    (
                        f"Unknown default light source '{name}'. Allowed: {allowed}"
                        f"{', ' if led_allowed else ''}{led_allowed}"
                        f"{', ' if fl_allowed else ''}{fl_allowed}"
                    ),
                )
            )
        path = _data_dir() / filename
        wl, intensity, resolved = load_light_source_csv(path, source_name=key)
        loaded[resolved] = (wl, intensity)

    for path in custom_paths or []:
        wl, intensity, resolved = load_light_source_csv(path)
        loaded[resolved] = (wl, intensity)

    if not loaded:
        raise InputError(format_error(ErrorCode.INPUT, "No light sources available for analysis."))
    return loaded


def load_light_source(
    source_path: Path | None,
    source_name: str | None = None,
) -> tuple[NDArray[np.float64], NDArray[np.float64], str]:
    if source_path is None:
        default_path = _data_dir() / BUILTIN_LIGHT_SOURCES["AM15G"]
        return load_light_source_csv(default_path, source_name=source_name or "AM15G")
    return load_light_source_csv(source_path, source_name=source_name)


def resample_light_source_to_grid(
    source_wavelengths: NDArray[np.float64],
    source_intensity: NDArray[np.float64],
    target_wavelengths: NDArray[np.float64],
) -> NDArray[np.float64]:
    return np.interp(
        target_wavelengths,
        source_wavelengths,
        source_intensity,
        left=0.0,
        right=0.0,
    )


def integrate_light_flux(
    light_intensity: NDArray[np.float64],
    wavelengths: NDArray[np.float64],
) -> float:
    return float(np.trapezoid(light_intensity, wavelengths))


def integrate_absorbed_flux(
    absorptance: NDArray[np.float64],
    light_intensity: NDArray[np.float64],
    wavelengths: NDArray[np.float64],
) -> float:
    return float(np.trapezoid(absorptance * light_intensity, wavelengths))


def normalize_signal_max(values: NDArray[np.float64]) -> NDArray[np.float64]:
    max_value = float(np.max(values)) if values.size else 0.0
    if max_value <= 0.0:
        return np.zeros_like(values)
    return values / max_value


def shape_overlap(
    absorptance: NDArray[np.float64],
    light_intensity: NDArray[np.float64],
    wavelengths: NDArray[np.float64],
) -> float:
    absorptance_norm = normalize_signal_max(absorptance)
    light_norm = normalize_signal_max(light_intensity)
    numerator = float(
        np.trapezoid(np.minimum(absorptance_norm, light_norm), wavelengths)
    )
    denominator = float(np.trapezoid(light_norm, wavelengths))
    if denominator <= 0.0:
        return 0.0
    return numerator / denominator


def get_light_source_unit(source_name: str) -> str:
    return LIGHT_SOURCE_UNITS.get(source_name.strip().upper(), "unspecified")


def get_absorbed_flux_unit(source_name: str) -> str:
    light_unit = get_light_source_unit(source_name)
    if light_unit == "W m^-2 nm^-1":
        return "W m^-2"
    if light_unit == "relative":
        return "relative_integral"
    return "unspecified"
