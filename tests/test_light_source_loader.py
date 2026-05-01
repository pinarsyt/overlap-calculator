from pathlib import Path

import pytest

from overlap_calculator.calculations.spectrum import load_light_source
from overlap_calculator.exceptions import InputError


def test_load_light_source_builtin() -> None:
    wavelengths, intensity, name = load_light_source(None)
    assert len(wavelengths) > 2
    assert len(wavelengths) == len(intensity)
    assert name == "AM15G"


def test_load_light_source_csv_requires_columns(tmp_path: Path) -> None:
    bad = tmp_path / "bad.csv"
    bad.write_text("x,y\n1,2\n", encoding="utf-8")

    with pytest.raises(InputError):
        load_light_source(bad)
