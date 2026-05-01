from __future__ import annotations

import pytest

from overlap_calculator.api.app import _parse_sheet_overrides
from overlap_calculator.exceptions import InputError


def test_parse_sheet_overrides_returns_none_for_missing_or_empty() -> None:
    assert _parse_sheet_overrides(None) is None
    assert _parse_sheet_overrides("") is None
    assert _parse_sheet_overrides("   ") is None


def test_parse_sheet_overrides_returns_none_for_empty_object() -> None:
    assert _parse_sheet_overrides("{}") is None


def test_parse_sheet_overrides_accepts_valid_mapping() -> None:
    parsed = _parse_sheet_overrides('{"dye_panel.xlsx": "raw", "B1_meas.xlsx": "sheet2"}')
    assert parsed == {"dye_panel.xlsx": "raw", "B1_meas.xlsx": "sheet2"}


def test_parse_sheet_overrides_rejects_malformed_json() -> None:
    with pytest.raises(InputError, match="JSON object"):
        _parse_sheet_overrides("{not json}")


def test_parse_sheet_overrides_rejects_non_object_json() -> None:
    with pytest.raises(InputError, match="JSON object"):
        _parse_sheet_overrides('["dye_panel.xlsx", "raw"]')


def test_parse_sheet_overrides_rejects_empty_key() -> None:
    with pytest.raises(InputError, match="non-empty filename"):
        _parse_sheet_overrides('{"": "raw"}')


def test_parse_sheet_overrides_rejects_non_string_value() -> None:
    with pytest.raises(InputError, match="non-empty sheet-name"):
        _parse_sheet_overrides('{"dye_panel.xlsx": 3}')


def test_parse_sheet_overrides_rejects_empty_value() -> None:
    with pytest.raises(InputError, match="non-empty sheet-name"):
        _parse_sheet_overrides('{"dye_panel.xlsx": ""}')
