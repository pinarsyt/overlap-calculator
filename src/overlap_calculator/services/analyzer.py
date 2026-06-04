from __future__ import annotations

import logging
import re
import time
from collections.abc import Mapping
from pathlib import Path

import numpy as np
from numpy.typing import NDArray

from overlap_calculator import __version__
from overlap_calculator.calculations.calibration import (
    BandOverride,
    Calibration,
    apply_calibration,
)
from overlap_calculator.calculations.spectrum import (
    DEFAULT_TEMPERATURE_K,
    REFERENCE_CONCENTRATION_MOLAR,
    REFERENCE_PATH_CM,
    build_extinction_spectrum,
    compute_absorbance,
    compute_absorptance,
    get_absorbed_flux_unit,
    get_light_source_unit,
    integrate_absorbed_flux,
    integrate_light_flux,
    load_light_sources,
    marcus_hush_sigma_ev,
    resample_light_source_to_grid,
    shape_overlap,
    validate_prefactor_mode,
    validate_sigma_mode,
)
from overlap_calculator.exceptions import AnalysisError, ParseError
from overlap_calculator.models import (
    AnalysisInput,
    AnalysisSkip,
    ExcitedState,
    RunResult,
    TDResult,
)
from overlap_calculator.parsers.experimental import load_experimental_series
from overlap_calculator.parsers.td import extract_chk_name, parse_td_output
from overlap_calculator.services.export import (
    export_results,
    prepare_output_dir,
)
from overlap_calculator.utils.errors import ErrorCode, format_error
from overlap_calculator.utils.logging import format_log

LOGGER = logging.getLogger(__name__)
_ROUTE_TD = re.compile(r"(?i)#\s*.*\btd\b")
_METHODS: tuple[str, str] = ("gaussian", "lorentzian")
_THEORETICAL_ABSORPTION_UNIT = (
    f"absorptance (Beer-Lambert at c={REFERENCE_CONCENTRATION_MOLAR:g} M, "
    f"L={REFERENCE_PATH_CM:g} cm)"
)
_EXPERIMENTAL_ABSORPTION_UNIT = "absorbance proxy (user-provided signal, no Beer-Lambert)"

__all__ = [
    "analyze",
    "analyze_inputs",
    "export_results",
    "prepare_output_dir",
]


def _resolve_per_state_sigma_ev(
    states: list[ExcitedState],
    sigma_mode: str,
    sigma_ev: float,
    reorganization_ev: float,
    temperature_k: float,
    overrides: Mapping[int, BandOverride],
) -> list[float]:
    """Per-transition Gaussian/Lorentzian sigma (eV) for the broadening kernel.

    Priority per state: explicit per-band sigma override > Marcus-Hush sigma
    (from a per-band or global reorganization energy) > the global fixed sigma.
    """
    sigmas: list[float] = []
    for index, _state in enumerate(states, start=1):
        override = overrides.get(index)
        if override is not None and override.sigma_ev is not None:
            sigmas.append(override.sigma_ev)
            continue
        if sigma_mode == "marcus-hush":
            reorg = (
                override.reorganization_ev
                if override is not None and override.reorganization_ev is not None
                else reorganization_ev
            )
            sigmas.append(marcus_hush_sigma_ev(reorg, temperature_k))
        else:
            sigmas.append(sigma_ev)
    return sigmas


def _looks_like_tddft_output(path: Path) -> bool:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if _ROUTE_TD.search(line):
                    return True
                if "Excited State" in line:
                    return True
    except OSError:
        return False
    return False


def _build_theoretical_result(
    *,
    sample_id: str,
    source_path: Path,
    td: TDResult | None,
    broadening_method: str,
    sigma_ev: float,
    prefactor_mode: str,
    sigma_mode: str,
    light_source_name: str,
    wavelengths: NDArray[np.float64],
    epsilon: NDArray[np.float64],
    intensity: NDArray[np.float64],
    concentration_molar: float,
    path_cm: float,
    timings_ms: dict[str, float],
) -> RunResult:
    absorbance = compute_absorbance(epsilon, concentration_molar, path_cm)
    absorptance = compute_absorptance(absorbance)
    absorbed_flux = integrate_absorbed_flux(absorptance, intensity, wavelengths)
    light_flux_total = integrate_light_flux(intensity, wavelengths)
    absorbed_fraction = absorbed_flux / light_flux_total if light_flux_total > 0.0 else 0.0
    shape = shape_overlap(absorptance, intensity, wavelengths)
    lambda_max_nm = float(wavelengths[int(np.argmax(epsilon))]) if epsilon.size else 0.0
    epsilon_max = float(np.max(epsilon)) if epsilon.size else 0.0
    absorptance_max = float(np.max(absorptance)) if absorptance.size else 0.0

    return RunResult(
        source_type="theoretical",
        sample_id=sample_id,
        source_path=str(source_path),
        td=td,
        lambda_max_nm=lambda_max_nm,
        molar_absorptivity_max=epsilon_max,
        absorptance_max=absorptance_max,
        absorbed_flux=absorbed_flux,
        absorbed_flux_unit=get_absorbed_flux_unit(light_source_name),
        light_flux_total=light_flux_total,
        absorbed_fraction=absorbed_fraction,
        shape_overlap=shape,
        absorption_unit=_THEORETICAL_ABSORPTION_UNIT,
        light_source_unit=get_light_source_unit(light_source_name),
        broadening_method=broadening_method,
        sigma_ev=sigma_ev,
        prefactor_mode=prefactor_mode,
        sigma_mode=sigma_mode,
        software_version=__version__,
        reference_concentration_molar=concentration_molar,
        reference_path_cm=path_cm,
        light_source_name=light_source_name,
        wavelengths_nm=wavelengths.tolist(),
        absorptance=absorptance.tolist(),
        molar_absorptivity=epsilon.tolist(),
        light_intensity=intensity.tolist(),
        timings_ms=timings_ms,
    )


def _build_experimental_result(
    *,
    sample_id: str,
    source_path: Path,
    broadening_method: str,
    sigma_ev: float,
    prefactor_mode: str,
    sigma_mode: str,
    light_source_name: str,
    wavelengths: NDArray[np.float64],
    absorbance: NDArray[np.float64],
    intensity: NDArray[np.float64],
    timings_ms: dict[str, float],
) -> RunResult:
    absorptance = compute_absorptance(absorbance)
    absorbed_flux = integrate_absorbed_flux(absorptance, intensity, wavelengths)
    light_flux_total = integrate_light_flux(intensity, wavelengths)
    absorbed_fraction = absorbed_flux / light_flux_total if light_flux_total > 0.0 else 0.0
    shape = shape_overlap(absorptance, intensity, wavelengths)
    lambda_max_nm = float(wavelengths[int(np.argmax(absorbance))]) if absorbance.size else 0.0
    absorptance_max = float(np.max(absorptance)) if absorptance.size else 0.0

    return RunResult(
        source_type="experimental",
        sample_id=sample_id,
        source_path=str(source_path),
        td=None,
        lambda_max_nm=lambda_max_nm,
        molar_absorptivity_max=0.0,
        absorptance_max=absorptance_max,
        absorbed_flux=absorbed_flux,
        absorbed_flux_unit=get_absorbed_flux_unit(light_source_name),
        light_flux_total=light_flux_total,
        absorbed_fraction=absorbed_fraction,
        shape_overlap=shape,
        absorption_unit=_EXPERIMENTAL_ABSORPTION_UNIT,
        light_source_unit=get_light_source_unit(light_source_name),
        broadening_method=broadening_method,
        sigma_ev=sigma_ev,
        prefactor_mode=prefactor_mode,
        sigma_mode=sigma_mode,
        software_version=__version__,
        reference_concentration_molar=0.0,
        reference_path_cm=0.0,
        light_source_name=light_source_name,
        wavelengths_nm=wavelengths.tolist(),
        absorptance=absorptance.tolist(),
        molar_absorptivity=[0.0] * wavelengths.size,
        light_intensity=intensity.tolist(),
        timings_ms=timings_ms,
    )


def _analyze_theoretical_item(
    item: AnalysisInput,
    sigma_ev: float,
    wl_min: float,
    wl_max: float,
    num_points: int,
    concentration_molar: float,
    path_cm: float,
    light_sources: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]],
    prefactor_mode: str,
    sigma_mode: str,
    reorganization_ev: float,
    temperature_k: float,
    calibration: Calibration | None,
) -> tuple[list[RunResult], AnalysisSkip | None]:
    source_path = Path(item.source_path)
    sample_id = item.sample_id or extract_chk_name(source_path) or source_path.stem

    if not _looks_like_tddft_output(source_path):
        return [], AnalysisSkip(
            sample_id=sample_id,
            td_path=item.source_path,
            reason="INPUT_ERROR: file does not look like a TD-DFT output",
        )

    started = time.perf_counter()
    try:
        t_parse = time.perf_counter()
        td = parse_td_output(source_path)
        parse_ms = (time.perf_counter() - t_parse) * 1000.0
    except ParseError as exc:
        return [], AnalysisSkip(
            sample_id=sample_id,
            td_path=item.source_path,
            reason=format_error(
                ErrorCode.ANALYSIS,
                f"Failed to parse TD-DFT file: {source_path} ({exc})",
            ),
        )

    states = apply_calibration(td.excited_states, calibration) if calibration else td.excited_states
    overrides = calibration.overrides_by_index() if calibration else {}
    per_state_sigma_ev = _resolve_per_state_sigma_ev(
        states,
        sigma_mode=sigma_mode,
        sigma_ev=sigma_ev,
        reorganization_ev=reorganization_ev,
        temperature_k=temperature_k,
        overrides=overrides,
    )
    # Representative scalar for the result row: the first transition's width. Per-state
    # widths may differ under marcus-hush + per-band overrides; sigma_mode flags that.
    recorded_sigma_ev = per_state_sigma_ev[0] if per_state_sigma_ev else sigma_ev

    results: list[RunResult] = []
    for method in _METHODS:
        t_broadening = time.perf_counter()
        wavelengths, epsilon = build_extinction_spectrum(
            states,
            method=method,
            sigma_ev=sigma_ev,
            wavelength_min_nm=wl_min,
            wavelength_max_nm=wl_max,
            num_points=num_points,
            prefactor_mode=prefactor_mode,
            per_state_sigma_ev=per_state_sigma_ev,
        )
        broadening_ms = (time.perf_counter() - t_broadening) * 1000.0

        for light_name, (light_wavelengths, light_intensity) in light_sources.items():
            t_light = time.perf_counter()
            intensity = resample_light_source_to_grid(
                light_wavelengths,
                light_intensity,
                wavelengths,
            )
            light_ms = (time.perf_counter() - t_light) * 1000.0

            t_integrals = time.perf_counter()
            result = _build_theoretical_result(
                sample_id=sample_id,
                source_path=source_path,
                td=td,
                broadening_method=method,
                sigma_ev=recorded_sigma_ev,
                prefactor_mode=prefactor_mode,
                sigma_mode=sigma_mode,
                light_source_name=light_name,
                wavelengths=wavelengths,
                epsilon=epsilon,
                intensity=intensity,
                concentration_molar=concentration_molar,
                path_cm=path_cm,
                timings_ms={},
            )
            integrals_ms = (time.perf_counter() - t_integrals) * 1000.0
            total_sample_ms = (time.perf_counter() - started) * 1000.0
            result = result.model_copy(update={
                "timings_ms": {
                    "parse_tddft_ms": parse_ms,
                    "broadening_ms": broadening_ms,
                    "light_source_ms": light_ms,
                    "integrals_ms": integrals_ms,
                    "total_sample_ms": total_sample_ms,
                }
            })
            results.append(result)
    return results, None


def _analyze_experimental_item(
    item: AnalysisInput,
    sigma_ev: float,
    light_sources: dict[str, tuple[NDArray[np.float64], NDArray[np.float64]]],
    prefactor_mode: str,
    sigma_mode: str,
) -> tuple[list[RunResult], AnalysisSkip | None]:
    source_path = Path(item.source_path)
    sample_id = item.sample_id or source_path.stem
    started = time.perf_counter()
    try:
        t_parse = time.perf_counter()
        series_name, wavelengths, absorbance = load_experimental_series(
            source_path,
            series_name=item.series_name,
            sheet_name=item.sheet_name,
        )
        parse_ms = (time.perf_counter() - t_parse) * 1000.0
    except Exception as exc:
        return [], AnalysisSkip(
            sample_id=sample_id,
            td_path=item.source_path,
            reason=format_error(
                ErrorCode.ANALYSIS,
                f"Failed to parse experimental file: {source_path} ({exc})",
            ),
        )

    if not item.sample_id:
        sample_id = series_name

    results: list[RunResult] = []
    for method in _METHODS:
        for light_name, (light_wavelengths, light_intensity) in light_sources.items():
            t_light = time.perf_counter()
            intensity = resample_light_source_to_grid(
                light_wavelengths,
                light_intensity,
                wavelengths,
            )
            light_ms = (time.perf_counter() - t_light) * 1000.0

            t_integrals = time.perf_counter()
            result = _build_experimental_result(
                sample_id=sample_id,
                source_path=source_path,
                broadening_method=method,
                sigma_ev=sigma_ev,
                prefactor_mode=prefactor_mode,
                sigma_mode=sigma_mode,
                light_source_name=light_name,
                wavelengths=wavelengths,
                absorbance=absorbance,
                intensity=intensity,
                timings_ms={},
            )
            integrals_ms = (time.perf_counter() - t_integrals) * 1000.0
            total_sample_ms = (time.perf_counter() - started) * 1000.0
            result = result.model_copy(update={
                "timings_ms": {
                    "parse_tddft_ms": parse_ms,
                    "broadening_ms": 0.0,
                    "light_source_ms": light_ms,
                    "integrals_ms": integrals_ms,
                    "total_sample_ms": total_sample_ms,
                }
            })
            results.append(result)
    return results, None


def analyze_inputs(
    items: list[AnalysisInput],
    sigma_ev: float,
    wl_min: float,
    wl_max: float,
    num_points: int,
    concentration_molar: float = REFERENCE_CONCENTRATION_MOLAR,
    path_cm: float = REFERENCE_PATH_CM,
    default_light_sources: list[str] | None = None,
    custom_light_source_paths: list[Path] | None = None,
    prefactor_mode: str = "constant",
    sigma_mode: str = "fixed",
    reorganization_ev: float = 0.30,
    temperature_k: float = DEFAULT_TEMPERATURE_K,
    calibration: Calibration | None = None,
) -> tuple[list[RunResult], list[AnalysisSkip]]:
    if not items:
        raise AnalysisError("No analysis inputs provided.")

    prefactor_mode = validate_prefactor_mode(prefactor_mode)
    sigma_mode = validate_sigma_mode(sigma_mode)

    light_sources = load_light_sources(
        default_names=default_light_sources,
        custom_paths=custom_light_source_paths,
    )
    LOGGER.info(
        format_log(
            "load",
            "light_sources",
            count=len(light_sources),
            names=",".join(sorted(light_sources.keys())),
        )
    )

    results: list[RunResult] = []
    skipped_items: list[AnalysisSkip] = []
    for item in items:
        if item.input_type == "theoretical":
            sample_results, skip = _analyze_theoretical_item(
                item,
                sigma_ev=sigma_ev,
                wl_min=wl_min,
                wl_max=wl_max,
                num_points=num_points,
                concentration_molar=concentration_molar,
                path_cm=path_cm,
                light_sources=light_sources,
                prefactor_mode=prefactor_mode,
                sigma_mode=sigma_mode,
                reorganization_ev=reorganization_ev,
                temperature_k=temperature_k,
                calibration=calibration,
            )
        else:
            sample_results, skip = _analyze_experimental_item(
                item,
                sigma_ev=sigma_ev,
                light_sources=light_sources,
                prefactor_mode=prefactor_mode,
                sigma_mode=sigma_mode,
            )

        if skip is not None:
            skipped_items.append(skip)
            LOGGER.warning(
                format_log(
                    "analyze",
                    "skip_input",
                    sample_id=skip.sample_id,
                    source=skip.td_path,
                    reason=skip.reason,
                )
            )
            continue

        results.extend(sample_results)

    if not results:
        raise AnalysisError(
            format_error(
                ErrorCode.ANALYSIS,
                "No valid theoretical or experimental files could be analyzed.",
            )
        )

    LOGGER.info(
        format_log(
            "analyze",
            "batch_summary",
            total=len(items),
            produced=len(results),
            skipped=len(skipped_items),
        )
    )
    return results, skipped_items


def analyze(
    items: list[AnalysisInput],
    *,
    sigma_ev: float = 0.30,
    wl_min: float = 200.0,
    wl_max: float = 800.0,
    num_points: int = 10000,
    concentration_molar: float = REFERENCE_CONCENTRATION_MOLAR,
    path_cm: float = REFERENCE_PATH_CM,
    default_light_sources: list[str] | None = None,
    custom_light_source_paths: list[Path] | None = None,
    prefactor_mode: str = "constant",
    sigma_mode: str = "fixed",
    reorganization_ev: float = 0.30,
    temperature_k: float = DEFAULT_TEMPERATURE_K,
    calibration: Calibration | None = None,
) -> tuple[list[RunResult], list[AnalysisSkip]]:
    """High-level entry point: analyze prepared inputs and return results.

    This is the importable-library counterpart of the CLI ``analyze`` command.
    It runs the full Gaussian + Lorentzian broadening, Beer-Lambert, and overlap
    pipeline against the requested reference light sources and returns the per
    (sample, light-source, method) :class:`RunResult` records plus the list of
    skipped inputs. Use :func:`export_results` to write tables/plots and
    :func:`overlap_calculator.services.provenance.write_run_manifest` for
    reproducibility metadata.

    >>> from overlap_calculator import analyze
    >>> from overlap_calculator.models import AnalysisInput
    >>> callable(analyze)
    True
    """
    return analyze_inputs(
        items,
        sigma_ev=sigma_ev,
        wl_min=wl_min,
        wl_max=wl_max,
        num_points=num_points,
        concentration_molar=concentration_molar,
        path_cm=path_cm,
        default_light_sources=default_light_sources,
        custom_light_source_paths=custom_light_source_paths,
        prefactor_mode=prefactor_mode,
        sigma_mode=sigma_mode,
        reorganization_ev=reorganization_ev,
        temperature_k=temperature_k,
        calibration=calibration,
    )
