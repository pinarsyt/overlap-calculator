"""Spectral-overlap analysis between absorption spectra and reference light sources.

Public, importable API. Minimal usage::

    from overlap_calculator import analyze, build_extinction_spectrum
    from overlap_calculator.models import AnalysisInput

    items = [AnalysisInput(input_type="theoretical", source_path="tddft.out")]
    results, skipped = analyze(items, default_light_sources=["AM15G"])

The building blocks (spectrum reconstruction, Beer-Lambert, descriptors,
light-source loaders, calibration) are re-exported here so the package can be
used as a library without importing private submodule paths.
"""

from __future__ import annotations

__version__ = "1.1.1"

from overlap_calculator.calculations.calibration import (
    Calibration,
    apply_calibration,
    load_calibration,
)
from overlap_calculator.calculations.spectrum import (
    build_extinction_spectrum,
    compute_absorbance,
    compute_absorptance,
    integrate_absorbed_flux,
    integrate_light_flux,
    load_light_sources,
    marcus_hush_sigma_ev,
    shape_overlap,
)
from overlap_calculator.services.analyzer import (
    analyze,
    analyze_inputs,
    export_results,
    prepare_output_dir,
)
from overlap_calculator.services.provenance import build_run_manifest, write_run_manifest

__all__ = [
    "__version__",
    # high-level pipeline
    "analyze",
    "analyze_inputs",
    "export_results",
    "prepare_output_dir",
    # spectrum reconstruction + Beer-Lambert
    "build_extinction_spectrum",
    "compute_absorbance",
    "compute_absorptance",
    "marcus_hush_sigma_ev",
    # descriptors / flux integrals
    "shape_overlap",
    "integrate_light_flux",
    "integrate_absorbed_flux",
    # light sources
    "load_light_sources",
    # calibration
    "Calibration",
    "load_calibration",
    "apply_calibration",
    # provenance
    "build_run_manifest",
    "write_run_manifest",
]
