"""Sheet-overrides case study: drive both the CLI and the HTTP API.

Demonstrates picking a specific Excel sheet by name. On the CLI this is
expressed once per entry inside ``input.json`` via ``sheet_name``. On
the API it is expressed via the ``sheet_overrides`` form field, which
maps each uploaded filename to the sheet name to use.

Outputs (single tree per case study):

- ``output/cli/``                       CLI tables and plots
- ``output/api/``                       API ZIP unpacked into the same shape
- ``output/api/analysis_outputs.zip``   raw API ZIP response
"""

from __future__ import annotations

import io
import json
import os
import shutil
import subprocess
import sys
import zipfile
from pathlib import Path

import requests

CASE_DIR = Path(__file__).resolve().parent
REPO_ROOT = CASE_DIR.parents[1]
INPUT_JSON = CASE_DIR / "input.json"
OUTPUT_ROOT = CASE_DIR / "output"
CLI_OUT = OUTPUT_ROOT / "cli"
API_OUT = OUTPUT_ROOT / "api"
API_URL = os.environ.get("OVERLAP_API_URL", "http://localhost:8000/analyze")

SHEET_OVERRIDES: dict[str, str] = {
    "organic_uvvis_photochemcad_dataset.xlsx": "program_input_absorbance",
}

CLI_OPTIONS: list[str] = [
    "--default-light-sources", "AM15G,LEDB4",
    "--plot-dpi", "400",
]
API_FORM: dict[str, str] = {
    "default_light_sources": "AM15G,LEDB4",
    "plot_dpi": "400",
    "sheet_overrides": json.dumps(SHEET_OVERRIDES),
}


def _unique_uploads() -> list[Path]:
    manifest = json.loads(INPUT_JSON.read_text(encoding="utf-8"))
    seen: dict[str, Path] = {}
    for entry in manifest:
        path = (INPUT_JSON.parent / entry["source_path"]).resolve()
        if not path.exists():
            raise FileNotFoundError(f"Manifest references missing file: {path}")
        seen[path.name] = path
    return list(seen.values())


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


def run_api() -> Path:
    uploads = _unique_uploads()
    files = [
        ("files", (path.name, path.open("rb"), "application/octet-stream"))
        for path in uploads
    ]
    print(
        f"[API] POST {API_URL}  files={[p.name for p in uploads]}  "
        f"sheet_overrides={SHEET_OVERRIDES}"
    )
    response = requests.post(API_URL, files=files, data=API_FORM, timeout=600)
    response.raise_for_status()
    _reset_dir(API_OUT)
    zip_path = API_OUT / "analysis_outputs.zip"
    zip_path.write_bytes(response.content)
    with zipfile.ZipFile(io.BytesIO(response.content)) as archive:
        archive.extractall(API_OUT)
    return API_OUT


def main() -> int:
    OUTPUT_ROOT.mkdir(parents=True, exist_ok=True)
    cli_out = run_cli()
    print(f"[CLI] -> {cli_out}")
    try:
        api_out = run_api()
    except requests.ConnectionError:
        print(f"[API] SKIPPED — server not reachable at {API_URL}")
        print("Start it first: python -m overlap_calculator.api.app")
        print("(or via Docker: docker compose up -d)")
        return 0
    print(f"[API] -> {api_out}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
