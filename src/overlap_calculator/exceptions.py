from __future__ import annotations


class OverlapCalculatorError(Exception):
    """Base exception for all analyzer errors."""


class InputError(OverlapCalculatorError):
    """Raised when input data or files are invalid or missing."""


class ParseError(OverlapCalculatorError):
    """Raised when parsing of Gaussian outputs fails."""


class AnalysisError(OverlapCalculatorError):
    """Raised when metric computation or aggregation fails."""


class OutputError(OverlapCalculatorError):
    """Raised when exporting results fails."""

