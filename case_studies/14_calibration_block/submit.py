"""Calibration block case study: drive the CLI only.

Demonstrates applying a TOML calibration file before broadening via
``--calibration case_studies/14_calibration_block/calib.toml`` on the CLI.

Note: the HTTP API does not accept calibration files. Use the CLI or the
Python library for this feature. The ``run_api`` step is therefore omitted
from this script.

Outputs (single tree per case study):

- ``output/cli/``   CLI tables and plots
"""

from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

CASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CASE_DIR.parents[1]
INPUT_JSON = CASE_DIR / "input.json"
CALIB_TOML = CASE_DIR / "calib.toml"
OUTPUT_ROOT = CASE_DIR / "output"
CLI_OUT = OUTPUT_ROOT / "cli"

CLI_OPTIONS: list[str] = [
    "--default-light-sources", "AM15G,LEDB4",
    "--calibration", str(CALIB_TOML.relative_to(REPO_ROOT)),
    "--plot-dpi", "400",
]

# The HTTP API does not accept calibration files. Calibration is a
# CLI/library-only feature. There is no API_FORM for this case study.


def _reset_dir(path: Path) -> None:
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def run_cli() -> Path:
    _reset_dir(CLI_OUT)
    cmd = [
        sys.executable, "-m", "overlap_calculator.cli.main", "analyze",
        "--input", str(INPUT_JSON),
        "--out", str(CLI_OUT),
        *CLI_OPTIONS,
    ]
    print("[CLI]", " ".join(cmd))
    subprocess.run(cmd, cwd=REPO_ROOT, check=True)
    return CLI_OUT


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    cli_out = run_cli()
    print(f"[CLI] -> {cli_out}")
    print(
        "[API] SKIPPED — calibration is CLI/library-only; "
        "the HTTP API does not accept calibration files."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
