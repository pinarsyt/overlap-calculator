from pathlib import Path

from overlap_calculator.models import ExcitedState, RunResult, TDResult
from overlap_calculator.services.export import _sample_sort_key, export_results


def _build_result(
    sample_id: str,
    method: str,
    *,
    light_source_name: str = "AM15G",
    absorbed_fraction: float = 0.088,
    shape_overlap_value: float | None = None,
) -> RunResult:
    if shape_overlap_value is None:
        shape_overlap_value = 0.53 if method == "gaussian" else 0.49
    return RunResult(
        source_type="theoretical",
        sample_id=sample_id,
        source_path=f"{sample_id}.out",
        td=TDResult(
            excited_states=[ExcitedState(state=1, energy_ev=2.10, wavelength_nm=590.4, f=0.31)],
            source=f"{sample_id}.out",
        ),
        lambda_max_nm=590.4,
        molar_absorptivity_max=3.2e4,
        absorptance_max=0.27,
        absorbed_flux=absorbed_fraction * 1000.0,
        absorbed_flux_unit="W m^-2",
        light_flux_total=1000.0,
        absorbed_fraction=absorbed_fraction,
        shape_overlap=shape_overlap_value,
        absorption_unit="absorptance (Beer-Lambert at c=1e-05 M, L=1 cm)",
        light_source_unit="W m^-2 nm^-1",
        broadening_method=method,
        sigma_ev=0.3,
        reference_concentration_molar=1.0e-5,
        reference_path_cm=1.0,
        light_source_name=light_source_name,
        wavelengths_nm=[200.0, 300.0, 400.0],
        absorptance=[0.1, 0.4, 0.2],
        molar_absorptivity=[1.0e4, 3.0e4, 2.0e4],
        light_intensity=[0.2, 0.5, 0.3],
        timings_ms={"total_sample_ms": 10.0},
    )


def _pair(sample_id: str) -> list[RunResult]:
    return [_build_result(sample_id, "gaussian"), _build_result(sample_id, "lorentzian")]


def test_export_results_writes_wide_format_tables_and_combined_plots(tmp_path: Path) -> None:
    export_results(_pair("sample-1"), tmp_path, make_plots=True, plot_dpi=120)

    assert (tmp_path / "tables" / "results.csv").exists()
    assert (tmp_path / "tables" / "results.json").exists()
    assert (tmp_path / "tables" / "results.xlsx").exists()
    assert (tmp_path / "tables" / "results_timings.xlsx").exists()
    assert (tmp_path / "tables" / "descriptor_summary.xlsx").exists()
    assert (tmp_path / "plots" / "absorption" / "sample-1__absolute.tiff").exists()
    assert (tmp_path / "plots" / "absorption" / "sample-1__normalized.tiff").exists()
    assert (tmp_path / "plots" / "light_source" / "AM15G.tiff").exists()
    assert (tmp_path / "plots" / "overlap" / "sample-1__AM15G__combined__absolute.tiff").exists()
    assert (tmp_path / "plots" / "overlap" / "sample-1__AM15G__combined__normalized.tiff").exists()
    assert (tmp_path / "plots" / "overlap" / "sample-1__AM15G__gaussian__absolute.tiff").exists()
    assert (tmp_path / "plots" / "overlap" / "sample-1__AM15G__gaussian__normalized.tiff").exists()
    assert (tmp_path / "plots" / "overlap" / "sample-1__AM15G__lorentzian__absolute.tiff").exists()
    assert (
        tmp_path / "plots" / "overlap" / "sample-1__AM15G__lorentzian__normalized.tiff"
    ).exists()


def test_export_results_passes_plot_dpi_to_tiff_writer(monkeypatch, tmp_path: Path) -> None:
    from matplotlib.figure import Figure

    captured: list[int] = []
    original_savefig = Figure.savefig

    def spy_savefig(self: Figure, *args: object, **kwargs: object) -> None:
        captured.append(int(kwargs["dpi"]))
        original_savefig(self, *args, **kwargs)

    monkeypatch.setattr(Figure, "savefig", spy_savefig)

    export_results(_pair("sample-1"), tmp_path, make_plots=True, plot_dpi=123)

    assert captured
    assert set(captured) == {123}


def test_wide_results_row_contains_both_methods(tmp_path: Path) -> None:
    import pandas as pd

    export_results(_pair("sample-1"), tmp_path, make_plots=False)
    df = pd.read_csv(tmp_path / "tables" / "results.csv")
    assert len(df) == 1
    assert "gaussian_absorbed_fraction" in df.columns
    assert "lorentzian_absorbed_fraction" in df.columns
    assert "delta_absorbed_fraction" in df.columns


def test_export_results_writes_overlay_for_multiple_samples(tmp_path: Path) -> None:
    export_results(
        [*_pair("sample-1"), *_pair("sample-2")],
        tmp_path,
        make_plots=True,
        plot_dpi=120,
    )

    assert (tmp_path / "tables" / "results.xlsx").exists()
    assert (tmp_path / "tables" / "descriptor_summary.csv").exists()
    assert (
        tmp_path / "plots" / "overlays" / "absorptance_overlay__gaussian__absolute.tiff"
    ).exists()
    assert (
        tmp_path / "plots" / "overlays" / "absorptance_overlay__gaussian__normalized.tiff"
    ).exists()


def test_sample_sort_key_orders_numeric_suffixes_naturally() -> None:
    sample_ids = ["1", "10", "2", "sample-11", "sample-2"]
    assert sorted(sample_ids, key=_sample_sort_key) == ["1", "2", "10", "sample-2", "sample-11"]


def _ranking_results() -> list[RunResult]:
    spec = [
        ("alpha", "AM15G", 0.40, 0.55),
        ("alpha", "LEDB4", 0.18, 0.62),
        ("beta", "AM15G", 0.32, 0.48),
        ("beta", "LEDB4", 0.41, 0.71),
    ]
    results: list[RunResult] = []
    for sample, light, gauss_frac, gauss_shape in spec:
        results.append(
            _build_result(
                sample,
                "gaussian",
                light_source_name=light,
                absorbed_fraction=gauss_frac,
                shape_overlap_value=gauss_shape,
            )
        )
        results.append(
            _build_result(
                sample,
                "lorentzian",
                light_source_name=light,
                absorbed_fraction=gauss_frac * 0.95,
                shape_overlap_value=gauss_shape * 0.97,
            )
        )
    return results


def test_export_results_writes_ranking_tables_for_all_metrics(tmp_path: Path) -> None:
    import pandas as pd

    export_results(_ranking_results(), tmp_path, make_plots=False)

    metrics = (
        "gaussian_absorbed_fraction",
        "lorentzian_absorbed_fraction",
        "gaussian_shape_overlap",
        "lorentzian_shape_overlap",
    )
    for metric in metrics:
        for grouping in ("by_light_source", "by_sample"):
            stem = f"ranking_{grouping}__{metric}"
            for ext in ("csv", "json", "xlsx"):
                assert (tmp_path / "tables" / f"{stem}.{ext}").exists(), f"missing {stem}.{ext}"

    df = pd.read_csv(
        tmp_path / "tables" / "ranking_by_light_source__gaussian_absorbed_fraction.csv"
    )
    am15g = df[df["light_source_name"] == "AM15G"].reset_index(drop=True)
    assert list(am15g["sample_id"]) == ["alpha", "beta"]
    assert list(am15g["rank"]) == [1, 2]
    ledb4 = df[df["light_source_name"] == "LEDB4"].reset_index(drop=True)
    assert list(ledb4["sample_id"]) == ["beta", "alpha"]
    assert list(ledb4["rank"]) == [1, 2]

    df_sample = pd.read_csv(
        tmp_path / "tables" / "ranking_by_sample__gaussian_shape_overlap.csv"
    )
    alpha = df_sample[df_sample["sample_id"] == "alpha"].reset_index(drop=True)
    assert list(alpha["light_source_name"]) == ["LEDB4", "AM15G"]
    assert list(alpha["rank"]) == [1, 2]


def test_export_results_writes_ranking_plots_per_metric(tmp_path: Path) -> None:
    export_results(_ranking_results(), tmp_path, make_plots=True, plot_dpi=120)

    metrics = (
        "gaussian_absorbed_fraction",
        "lorentzian_absorbed_fraction",
        "gaussian_shape_overlap",
        "lorentzian_shape_overlap",
    )
    for metric in metrics:
        light_dir = tmp_path / "plots" / "ranking" / "by_light_source" / metric
        sample_dir = tmp_path / "plots" / "ranking" / "by_sample" / metric
        assert (light_dir / "AM15G.tiff").exists()
        assert (light_dir / "LEDB4.tiff").exists()
        assert (sample_dir / "alpha.tiff").exists()
        assert (sample_dir / "beta.tiff").exists()


def test_export_results_skips_rankings_when_disabled(tmp_path: Path) -> None:
    export_results(
        _ranking_results(),
        tmp_path,
        make_plots=True,
        plot_dpi=120,
        make_rankings=False,
    )

    tables_dir = tmp_path / "tables"
    assert (tables_dir / "results.csv").exists()
    assert not list(tables_dir.glob("ranking_by_*"))
    ranking_plots = tmp_path / "plots" / "ranking"
    assert not ranking_plots.exists()
