from __future__ import annotations

import json
import logging
from json import JSONDecodeError
from pathlib import Path

from overlap_calculator.exceptions import InputError
from overlap_calculator.models import AnalysisInput
from overlap_calculator.utils.errors import ErrorCode, format_error
from overlap_calculator.utils.logging import format_log

LOGGER = logging.getLogger(__name__)


def _resolve_path(base_dir: Path, path_value: str) -> Path:
    raw = Path(path_value)
    if raw.is_absolute():
        return raw

    candidate_base = (base_dir / raw).resolve()
    if candidate_base.exists():
        return candidate_base

    candidate_cwd = (Path.cwd() / raw).resolve()
    if candidate_cwd.exists():
        return candidate_cwd

    return candidate_base


def load_input_json(input_file: Path) -> list[AnalysisInput]:
    LOGGER.info(format_log("load", "input_json", path=input_file))
    if not input_file.exists():
        raise InputError(format_error(ErrorCode.INPUT, f"Input file not found: {input_file}"))

    try:
        raw = json.loads(input_file.read_text(encoding="utf-8-sig"))
    except (OSError, JSONDecodeError) as exc:
        raise InputError(
            format_error(ErrorCode.INPUT, f"Failed to read input file: {input_file}")
        ) from exc

    if not isinstance(raw, list):
        raise InputError(format_error(ErrorCode.INPUT, "Input file must contain a JSON array."))

    base_dir = input_file.parent
    items: list[AnalysisInput] = []
    for item in raw:
        data = dict(item)
        if "source_path" not in data and "td_path" in data:
            data["source_path"] = data["td_path"]
            data.setdefault("input_type", "theoretical")
        parsed = AnalysisInput.model_validate(data)
        source_path = _resolve_path(base_dir, parsed.source_path)
        if not source_path.exists():
            raise InputError(
                format_error(ErrorCode.INPUT, f"Input source file not found: {source_path}")
            )
        items.append(
            AnalysisInput(
                input_type=parsed.input_type,
                source_path=str(source_path),
                sample_id=parsed.sample_id,
                series_name=parsed.series_name,
                sheet_name=parsed.sheet_name,
            )
        )

    if not items:
        raise InputError(format_error(ErrorCode.INPUT, "Input file is empty."))

    LOGGER.info(format_log("load", "analysis_inputs", count=len(items), source=input_file))
    return items

