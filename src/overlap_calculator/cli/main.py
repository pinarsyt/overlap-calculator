from __future__ import annotations

import logging
from pathlib import Path
from typing import Annotated, Optional

import click
import typer

from overlap_calculator import __version__
from overlap_calculator.config.settings import settings
from overlap_calculator.exceptions import OverlapCalculatorError
from overlap_calculator.models import AnalysisInput, AnalysisSkip
from overlap_calculator.services.analyzer import analyze_inputs, export_results, prepare_output_dir
from overlap_calculator.services.input_generator import (
    generate_input_json,
    generate_inputs_with_skips,
)
from overlap_calculator.services.input_loader import load_input_json
from overlap_calculator.utils.logging import format_log, setup_logging


class OrderedGroup(typer.core.TyperGroup):
    def list_commands(self, ctx: click.Context) -> list[str]:
        return list(self.commands.keys())


app = typer.Typer(
    add_completion=False,
    no_args_is_help=True,
    context_settings={"help_option_names": ["-h", "--help"]},
    cls=OrderedGroup,
)


@app.command("version")
def version() -> None:
    typer.echo(__version__)


@app.callback(invoke_without_command=True)
def main(ctx: typer.Context) -> None:
    if ctx.invoked_subcommand is None:
        typer.echo(ctx.get_help())
        raise typer.Exit()


def _load_or_generate_inputs(
    input_file: Path,
    logger: logging.Logger,
) -> tuple[list[AnalysisInput], list[AnalysisSkip]]:
    if input_file.exists():
        return load_input_json(input_file), []

    files_dir = input_file.parent / "files"
    logger.info(
        format_log(
            "generate",
            "input_json_missing",
            input_file=input_file,
            files_dir=files_dir,
        )
    )
    items, skipped_scan = generate_inputs_with_skips(files_dir)
    out_dir = input_file.parent
    out_dir.mkdir(parents=True, exist_ok=True)
    generate_input_json(files_dir, input_file)
    logger.info(format_log("generate", "input_json", path=input_file, items=len(items)))
    return load_input_json(input_file), skipped_scan


@app.command("analyze")
def analyze(
    input_file: Annotated[
        Path,
        typer.Option("--input", help="JSON file with mixed analysis inputs"),
    ] = Path("input/input.json"),
    out: Annotated[Path, typer.Option("--out", help="Output directory")] = Path("output"),
    sigma_ev: Annotated[
        float, typer.Option("--sigma-ev", help="Broadening sigma in eV (std dev; 0.1-0.4 typical)")
    ] = settings.sigma_ev,
    wl_min: Annotated[float, typer.Option("--wl-min", help="Wavelength minimum in nm")] = (
        settings.wavelength_min_nm
    ),
    wl_max: Annotated[float, typer.Option("--wl-max", help="Wavelength maximum in nm")] = (
        settings.wavelength_max_nm
    ),
    num_points: Annotated[int, typer.Option("--num-points", help="Spectrum grid size")] = (
        settings.wavelength_points
    ),
    concentration_m: Annotated[
        float,
        typer.Option("--concentration-m", help="Reference concentration in mol/L for Beer-Lambert"),
    ] = settings.reference_concentration_molar,
    path_cm: Annotated[
        float, typer.Option("--path-cm", help="Reference path length in cm for Beer-Lambert")
    ] = settings.reference_path_cm,
    default_light_sources: Annotated[
        str,
        typer.Option(
            "--default-light-sources",
            help=(
                "Comma-separated default light sources. "
                "Default: AM15G,LEDB4,LEDB2,LEDB3,CIEFL10"
            ),
        ),
    ] = settings.default_light_sources,
    light_source_file: Annotated[
        Optional[list[Path]],
        typer.Option(
            "--light-source-file",
            help="Optional custom light source CSV file(s). Repeat option for multiple files.",
        ),
    ] = None,
    log_level: Annotated[str, typer.Option("--log-level", help="Logging level")] = "INFO",
    log_format: Annotated[
        str, typer.Option("--log-format", help="Logging format (text/json)")
    ] = "text",
    plot_outputs: Annotated[
        bool,
        typer.Option("--plot-outputs/--no-plot-outputs", help="Generate TIFF plots"),
    ] = True,
    plot_dpi: Annotated[
        int,
        typer.Option("--plot-dpi", min=72, help="TIFF plot resolution in DPI"),
    ] = settings.plot_dpi,
    ranking_outputs: Annotated[
        bool,
        typer.Option(
            "--ranking-outputs/--no-ranking-outputs",
            help=(
                "Emit grouped ranking tables and bar charts for both "
                "absorbed_fraction and shape_overlap, in Gaussian and Lorentzian variants"
            ),
        ),
    ] = settings.ranking_outputs,
) -> None:
    setup_logging(log_level, log_format)
    logger = logging.getLogger(__name__)
    try:
        light_source_files = list(light_source_file or [])
        selected_defaults = [
            value.strip() for value in default_light_sources.split(",") if value.strip()
        ]
        logger.info(
            format_log(
                "analyze",
                "start",
                input=input_file,
                out=out,
                sigma_ev=sigma_ev,
                wl_min=wl_min,
                wl_max=wl_max,
                num_points=num_points,
                concentration_molar=concentration_m,
                path_cm=path_cm,
                default_light_sources=",".join(selected_defaults),
                custom_light_sources=len(light_source_files),
                broadening_comparison="enabled",
                plot_outputs=plot_outputs,
                plot_dpi=plot_dpi,
                ranking_outputs=ranking_outputs,
            )
        )
        items, skipped_scan = _load_or_generate_inputs(input_file, logger)
        prepare_output_dir(out, True)
        results, skipped_items = analyze_inputs(
            items,
            sigma_ev=sigma_ev,
            wl_min=wl_min,
            wl_max=wl_max,
            num_points=num_points,
            concentration_molar=concentration_m,
            path_cm=path_cm,
            default_light_sources=selected_defaults,
            custom_light_source_paths=light_source_files,
        )
        combined_skipped = [*skipped_scan, *skipped_items]
        export_results(
            results,
            out,
            make_plots=plot_outputs,
            skipped_items=combined_skipped,
            plot_dpi=plot_dpi,
            make_rankings=ranking_outputs,
        )
        if combined_skipped:
            logger.warning(
                format_log(
                    "analyze",
                    "completed_with_skips",
                    out=out,
                    produced=len(results),
                    skipped=len(combined_skipped),
                )
            )
        else:
            logger.info(format_log("analyze", "complete", out=out, produced=len(results)))
    except OverlapCalculatorError as exc:
        logger.error(format_log("analyze", "failed", error=str(exc)))
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        logger.exception(format_log("analyze", "unexpected_error", error=str(exc)))
        raise typer.Exit(code=1) from exc


@app.command("generate-input")
def generate_input(
    files_dir: Annotated[
        Path,
        typer.Option(
            "--files-dir",
            help="Directory with theoretical (.out) and/or experimental (.csv/.xlsx/.xls) files",
        ),
    ] = Path("input/files"),
    out: Annotated[Path, typer.Option("--out", help="Output JSON path")] = Path(
        "input/input.json"
    ),
    log_level: Annotated[str, typer.Option("--log-level", help="Logging level")] = "INFO",
    log_format: Annotated[
        str, typer.Option("--log-format", help="Logging format (text/json)")
    ] = "text",
) -> None:
    setup_logging(log_level, log_format)
    logger = logging.getLogger(__name__)
    try:
        logger.info(
            format_log(
                "generate",
                "start",
                files_dir=files_dir,
                out=out,
            )
        )
        items = generate_input_json(files_dir, out)
        logger.info(format_log("generate", "complete", out=out, items=len(items)))
    except OverlapCalculatorError as exc:
        logger.error(format_log("generate", "failed", error=str(exc)))
        raise typer.Exit(code=1) from exc
    except Exception as exc:
        logger.exception(format_log("generate", "unexpected_error", error=str(exc)))
        raise typer.Exit(code=1) from exc


if __name__ == "__main__":
    app()
