"""ASCII entry point; reuses the project's isolated environment when available."""
import os
from pathlib import Path
import runpy
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
if __name__ == "__main__":
    environment = ROOT / ".venv"
    python = environment / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python.is_file() and Path(sys.prefix).resolve() != environment.resolve():
        sys.exit(subprocess.call([str(python), str(Path(__file__).resolve()), *sys.argv[1:]]))
    runpy.run_path(str(ROOT / "🎯 Main Files to Run" / "run_bot.py"), run_name="__main__")
