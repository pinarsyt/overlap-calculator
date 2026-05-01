import logging
from pathlib import Path

from overlap_calculator.cli.main import _load_or_generate_inputs
from overlap_calculator.models import AnalysisInput, AnalysisSkip


def test_load_or_generate_inputs_uses_existing_input(monkeypatch, tmp_path: Path) -> None:
    input_file = tmp_path / "input.json"
    input_file.write_text("[]", encoding="utf-8")
    expected = [
        AnalysisInput(
            input_type="theoretical",
            source_path="td.out",
            sample_id="sample",
        )
    ]

    def fake_load(path: Path) -> list[AnalysisInput]:
        if path == input_file:
            return expected
        return []

    monkeypatch.setattr("overlap_calculator.cli.main.load_input_json", fake_load)

    pairs, skipped = _load_or_generate_inputs(input_file, logging.getLogger(__name__))

    assert pairs == expected
    assert skipped == []


def test_load_or_generate_inputs_generates_missing_input(monkeypatch, tmp_path: Path) -> None:
    input_dir = tmp_path / "input"
    input_dir.mkdir()
    input_file = input_dir / "input.json"
    files_dir = input_dir / "files"
    generated = [
        AnalysisInput(
            input_type="theoretical",
            source_path="td.out",
            sample_id="sample",
        )
    ]
    scan_skipped = [AnalysisSkip(sample_id="opt", td_path="opt.out", reason="skip")]
    calls: list[tuple[str, Path, Path] | tuple[str, Path]] = []

    def fake_generate(path: Path, out: Path) -> list[AnalysisInput]:
        calls.append(("generate", path, out))
        input_file.write_text("[]", encoding="utf-8")
        return generated

    def fake_load(path: Path) -> list[AnalysisInput]:
        calls.append(("load", path))
        return generated

    def fake_scan(path: Path) -> tuple[list[AnalysisInput], list[AnalysisSkip]]:
        return generated, scan_skipped

    monkeypatch.setattr("overlap_calculator.cli.main.generate_input_json", fake_generate)
    monkeypatch.setattr("overlap_calculator.cli.main.generate_inputs_with_skips", fake_scan)
    monkeypatch.setattr("overlap_calculator.cli.main.load_input_json", fake_load)

    pairs, skipped = _load_or_generate_inputs(input_file, logging.getLogger(__name__))

    assert pairs == generated
    assert skipped == scan_skipped
    assert calls == [
        ("generate", files_dir, input_file),
        ("load", input_file),
    ]
