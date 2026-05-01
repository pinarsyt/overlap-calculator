from pathlib import Path

from overlap_calculator.models import AnalysisInput
from overlap_calculator.services.analyzer import analyze_inputs


def test_analyze_inputs_skips_invalid_files(tmp_path: Path) -> None:
    valid = tmp_path / "valid.out"
    invalid = tmp_path / "invalid.out"
    valid.write_text(
        "\n".join(
            [
                " #P TD(B3LYP)/6-31G(d)",
                "",
                " Excited State   1:   Singlet-A    1.8647 eV  664.91 nm  f=0.3040",
            ]
        ),
        encoding="utf-8",
    )
    invalid.write_text(" #P TD(B3LYP)/6-31G(d)\n", encoding="utf-8")

    results, skipped_items = analyze_inputs(
        [
            AnalysisInput(
                input_type="theoretical",
                source_path=str(valid),
                sample_id="valid",
            ),
            AnalysisInput(
                input_type="theoretical",
                source_path=str(invalid),
                sample_id="invalid",
            ),
        ],
        sigma_ev=0.3,
        wl_min=200.0,
        wl_max=800.0,
        num_points=500,
        default_light_sources=["AM15G"],
    )

    assert len(results) == 2
    assert {item.broadening_method for item in results} == {"gaussian", "lorentzian"}
    assert {item.sample_id for item in results} == {"valid"}
    assert len(skipped_items) == 1
    assert skipped_items[0].sample_id == "invalid"
