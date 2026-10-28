"""Bootstrap the isolated supported browser environment."""
from pathlib import Path
import runpy

if __name__ == "__main__":
    runpy.run_path(str(Path(__file__).parent / "🔧 Tools and Scripts" / "setup.py"), run_name="__main__")
