"""Small bounded XeLaTeX driver; stop when TOC/references converge."""
from pathlib import Path
import subprocess


def reference_state(folder: Path):
    return tuple((folder / ('main' + suffix)).read_bytes()
                 if (folder / ('main' + suffix)).exists() else b''
                 for suffix in ('.aux', '.toc', '.out'))


def compile_xelatex(folder: Path, max_passes=5):
    previous = reference_state(folder)
    for pass_number in range(1, max_passes + 1):
        result = subprocess.run(
            ['xelatex', '-no-shell-escape', '-interaction=nonstopmode',
             '-halt-on-error', 'main.tex'], cwd=folder, capture_output=True, timeout=180)
        if result.returncode:
            raise ValueError(f'{folder.name}: compile failed; inspect main.log')
        current = reference_state(folder)
        log = (folder / 'main.log').read_text(errors='replace')
        rerun = any(message in log for message in (
            'Rerun to get', 'Rerun to get outlines right', 'Label(s) may have changed'))
        if current == previous and not rerun:
            return pass_number
        previous = current
    raise ValueError(f'{folder.name}: references did not converge after {max_passes} passes')
