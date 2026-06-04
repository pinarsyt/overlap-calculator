from __future__ import annotations

from typing import Literal, Protocol

from pydantic import BaseModel, ConfigDict, Field


class CcReadIO(Protocol):
    def ccread(self, filename: str) -> object: ...


class StrictBaseModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class ExcitedState(StrictBaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True, populate_by_name=True)
    state: int
    energy_ev: float
    wavelength_nm: float
    oscillator_strength: float = Field(alias="f")


class TDResult(StrictBaseModel):
    excited_states: list[ExcitedState]
    source: str
    method_basis: str | None = None
    solvent: str | None = None


class RunResult(StrictBaseModel):
    source_type: Literal["theoretical", "experimental"]
    sample_id: str
    source_path: str
    td: TDResult | None = None
    lambda_max_nm: float
    molar_absorptivity_max: float
    absorptance_max: float
    absorbed_flux: float
    absorbed_flux_unit: str
    light_flux_total: float
    absorbed_fraction: float
    shape_overlap: float
    absorption_unit: str
    light_source_unit: str
    broadening_method: str
    sigma_ev: float
    prefactor_mode: str = "constant"
    sigma_mode: str = "fixed"
    software_version: str = ""
    reference_concentration_molar: float
    reference_path_cm: float
    light_source_name: str
    wavelengths_nm: list[float]
    absorptance: list[float]
    molar_absorptivity: list[float]
    light_intensity: list[float]
    timings_ms: dict[str, float] = Field(default_factory=dict)


class AnalysisSkip(StrictBaseModel):
    sample_id: str
    td_path: str
    reason: str


class AnalysisInput(StrictBaseModel):
    input_type: Literal["theoretical", "experimental"] = "theoretical"
    source_path: str
    sample_id: str | None = None
    series_name: str | None = None
    sheet_name: str | None = None
