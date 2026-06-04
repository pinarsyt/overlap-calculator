from __future__ import annotations

import io
import json
import logging
import re
import tempfile
import time
import uuid
import zipfile
from collections.abc import Mapping
from pathlib import Path
from typing import cast

from flask import Flask, Response, g, jsonify, request, send_file
from werkzeug.datastructures import FileStorage

from overlap_calculator.config.settings import settings
from overlap_calculator.exceptions import (
    AnalysisError,
    InputError,
    OutputError,
    OverlapCalculatorError,
)
from overlap_calculator.models import AnalysisInput, AnalysisSkip
from overlap_calculator.services.analyzer import analyze_inputs, export_results, prepare_output_dir
from overlap_calculator.services.input_generator import generate_inputs_with_skips
from overlap_calculator.services.provenance import build_run_manifest, write_run_manifest
from overlap_calculator.utils.errors import ErrorCode, format_error
from overlap_calculator.utils.logging import format_log, set_request_id, setup_logging

app = Flask(__name__)
setup_logging(settings.log_level, settings.log_format)
LOGGER = logging.getLogger(__name__)


@app.before_request
def assign_request_id() -> None:
    request_id = uuid.uuid4().hex
    g.request_id = request_id
    set_request_id(request_id)


@app.after_request
def attach_request_id(response: Response) -> Response:
    response.headers["X-Request-ID"] = g.get("request_id", "")
    return response


@app.get("/health")
def health() -> tuple[Response, int]:
    return jsonify({"status": "ok"}), 200


@app.errorhandler(Exception)
def handle_exception(exc: Exception) -> tuple[Response, int]:
    LOGGER.exception(
        format_log("request", "unhandled_exception", request_id=g.get("request_id"), error=str(exc))
    )
    return (
        jsonify({"error": "Internal server error", "request_id": g.get("request_id")}),
        500,
    )


def _sanitize_filename(name: str) -> str:
    cleaned = re.sub(r"[^A-Za-z0-9._-]", "_", name)
    return cleaned or "upload.bin"


def _parse_bulk_files() -> list[FileStorage]:
    files = request.files.getlist("files")
    return [item for item in files if item and item.filename]


def _parse_light_source_files() -> list[FileStorage]:
    uploaded = request.files.getlist("light_source_files")
    legacy_single = request.files.get("light_source_csv")
    items = [item for item in uploaded if item and item.filename]
    if legacy_single and legacy_single.filename:
        items.append(legacy_single)
    return items


def _validate_upload(
    file_storage: FileStorage,
    index: int,
    kind: str,
    allowed_exts: tuple[str, ...] | None = None,
) -> None:
    filename = file_storage.filename or ""
    ext = Path(filename).suffix.lower()
    valid_exts = allowed_exts or settings.upload_allowed_exts
    if ext not in valid_exts:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                (
                    f"Invalid file extension for item {index} ({kind}). "
                    f"Allowed: {valid_exts}"
                ),
            )
        )
    size_bytes: int | None = None
    if file_storage.content_length is not None:
        size_bytes = file_storage.content_length
    else:
        try:
            stream = file_storage.stream
            pos = stream.tell()
            stream.seek(0, io.SEEK_END)
            size_bytes = stream.tell()
            stream.seek(pos)
        except Exception:
            size_bytes = None
    if size_bytes is not None and size_bytes > settings.upload_max_mb * 1024 * 1024:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                f"File too large for item {index} ({kind}). Max: {settings.upload_max_mb} MB",
            )
        )


def _generate_inputs_from_bulk(
    files: list[FileStorage],
    files_dir: Path,
    sheet_overrides_by_filename: Mapping[str, str] | None = None,
) -> tuple[list[AnalysisInput], list[AnalysisSkip]]:
    request_id = g.get("request_id", uuid.uuid4().hex)
    files_dir.mkdir(parents=True, exist_ok=True)
    LOGGER.info(
        format_log(
            "upload",
            "start",
            request_id=request_id,
            files=len(files),
            files_dir=files_dir,
        )
    )

    saved_path_to_sheet: dict[Path, str] = {}
    for idx, upload in enumerate(files):
        _validate_upload(upload, idx, "files")
        original_name = upload.filename or f"upload_{idx}"
        safe_name = _sanitize_filename(original_name)
        target = files_dir / f"{idx}_{safe_name}"
        try:
            upload.save(target)
        except OSError as exc:
            LOGGER.error(format_log("upload", "save_failed", index=idx, error=str(exc)))
            raise OutputError(
                format_error(ErrorCode.OUTPUT, "Failed to save uploaded files.")
            ) from exc
        if sheet_overrides_by_filename:
            override = sheet_overrides_by_filename.get(original_name)
            if override is not None:
                saved_path_to_sheet[target] = override

    items, skipped_scan = generate_inputs_with_skips(
        files_dir,
        sheet_overrides=saved_path_to_sheet or None,
    )
    LOGGER.info(format_log("upload", "complete", request_id=request_id, items=len(items)))
    return items, skipped_scan


def _save_custom_light_sources(files: list[FileStorage], target_dir: Path) -> list[Path]:
    paths: list[Path] = []
    for idx, upload in enumerate(files):
        _validate_upload(upload, idx, "light_source_files", allowed_exts=(".csv",))
        safe_name = _sanitize_filename(upload.filename or f"light_source_{idx}.csv")
        out_path = target_dir / f"light_source_{safe_name}"
        upload.save(out_path)
        paths.append(out_path)
    return paths


def _get_bool(form: Mapping[str, str], key: str, default: bool) -> bool:
    return form.get(key, str(default)).strip().lower() == "true"


def _get_float(form: Mapping[str, str], key: str, default: float) -> float:
    raw = form.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return float(raw)
    except ValueError as exc:
        raise InputError(format_error(ErrorCode.INPUT, f"Invalid float for {key}: {raw}")) from exc


def _get_int(form: Mapping[str, str], key: str, default: int) -> int:
    raw = form.get(key)
    if raw is None or raw.strip() == "":
        return default
    try:
        return int(raw)
    except ValueError as exc:
        raise InputError(
            format_error(ErrorCode.INPUT, f"Invalid integer for {key}: {raw}")
        ) from exc


def _parse_sheet_overrides(raw: str | None) -> dict[str, str] | None:
    if raw is None or raw.strip() == "":
        return None
    try:
        parsed = json.loads(raw)
    except ValueError as exc:
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                "sheet_overrides must be a JSON object mapping filename to sheet name.",
            )
        ) from exc
    if not isinstance(parsed, dict):
        raise InputError(
            format_error(
                ErrorCode.INPUT,
                "sheet_overrides must be a JSON object, not a list or scalar.",
            )
        )
    overrides: dict[str, str] = {}
    for key, value in parsed.items():
        if not isinstance(key, str) or not key:
            raise InputError(
                format_error(
                    ErrorCode.INPUT,
                    "sheet_overrides keys must be non-empty filename strings.",
                )
            )
        if not isinstance(value, str) or not value:
            raise InputError(
                format_error(
                    ErrorCode.INPUT,
                    f"sheet_overrides['{key}'] must be a non-empty sheet-name string.",
                )
            )
        overrides[key] = value
    return overrides or None


@app.route("/analyze", methods=["POST"])
def analyze_route() -> tuple[Response, int]:
    started = time.perf_counter()
    form: Mapping[str, str] = cast(Mapping[str, str], request.form)
    plot_outputs = _get_bool(form, "plot_outputs", settings.plot_outputs)
    sigma_ev = _get_float(form, "sigma_ev", settings.sigma_ev)
    wl_min = _get_float(form, "wl_min", settings.wavelength_min_nm)
    wl_max = _get_float(form, "wl_max", settings.wavelength_max_nm)
    num_points = _get_int(form, "num_points", settings.wavelength_points)
    plot_dpi = _get_int(form, "plot_dpi", settings.plot_dpi)
    if plot_dpi < 72:
        raise InputError(format_error(ErrorCode.INPUT, "plot_dpi must be >= 72."))
    ranking_outputs = _get_bool(form, "ranking_outputs", settings.ranking_outputs)
    concentration_m = _get_float(form, "concentration_m", settings.reference_concentration_molar)
    path_cm = _get_float(form, "path_cm", settings.reference_path_cm)
    prefactor_mode = form.get("prefactor_mode", settings.prefactor_mode)
    sigma_mode = form.get("sigma_mode", settings.sigma_mode)
    reorganization_ev = _get_float(form, "reorganization_ev", settings.reorganization_ev)
    temperature_k = _get_float(form, "temperature_k", settings.temperature_k)
    default_light_sources_raw = form.get("default_light_sources", settings.default_light_sources)
    default_light_sources = [v.strip() for v in default_light_sources_raw.split(",") if v.strip()]
    sheet_overrides = _parse_sheet_overrides(form.get("sheet_overrides"))

    bulk_files = _parse_bulk_files()
    custom_light_source_uploads = _parse_light_source_files()
    LOGGER.info(
        format_log(
            "request",
            "analyze",
            request_id=g.get("request_id"),
            sigma_ev=sigma_ev,
            wl_min=wl_min,
            wl_max=wl_max,
            num_points=num_points,
            concentration_molar=concentration_m,
            path_cm=path_cm,
            default_light_sources=",".join(default_light_sources),
            custom_light_sources=len(custom_light_source_uploads),
            broadening_comparison="enabled",
            plot_outputs=plot_outputs,
            plot_dpi=plot_dpi,
            ranking_outputs=ranking_outputs,
            bulk_upload=len(bulk_files),
            sheet_overrides=len(sheet_overrides) if sheet_overrides else 0,
        )
    )
    try:
        if not bulk_files:
            return (
                jsonify(
                    {
                        "error": "No files uploaded. Use multipart key 'files'.",
                        "request_id": g.get("request_id"),
                    }
                ),
                400,
            )

        with tempfile.TemporaryDirectory(prefix="overlap-calculator_") as tmp_root:
            tmp_path = Path(tmp_root)
            files_dir = tmp_path / "files"
            out_dir = tmp_path / "output"
            items, skipped_scan = _generate_inputs_from_bulk(
                bulk_files,
                files_dir,
                sheet_overrides_by_filename=sheet_overrides,
            )
            if not items:
                return jsonify(
                    {
                        "error": "No analyzable theoretical/experimental inputs were found.",
                        "request_id": g.get("request_id"),
                    }
                ), 400

            custom_light_source_paths = _save_custom_light_sources(
                custom_light_source_uploads,
                tmp_path,
            )

            try:
                prepare_output_dir(out_dir, True)
                results, skipped_items = analyze_inputs(
                    items,
                    sigma_ev=sigma_ev,
                    wl_min=wl_min,
                    wl_max=wl_max,
                    num_points=num_points,
                    concentration_molar=concentration_m,
                    path_cm=path_cm,
                    default_light_sources=default_light_sources,
                    custom_light_source_paths=custom_light_source_paths,
                    prefactor_mode=prefactor_mode,
                    sigma_mode=sigma_mode,
                    reorganization_ev=reorganization_ev,
                    temperature_k=temperature_k,
                )
                combined_skipped = [*skipped_scan, *skipped_items]
                export_results(
                    results,
                    out_dir,
                    make_plots=plot_outputs,
                    skipped_items=combined_skipped,
                    plot_dpi=plot_dpi,
                    make_rankings=ranking_outputs,
                )
                manifest = build_run_manifest(
                    results=results,
                    items=items,
                    parameters={
                        "sigma_ev": sigma_ev,
                        "prefactor_mode": prefactor_mode,
                        "sigma_mode": sigma_mode,
                        "reorganization_ev": reorganization_ev,
                        "temperature_k": temperature_k,
                        "wavelength_min_nm": wl_min,
                        "wavelength_max_nm": wl_max,
                        "num_points": num_points,
                        "concentration_molar": concentration_m,
                        "path_cm": path_cm,
                        "default_light_sources": default_light_sources,
                        "custom_light_source_count": len(custom_light_source_paths),
                        "calibration": None,
                    },
                    skipped_items=combined_skipped,
                    light_source_names=sorted(
                        {result.light_source_name for result in results}
                    ),
                )
                write_run_manifest(out_dir, manifest)
                elapsed_s = time.perf_counter() - started
                LOGGER.info(
                    format_log(
                        "request",
                        "complete",
                        request_id=g.get("request_id"),
                        produced=len(results),
                        skipped=len(combined_skipped),
                        out_dir=out_dir,
                        elapsed_s=round(elapsed_s, 3),
                    )
                )
            except (InputError, AnalysisError, OutputError, OverlapCalculatorError) as exc:
                LOGGER.error(
                    format_log("request", "failed", request_id=g.get("request_id"), error=str(exc))
                )
                status = 400
                if isinstance(exc, AnalysisError):
                    status = 422
                elif isinstance(exc, OutputError):
                    status = 500
                return jsonify({"error": str(exc), "request_id": g.get("request_id")}), status

            zip_buffer = io.BytesIO()
            with zipfile.ZipFile(zip_buffer, "w", compression=zipfile.ZIP_DEFLATED) as zip_file:
                for file_path in out_dir.rglob("*"):
                    if file_path.is_file():
                        zip_file.write(file_path, arcname=file_path.relative_to(out_dir))
            zip_buffer.seek(0)

            response = send_file(
                zip_buffer,
                mimetype="application/zip",
                as_attachment=True,
                download_name="analysis_outputs.zip",
            )
            response.headers["X-Request-ID"] = g.get("request_id", "")
            return response, 200
    except (InputError, OverlapCalculatorError) as exc:
        LOGGER.warning(
            format_log(
                "request",
                "validation_failed",
                request_id=g.get("request_id"),
                error=str(exc),
            )
        )
        return jsonify({"error": str(exc), "request_id": g.get("request_id")}), 400
    except Exception as exc:
        LOGGER.exception(
            format_log(
                "request",
                "unhandled_error",
                request_id=g.get("request_id"),
                error=str(exc),
            )
        )
        return jsonify({"error": "Internal server error", "request_id": g.get("request_id")}), 500


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=8000)
