from __future__ import annotations

import hashlib
import json
import logging
import os
import subprocess
from datetime import UTC, datetime
from pathlib import Path
from typing import Any

from overlap_calculator import __version__
from overlap_calculator.exceptions import OutputError
from overlap_calculator.models import AnalysisInput, AnalysisSkip, RunResult
from overlap_calculator.utils.errors import ErrorCode, format_error
from overlap_calculator.utils.logging import format_log

LOGGER = logging.getLogger(__name__)

RUN_MANIFEST_FILENAME = "run_manifest.json"
_SHA256_CHUNK_BYTES = 1024 * 1024


def _sha256_file(path: Path) -> str | None:
    digest = hashlib.sha256()
    try:
        with path.open("rb") as handle:
            for chunk in iter(lambda: handle.read(_SHA256_CHUNK_BYTES), b""):
                digest.update(chunk)
    except OSError:
        return None
    return digest.hexdigest()


def _relative_source(source_path: str) -> str:
    """Input reference for the manifest: a run-directory-relative POSIX path.

    Records e.g. ``input/files/sample.out`` (relative to the directory the run
    was launched from) rather than an absolute machine path. If the input lies
    outside the run directory or on another drive, only the base file name is
    recorded so no absolute path or parent layout leaks. The SHA-256 fingerprints
    the file content regardless.
    """
    source = Path(source_path)
    try:
        rel = Path(os.path.relpath(source, Path.cwd())).as_posix()
    except ValueError:
        return source.name
    if rel == ".." or rel.startswith("../"):
        return source.name
    return rel


def _git_commit() -> str | None:
    try:
        # Resolve the commit of the package's OWN source tree (meaningful for a
        # source / editable checkout); returns None for a wheel install or when the
        # source is not in a git work tree. Anchored to the package, not the caller's
        # cwd, so an unrelated repo the tool happens to run from is never recorded.
        completed = subprocess.run(
            ["git", "rev-parse", "HEAD"],
            cwd=Path(__file__).resolve().parent,
            capture_output=True,
            text=True,
            timeout=5,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return None
    if completed.returncode != 0:
        return None
    commit = completed.stdout.strip()
    return commit or None


def build_run_manifest(
    *,
    results: list[RunResult],
    items: list[AnalysisInput],
    parameters: dict[str, Any],
    skipped_items: list[AnalysisSkip] | None = None,
    light_source_names: list[str] | None = None,
) -> dict[str, Any]:
    """Assemble a reproducibility manifest for one analysis run.

    Captures the software version, the git commit (when available), a UTC
    timestamp, the SHA-256 of every input file, the resolved runtime parameters,
    and the linkage keys (sample id, run-relative source path, sheet, series) so a
    third party can reconstruct the run from archived artefacts. Source paths are
    recorded relative to the run directory (never as an absolute machine path);
    the SHA-256 fingerprints the file content.
    """
    seen_paths: set[str] = set()
    inputs: list[dict[str, Any]] = []
    for item in items:
        if item.source_path in seen_paths:
            continue
        seen_paths.add(item.source_path)
        inputs.append(
            {
                "sample_id": item.sample_id,
                "input_type": item.input_type,
                "source_path": _relative_source(item.source_path),
                "series_name": item.series_name,
                "sheet_name": item.sheet_name,
                "sha256": _sha256_file(Path(item.source_path)),
            }
        )

    return {
        "software_version": __version__,
        "git_commit": _git_commit(),
        "generated_at_utc": datetime.now(UTC).isoformat(),
        "parameters": parameters,
        "light_sources": sorted(light_source_names or []),
        "inputs": inputs,
        "results_count": len(results),
        "skipped_count": len(skipped_items or []),
    }


def write_run_manifest(out_dir: Path, manifest: dict[str, Any]) -> Path:
    out_dir.mkdir(parents=True, exist_ok=True)
    manifest_path = out_dir / RUN_MANIFEST_FILENAME
    try:
        manifest_path.write_text(
            json.dumps(manifest, indent=2, ensure_ascii=False),
            encoding="utf-8",
        )
    except OSError as exc:
        raise OutputError(
            format_error(ErrorCode.OUTPUT, f"Failed to write run manifest: {manifest_path}")
        ) from exc
    LOGGER.info(
        format_log(
            "provenance",
            "run_manifest",
            path=manifest_path,
            inputs=len(manifest.get("inputs", [])),
            version=manifest.get("software_version"),
        )
    )
    return manifest_path
