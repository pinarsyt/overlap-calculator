import math

import numpy as np

from overlap_calculator.calculations.spectrum import (
    EPSILON_PREFACTOR_M_1_CM_2,
    build_extinction_spectrum,
    compute_absorbance,
    compute_absorptance,
    integrate_absorbed_flux,
    integrate_light_flux,
    shape_overlap,
)
from overlap_calculator.models import ExcitedState


def test_extinction_spectrum_units_and_shape():
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=620.0, f=0.5)]
    wavelengths, epsilon = build_extinction_spectrum(
        states,
        method="gaussian",
        sigma_ev=0.3,
        wavelength_min_nm=400.0,
        wavelength_max_nm=800.0,
        num_points=4000,
    )
    assert len(wavelengths) == 4000
    assert len(epsilon) == 4000
    assert epsilon.max() > 0.0
    assert np.all(epsilon >= 0.0)


def test_extinction_spectrum_conserves_oscillator_strength():
    f_total = 0.5
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=620.0, f=f_total)]
    wavelengths, epsilon = build_extinction_spectrum(
        states,
        method="gaussian",
        sigma_ev=0.3,
        wavelength_min_nm=200.0,
        wavelength_max_nm=1500.0,
        num_points=20000,
    )
    nu_grid = 1.0e7 / wavelengths
    order = np.argsort(nu_grid)
    integrated_in_cm1 = float(np.trapezoid(epsilon[order], nu_grid[order]))
    expected = EPSILON_PREFACTOR_M_1_CM_2 * f_total
    assert math.isclose(integrated_in_cm1, expected, rel_tol=5e-3)


def test_build_extinction_spectrum_lorentzian_positive():
    states = [ExcitedState(state=1, energy_ev=2.0, wavelength_nm=620.0, f=0.3)]
    _, epsilon = build_extinction_spectrum(
        states,
        method="lorentzian",
        sigma_ev=0.3,
        wavelength_min_nm=400.0,
        wavelength_max_nm=800.0,
        num_points=2000,
    )
    assert epsilon.max() > 0.0
    assert np.all(epsilon >= 0.0)


def test_beer_lambert_absorptance_bounded():
    epsilon = np.array([0.0, 1.0e3, 1.0e4, 1.0e5], dtype=np.float64)
    absorbance = compute_absorbance(epsilon, concentration_molar=1.0e-5, path_cm=1.0)
    absorptance = compute_absorptance(absorbance)
    assert np.all(absorptance >= 0.0)
    assert np.all(absorptance < 1.0)
    assert absorptance[0] == 0.0
    assert absorptance[3] > absorptance[1]


def test_integrate_absorbed_flux_product_not_min():
    wavelengths = np.linspace(400.0, 700.0, 1000)
    absorptance = np.full_like(wavelengths, 0.5)
    intensity = np.full_like(wavelengths, 2.0)
    flux = integrate_absorbed_flux(absorptance, intensity, wavelengths)
    light = integrate_light_flux(intensity, wavelengths)
    assert math.isclose(flux, 0.5 * light, rel_tol=1e-9)


def test_shape_overlap_peaks_when_aligned():
    wavelengths = np.linspace(400.0, 700.0, 1000)
    light = np.exp(-0.5 * ((wavelengths - 550.0) / 30.0) ** 2)
    aligned = np.exp(-0.5 * ((wavelengths - 550.0) / 30.0) ** 2)
    misaligned = np.exp(-0.5 * ((wavelengths - 450.0) / 30.0) ** 2)
    aligned_score = shape_overlap(aligned, light, wavelengths)
    misaligned_score = shape_overlap(misaligned, light, wavelengths)
    assert 0.0 <= misaligned_score < aligned_score <= 1.0
