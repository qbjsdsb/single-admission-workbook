from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess


def _command_line(command: list[str]) -> str:
    try:
        result = subprocess.run(
            command, capture_output=True, text=True, timeout=15, check=False
        )
    except (OSError, subprocess.SubprocessError):
        return "unavailable"
    text = (result.stdout or result.stderr or "").strip()
    return text.splitlines()[0] if text else f"exit:{result.returncode}"


def _file_record(name: str, path: Path) -> dict[str, str]:
    if not path.is_file():
        return {"name": name, "match": str(path) or "unavailable", "sha256": "unavailable"}
    return {
        "name": name,
        "match": str(path),
        "sha256": hashlib.sha256(path.read_bytes()).hexdigest(),
    }


def _tex_font_record(filename: str) -> dict[str, str]:
    kpsewhich = shutil.which("kpsewhich")
    if not kpsewhich:
        return {"name": filename, "match": "unavailable", "sha256": "unavailable"}
    try:
        result = subprocess.run(
            [kpsewhich, filename],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        path = Path(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        path = Path()
    return _file_record(filename, path)


def _system_font_record(name: str) -> dict[str, str]:
    fc_match = shutil.which("fc-match")
    if not fc_match:
        return {"name": name, "match": "unavailable", "sha256": "unavailable"}
    try:
        result = subprocess.run(
            [fc_match, "-f", "%{file}", name],
            capture_output=True,
            text=True,
            timeout=10,
            check=False,
        )
        path = Path(result.stdout.strip())
    except (OSError, subprocess.SubprocessError):
        path = Path()
    return _file_record(name, path)


def latex_environment_payload() -> dict:
    """Describe the compile environment that can change PDF output."""
    return {
        "xelatex": _command_line(["xelatex", "--version"]),
        "kpsewhich": _command_line(["kpsewhich", "--version"]),
        "fonts": [
            _tex_font_record("FandolSong-Regular.otf"),
            _tex_font_record("FandolHei-Regular.otf"),
            _tex_font_record("FandolKai-Regular.otf"),
            _system_font_record("Tinos"),
        ],
    }


def latex_environment_fingerprint() -> str:
    payload = json.dumps(
        latex_environment_payload(),
        ensure_ascii=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")
    return hashlib.sha256(payload).hexdigest()


def combined_compile_id(source_build_id: str, environment_id: str) -> str:
    """A cached PDF is reusable only when source AND compile environment match."""
    return hashlib.sha256(
        f"{source_build_id.strip()}:{environment_id.strip()}".encode("utf-8")
    ).hexdigest()
