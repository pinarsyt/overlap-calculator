from __future__ import annotations

import tomllib
from pathlib import Path

from pydantic import ConfigDict, Field, ValidationError

from overlap_calculator.exceptions import InputError
from overlap_calculator.models import ExcitedState, StrictBaseModel
from overlap_calculator.utils.errors import ErrorCode, format_error

# hc in eV*nm: lambda(nm) = HC_EV_NM / E(eV). CODATA 2018.
HC_EV_NM = 1239.841984


class BandOverride(StrictBaseModel):
    model_config = ConfigDict(extra="forbid")
    index: int = Field(ge=1)
    sigma_ev: float | None = Field(default=None, gt=0.0)
    reorganization_ev: float | None = Field(default=None, gt=0.0)


class Calibration(StrictBaseModel):
    """Pre-broadening calibration applied to TD-DFT excited states.

    - ``energy_a``, ``energy_b``: linear energy calibration ``E_cal = a*E + b``
      (E and b in eV). When ``(a, b) == (1.0, 0.0)`` the energy and wavelength of
      every state are left untouched (no recompute), so the identity calibration
      is bit-identical to running without ``--calibration``.
    - ``oscillator_alpha``: oscillator-strength scaling ``f_cal = alpha * f``.
    - ``bands``: optional per-transition width / reorganization-energy overrides.
    """

    model_config = ConfigDict(extra="forbid")
    energy_a: float = 1.0
    energy_b: float = 0.0
    oscillator_alpha: float = Field(default=1.0, gt=0.0)
    bands: list[BandOverride] = Field(default_factory=list)

    def is_identity(self) -> bool:
        return (
            self.energy_a == 1.0
            and self.energy_b == 0.0
            and self.oscillator_alpha == 1.0
            and not self.bands
        )

    def overrides_by_index(self) -> dict[int, BandOverride]:
        return {band.index: band for band in self.bands}


def load_calibration(path: Path) -> Calibration:
    """Load a calibration block from a TOML file.

    Expected schema (all sections optional)::

        [energy]
        a = 1.0
        b = 0.0

        [oscillator]
        alpha = 1.0

        [[band]]
        index = 1
        sigma_ev = 0.25
        reorganization_ev = 0.40
    """
    try:
        with path.open("rb") as handle:
            raw = tomllib.load(handle)
    except (OSError, tomllib.TOMLDecodeError) as exc:
        raise InputError(
            format_error(ErrorCode.INPUT, f"Failed to read calibration file: {path}")
        ) from exc

    energy = raw.get("energy", {})
    oscillator = raw.get("oscillator", {})
    bands_raw = raw.get("band", [])
    if not isinstance(bands_raw, list):
        raise InputError(
            format_error(ErrorCode.INPUT, "calibration 'band' must be an array of tables.")
        )

    try:
        return Calibration(
            energy_a=float(energy.get("a", 1.0)),
            energy_b=float(energy.get("b", 0.0)),
            oscillator_alpha=float(oscillator.get("alpha", 1.0)),
            bands=[BandOverride.model_validate(band) for band in bands_raw],
        )
    except (TypeError, ValueError, ValidationError) as exc:
        raise InputError(
            format_error(ErrorCode.INPUT, f"Invalid calibration file: {path} ({exc})")
        ) from exc


def apply_calibration(
    states: list[ExcitedState],
    calibration: Calibration,
) -> list[ExcitedState]:
    """Return calibrated excited states.

    Energy/wavelength are recomputed only when the linear energy map is
    non-identity; the wavelength is derived from the calibrated energy via
    ``lambda = HC_EV_NM / E_cal`` to stay consistent with the broadening grid.
    """
    if calibration.is_identity():
        return states

    a = calibration.energy_a
    b = calibration.energy_b
    alpha = calibration.oscillator_alpha
    recompute_energy = not (a == 1.0 and b == 0.0)

    calibrated: list[ExcitedState] = []
    for state in states:
        energy_ev = state.energy_ev
        wavelength_nm = state.wavelength_nm
        if recompute_energy:
            energy_ev = a * state.energy_ev + b
            if energy_ev <= 0.0:
                raise InputError(
                    format_error(
                        ErrorCode.INPUT,
                        (
                            f"Calibrated energy is non-positive for state {state.state} "
                            f"(E_cal={energy_ev:g} eV); check a/b."
                        ),
                    )
                )
            wavelength_nm = HC_EV_NM / energy_ev
        calibrated.append(
            ExcitedState(
                state=state.state,
                energy_ev=energy_ev,
                wavelength_nm=wavelength_nm,
                f=alpha * state.oscillator_strength,
            )
        )
    return calibrated
