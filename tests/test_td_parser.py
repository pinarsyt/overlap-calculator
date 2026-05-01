import pytest

from overlap_calculator.exceptions import ParseError
from overlap_calculator.parsers.td import extract_chk_name, parse_td_output


def test_parse_td_output(tmp_path):
    td_path = tmp_path / "td-dft.out"
    td_path.write_text(
        "\n".join(
            [
                " #P TD(B3LYP)/6-31G(d)",
                "",
                " Excited State   1:   Singlet-A    1.8647 eV  664.91 nm  f=0.3040",
                "",
            ]
        ),
        encoding="utf-8",
    )
    result = parse_td_output(td_path)
    first = result.excited_states[0]
    assert first.state == 1
    assert round(first.energy_ev, 4) == 1.8647
    assert round(first.wavelength_nm, 2) == 664.91
    assert round(first.oscillator_strength, 4) == 0.3040


def test_parse_td_output_rejects_negative_oscillator_strength(tmp_path):
    td_path = tmp_path / "td-dft.out"
    td_path.write_text(
        " Excited State   1:   Singlet-A    1.8647 eV  664.91 nm  f=-0.3040",
        encoding="utf-8",
    )

    with pytest.raises(ParseError):
        parse_td_output(td_path)


def test_extract_chk_name_strips_extension(tmp_path):
    path = tmp_path / "job.out"
    path.write_text("%chk=B1_td.chk\n# td=(nstates=10)\n", encoding="utf-8")
    assert extract_chk_name(path) == "B1_td"


def test_extract_chk_name_handles_directory_and_case(tmp_path):
    path = tmp_path / "job.out"
    path.write_text("   %Chk = /scratch/run/B9_TD.CHK\n", encoding="utf-8")
    assert extract_chk_name(path) == "B9_TD"


def test_extract_chk_name_returns_none_when_absent(tmp_path):
    path = tmp_path / "job.out"
    path.write_text("# td=(nstates=10) b3lyp/6-31g(d)\n", encoding="utf-8")
    assert extract_chk_name(path) is None


