from __future__ import annotations

import logging
import re
from pathlib import Path

from overlap_calculator.exceptions import ParseError
from overlap_calculator.models import ExcitedState, TDResult
from overlap_calculator.utils.errors import ErrorCode, format_error

LOGGER = logging.getLogger(__name__)

EXCITED_PATTERN = re.compile(
    r"^Excited State\s+(\d+):\s+\S+\s+([0-9.]+)\s+eV\s+([0-9.]+)\s+nm\s+f=([0-9.]+)"
)
ROUTE_METHOD_PATTERN = re.compile(r"(?i)([a-z0-9+\-]+/[a-z0-9(),+\-]+)")
ROUTE_SOLVENT_PATTERN = re.compile(r"(?i)\bscrf=\([^)]+\)")
CHK_PATTERN = re.compile(r"(?i)^\s*%chk\s*=\s*(\S+)")


def extract_chk_name(path: Path) -> str | None:
    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                match = CHK_PATTERN.match(line)
                if match:
                    name = Path(match.group(1)).name
                    if name.lower().endswith(".chk"):
                        name = name[:-4]
                    return name or None
    except OSError:
        return None
    return None


def parse_td_output(path: Path) -> TDResult:
    LOGGER.info("Parsing TD-DFT output: %s", path)
    excited_states: list[ExcitedState] = []
    method_basis: str | None = None
    solvent: str | None = None
    route_lines: list[str] = []
    collecting_route = False
    route_captured = False

    try:
        with path.open("r", encoding="utf-8", errors="ignore") as handle:
            for line in handle:
                if not route_captured:
                    if line.lstrip().startswith("#"):
                        collecting_route = True
                        route_lines.append(line.strip())
                    elif collecting_route:
                        if line.strip() == "":
                            collecting_route = False
                            route_captured = True
                        else:
                            route_lines.append(line.strip())

                match = EXCITED_PATTERN.match(line.strip())
                if not match:
                    continue
                state, energy, wavelength, osc = match.groups()
                wavelength_value = float(wavelength)
                oscillator_value = float(osc)
                if wavelength_value <= 0:
                    raise ParseError(
                        format_error(
                            ErrorCode.PARSE,
                            f"Invalid wavelength ({wavelength_value}) in TD-DFT output.",
                        )
                    )
                if oscillator_value < 0:
                    raise ParseError(
                        format_error(
                            ErrorCode.PARSE,
                            f"Invalid oscillator strength ({oscillator_value}) in TD-DFT output.",
                        )
                    )
                excited_states.append(
                    ExcitedState(
                        state=int(state),
                        energy_ev=float(energy),
                        wavelength_nm=wavelength_value,
                        f=oscillator_value,
                    )
                )
    except OSError as exc:
        raise ParseError(
            format_error(ErrorCode.PARSE, f"Failed to read TD-DFT output: {path}")
        ) from exc

    if route_lines and (method_basis is None or solvent is None):
        route_text = " ".join(route_lines).lower()
        if method_basis is None:
            route_match = ROUTE_METHOD_PATTERN.search(route_text)
            if route_match:
                method_basis = route_match.group(1)
        if solvent is None:
            solvent_match = ROUTE_SOLVENT_PATTERN.search(route_text)
            if solvent_match:
                solvent = solvent_match.group(0)

    if not excited_states:
        raise ParseError(format_error(ErrorCode.PARSE, "No excited states found in TD-DFT output."))

    LOGGER.debug("TD-DFT parse complete: %d states", len(excited_states))
    return TDResult(
        excited_states=excited_states,
        source=str(path),
        method_basis=method_basis,
        solvent=solvent,
    )


