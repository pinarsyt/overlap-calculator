from __future__ import annotations

from enum import StrEnum


class ErrorCode(StrEnum):
    INPUT = "INPUT_ERROR"
    PARSE = "PARSE_ERROR"
    ANALYSIS = "ANALYSIS_ERROR"
    OUTPUT = "OUTPUT_ERROR"


def format_error(code: ErrorCode, message: str) -> str:
    return f"{code.value}: {message}"
