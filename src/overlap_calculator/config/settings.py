from __future__ import annotations

from pydantic import Field, field_validator
from pydantic_settings import BaseSettings, SettingsConfigDict

from overlap_calculator.exceptions import InputError
from overlap_calculator.utils.errors import ErrorCode, format_error
from overlap_calculator.utils.logging import VALID_LOG_LEVELS


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_prefix="GAUSS_", env_file=".env", extra="ignore")

    log_level: str = "INFO"
    log_format: str = "text"
    plot_outputs: bool = True
    plot_dpi: int = Field(default=400, ge=72)
    ranking_outputs: bool = True
    sigma_ev: float = Field(default=0.30, gt=0.0)
    wavelength_min_nm: float = Field(default=200.0, gt=0.0)
    wavelength_max_nm: float = Field(default=800.0, gt=0.0)
    wavelength_points: int = Field(default=10000, ge=50)
    reference_concentration_molar: float = Field(default=1.0e-5, gt=0.0)
    reference_path_cm: float = Field(default=1.0, gt=0.0)
    default_light_sources: str = "AM15G,LEDB4,LEDB2,LEDB3,CIEFL10"
    upload_max_mb: int = Field(default=50, ge=1)
    upload_allowed_exts: tuple[str, ...] = (".out", ".log", ".csv", ".xlsx", ".xls")

    @field_validator("log_level")
    @classmethod
    def validate_log_level(cls, value: str) -> str:
        normalized = value.upper()
        if normalized not in VALID_LOG_LEVELS:
            allowed = ", ".join(sorted(VALID_LOG_LEVELS))
            raise InputError(
                format_error(ErrorCode.INPUT, f"Invalid log level: {value}. Allowed: {allowed}")
            )
        return normalized

    @field_validator("log_format")
    @classmethod
    def validate_log_format(cls, value: str) -> str:
        normalized = value.lower()
        if normalized not in {"text", "json"}:
            raise InputError(
                format_error(ErrorCode.INPUT, f"Invalid log format: {value}. Allowed: text, json")
            )
        return normalized

    @field_validator("upload_allowed_exts", mode="before")
    @classmethod
    def normalize_extensions(cls, value: object) -> tuple[str, ...]:
        if isinstance(value, str):
            parts = [p.strip() for p in value.split(",") if p.strip()]
        elif isinstance(value, list | tuple | set):
            parts = [str(p).strip() for p in value if str(p).strip()]
        else:
            parts = []
        normalized = []
        for ext in parts:
            ext = ext.lower()
            if not ext.startswith("."):
                ext = f".{ext}"
            normalized.append(ext)
        if not normalized:
            raise InputError(format_error(ErrorCode.INPUT, "Upload extensions cannot be empty."))
        return tuple(normalized)


settings = Settings()
