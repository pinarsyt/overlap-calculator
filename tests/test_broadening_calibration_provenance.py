"""Tests for the configurable broadening, calibration, public API, and provenance features.

Covers: the public importable API, the frequency-resolved prefactor mode, the
Marcus-Hush sigma path, the calibration block, and the run-manifest provenance.
The physics targets (area invariance, +1/2 (sigma/nu)^2 peak excess, blue-shift,
sigma = sqrt(2 lambda kB T)) follow the derivations in the user manual.
"""

import json
import math
import os
from pathlib import Path

import numpy as np
import pytest

import overlap_calculator
from overlap_calculator import (
    analyze,
    analyze_inputs,
    build_extinction_spectrum,
    marcus_hush_sigma_ev,
)
from overlap_calculator.calculations.calibration import (
    BandOverride,
    Calibration,
    apply_calibration,
    load_calibration,
)
from overlap_calculator.calculations.spectrum import BOLTZMANN_EV_PER_K, CM1_PER_EV
from overlap_calculator.exceptions import InputError
from overlap_calculator.models import AnalysisInput, ExcitedState
from overlap_calculator.services.analyzer import _resolve_per_state_sigma_ev
from overlap_calculator.services.provenance import build_run_manifest, write_run_manifest

_TDDFT_TEXT = """ #p td b3lyp/6-31g scrf=(solvent=water)

 Excited State   1:      Singlet-A      2.4000 eV  516.60 nm  f=0.5000
 Excited State   2:      Singlet-A      3.1000 eV  399.95 nm  f=0.2000
"""


def _band_area_cm1(wavelengths: np.ndarray, epsilon: np.ndarray) -> float:
    nu = 1.0e7 / wavelengths
    order = np.argsort(nu)
    return float(np.trapezoid(epsilon[order], nu[order]))


# --------------------------------------------------------------------------- #
# Public importable API
# --------------------------------------------------------------------------- #
def test_public_api_surface() -> None:
    expected = [
        "analyze",
        "analyze_inputs",
        "export_results",
        "prepare_output_dir",
        "build_extinction_spectrum",
        "compute_absorbance",
        "compute_absorptance",
        "shape_overlap",
        "integrate_light_flux",
        "integrate_absorbed_flux",
        "load_light_sources",
        "marcus_hush_sigma_ev",
        "Calibration",
        "load_calibration",
        "apply_calibration",
        "build_run_manifest",
        "write_run_manifest",
        "__version__",
    ]
    for name in expected:
        assert hasattr(overlap_calculator, name), f"missing public name: {name}"
        assert name in overlap_calculator.__all__
    # The expected set must track __all__ exactly, so a future export is not missed.
    assert set(expected) == set(overlap_calculator.__all__)


def test_analyze_is_callable() -> None:
    assert callable(analyze)


def test_invalid_sigma_mode_rejected() -> None:
    items = [AnalysisInput(input_type="theoretical", source_path="x.out")]
    with pytest.raises(InputError):
        analyze_inputs(
            items,
            sigma_ev=0.30,
            wl_min=200.0,
            wl_max=800.0,
            num_points=2000,
            sigma_mode="bogus",
        )


# --------------------------------------------------------------------------- #
# Frequency-resolved prefactor mode
# --------------------------------------------------------------------------- #
def test_frequency_resolved_area_matches_constant() -> None:
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=500.0, f=0.5)]
    common = dict(
        method="gaussian",
        sigma_ev=0.30,
        wavelength_min_nm=200.0,
        wavelength_max_nm=800.0,
        num_points=40000,
    )
    wl, e_const = build_extinction_spectrum(states, prefactor_mode="constant", **common)
    _, e_fr = build_extinction_spectrum(states, prefactor_mode="frequency-resolved", **common)
    area_const = _band_area_cm1(wl, e_const)
    area_fr = _band_area_cm1(wl, e_fr)
    # Symmetric lineshape => identical integrated intensity (to grid precision).
    assert math.isclose(area_const, area_fr, rel_tol=1e-3)


def test_frequency_resolved_peak_excess_matches_theory() -> None:
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=500.0, f=0.5)]
    common = dict(
        method="gaussian",
        sigma_ev=0.30,
        wavelength_min_nm=440.0,
        wavelength_max_nm=560.0,
        num_points=60000,
    )
    _, e_const = build_extinction_spectrum(states, prefactor_mode="constant", **common)
    _, e_fr = build_extinction_spectrum(states, prefactor_mode="frequency-resolved", **common)
    sigma_cm = 0.30 * CM1_PER_EV
    nu_i = 1.0e7 / 500.0
    expected = 0.5 * (sigma_cm / nu_i) ** 2  # ~0.73 % for a 500 nm band, sigma=0.30 eV
    excess = (e_fr.max() - e_const.max()) / e_const.max()
    assert math.isclose(excess, expected, rel_tol=5e-2)
    assert excess < 0.02  # < 2 % in the visible range


def test_frequency_resolved_blueshifts_peak() -> None:
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=500.0, f=0.5)]
    common = dict(
        method="gaussian",
        sigma_ev=0.30,
        wavelength_min_nm=300.0,
        wavelength_max_nm=700.0,
        num_points=80000,
    )
    wl, e_const = build_extinction_spectrum(states, prefactor_mode="constant", **common)
    _, e_fr = build_extinction_spectrum(states, prefactor_mode="frequency-resolved", **common)
    lam_const = float(wl[int(np.argmax(e_const))])
    lam_fr = float(wl[int(np.argmax(e_fr))])
    assert lam_fr < lam_const  # FR peak shifts to higher wavenumber (shorter wavelength)


def test_invalid_prefactor_mode_rejected() -> None:
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=500.0, f=0.5)]
    with pytest.raises(InputError):
        build_extinction_spectrum(
            states,
            method="gaussian",
            sigma_ev=0.30,
            wavelength_min_nm=200.0,
            wavelength_max_nm=800.0,
            num_points=2000,
            prefactor_mode="bogus",
        )


# --------------------------------------------------------------------------- #
# Marcus-Hush broadening width
# --------------------------------------------------------------------------- #
def test_marcus_hush_sigma_formula_and_value() -> None:
    sigma = marcus_hush_sigma_ev(0.30, 298.15)
    assert math.isclose(sigma, math.sqrt(2.0 * 0.30 * BOLTZMANN_EV_PER_K * 298.15))
    assert math.isclose(sigma, 0.12416, abs_tol=1e-4)


def test_marcus_hush_rejects_nonpositive() -> None:
    with pytest.raises(InputError):
        marcus_hush_sigma_ev(0.0, 298.15)
    with pytest.raises(InputError):
        marcus_hush_sigma_ev(0.30, 0.0)


def test_marcus_hush_equivalent_to_fixed_sigma() -> None:
    sigma_eq = marcus_hush_sigma_ev(0.30, 298.15)
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=500.0, f=0.5)]
    common = dict(
        method="gaussian",
        wavelength_min_nm=300.0,
        wavelength_max_nm=700.0,
        num_points=4000,
    )
    _, e_fixed = build_extinction_spectrum(states, sigma_ev=sigma_eq, **common)
    _, e_per_state = build_extinction_spectrum(
        states, sigma_ev=0.30, per_state_sigma_ev=[sigma_eq], **common
    )
    assert np.array_equal(e_fixed, e_per_state)


def test_band_override_sigma_beats_marcus_hush() -> None:
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=500.0, f=0.5)]
    calib = Calibration(bands=[BandOverride(index=1, sigma_ev=0.25)])
    sigmas = _resolve_per_state_sigma_ev(
        states,
        sigma_mode="marcus-hush",
        sigma_ev=0.30,
        reorganization_ev=0.30,
        temperature_k=298.15,
        overrides=calib.overrides_by_index(),
    )
    assert sigmas == [0.25]


# --------------------------------------------------------------------------- #
# Calibration block
# --------------------------------------------------------------------------- #
def test_calibration_identity_short_circuits() -> None:
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=500.0, f=0.5)]
    calib = Calibration()
    assert calib.is_identity()
    assert apply_calibration(states, calib) is states


def test_calibration_identity_spectrum_bit_identical() -> None:
    states = [
        ExcitedState(state=1, energy_ev=2.0, wavelength_nm=620.0, f=0.5),
        ExcitedState(state=2, energy_ev=3.1, wavelength_nm=399.95, f=0.2),
    ]
    common = dict(
        method="gaussian",
        sigma_ev=0.30,
        wavelength_min_nm=200.0,
        wavelength_max_nm=800.0,
        num_points=4000,
    )
    _, e_no_calib = build_extinction_spectrum(states, **common)
    _, e_identity = build_extinction_spectrum(apply_calibration(states, Calibration()), **common)
    assert np.array_equal(e_no_calib, e_identity)


def test_calibration_energy_shift_recomputes_wavelength() -> None:
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=620.0, f=0.5)]
    out = apply_calibration(states, Calibration(energy_b=0.1))
    assert math.isclose(out[0].energy_ev, 2.1)
    assert out[0].wavelength_nm < 620.0
    assert math.isclose(out[0].wavelength_nm, 1239.841984 / 2.1, rel_tol=1e-9)


def test_calibration_alpha_scales_oscillator_only() -> None:
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=620.0, f=0.5)]
    out = apply_calibration(states, Calibration(oscillator_alpha=2.0))
    assert math.isclose(out[0].oscillator_strength, 1.0)
    assert out[0].wavelength_nm == 620.0
    assert out[0].energy_ev == 2.0


def test_calibration_rejects_nonpositive_energy() -> None:
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=620.0, f=0.5)]
    with pytest.raises(InputError):
        apply_calibration(states, Calibration(energy_a=1.0, energy_b=-5.0))


def test_load_calibration_toml(tmp_path: Path) -> None:
    path = tmp_path / "calib.toml"
    path.write_text(
        "[energy]\na = 1.0\nb = 0.05\n\n[oscillator]\nalpha = 1.1\n\n"
        "[[band]]\nindex = 1\nsigma_ev = 0.25\n",
        encoding="utf-8",
    )
    calib = load_calibration(path)
    assert math.isclose(calib.energy_a, 1.0)
    assert math.isclose(calib.energy_b, 0.05)
    assert math.isclose(calib.oscillator_alpha, 1.1)
    assert calib.bands[0].index == 1
    assert calib.bands[0].sigma_ev == 0.25
    assert not calib.is_identity()


# --------------------------------------------------------------------------- #
# Run-manifest provenance + end-to-end with the new modes
# --------------------------------------------------------------------------- #
def test_analyze_with_new_modes_and_manifest(tmp_path: Path) -> None:
    src = tmp_path / "sample.out"
    src.write_text(_TDDFT_TEXT, encoding="utf-8")
    items = [AnalysisInput(input_type="theoretical", source_path=str(src), sample_id="s1")]

    results, skipped = analyze_inputs(
        items,
        sigma_ev=0.30,
        wl_min=300.0,
        wl_max=800.0,
        num_points=2000,
        default_light_sources=["AM15G"],
        prefactor_mode="frequency-resolved",
        sigma_mode="marcus-hush",
        reorganization_ev=0.30,
    )
    assert results
    expected_sigma = marcus_hush_sigma_ev(0.30, 298.15)
    for result in results:
        assert result.prefactor_mode == "frequency-resolved"
        assert result.sigma_mode == "marcus-hush"
        assert math.isclose(result.sigma_ev, expected_sigma, rel_tol=1e-9)
        assert result.software_version == overlap_calculator.__version__

    manifest = build_run_manifest(
        results=results,
        items=items,
        parameters={"sigma_mode": "marcus-hush", "prefactor_mode": "frequency-resolved"},
        skipped_items=skipped,
        light_source_names=["AM15G"],
    )
    manifest_path = write_run_manifest(tmp_path, manifest)
    assert manifest_path.name == "run_manifest.json"

    data = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert data["software_version"] == overlap_calculator.__version__
    assert data["inputs"][0]["sample_id"] == "s1"
    # run-relative source path; the tmp input lives outside the run dir so it
    # falls back to the base name. Never an absolute machine path.
    assert data["inputs"][0]["source_path"] == "sample.out"
    assert not os.path.isabs(data["inputs"][0]["source_path"])
    assert len(data["inputs"][0]["sha256"]) == 64
    assert "generated_at_utc" in data
