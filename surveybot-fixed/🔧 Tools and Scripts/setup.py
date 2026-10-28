#!/usr/bin/env python3
"""Repeatable setup for the supported Playwright browser workflow."""
import argparse
import os
from pathlib import Path
import subprocess
import sys
import venv

ROOT = Path(__file__).resolve().parents[1]
ENVIRONMENT = ROOT / ".venv"


def environment_python():
    return ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")


def create_env_file():
    destination = ROOT / ".env"
    if destination.exists():
        print("Keeping existing .env unchanged.")
        return
    example = ROOT / ".env.example"
    fd = os.open(destination, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
    with os.fdopen(fd, "w", encoding="utf-8") as stream:
        stream.write(example.read_text(encoding="utf-8"))
    print("Created .env with empty credential fields. Enter your key locally or use environment settings.")


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--skip-browser", action="store_true", help="Use an existing browser configured by BROWSER_EXECUTABLE")
    parser.add_argument("--browser", choices=("chromium", "firefox", "webkit"), default="chromium")
    args = parser.parse_args(argv)
    if sys.version_info < (3, 10):
        parser.error("Python 3.10 or newer is required; Python 3.12 is tested.")
    python = environment_python()
    if not python.is_file():
        venv.EnvBuilder(with_pip=True).create(ENVIRONMENT)
    locked = ROOT / "⚙️ Configurations" / "requirements_playwright.lock.txt"
    plain = locked.with_name("requirements_playwright.txt")
    command = [str(python), "-m", "pip", "install", "-r", str(locked if locked.is_file() else plain)]
    if locked.is_file():
        command.append("--require-hashes")
    subprocess.run(command, cwd=ROOT, check=True)
    if not args.skip_browser:
        subprocess.run([str(python), "-m", "playwright", "install", args.browser], cwd=ROOT, check=True)
    create_env_file()
    print("Dependencies installed. Run: python run_bot.py --smoke-test")
    print("Live use also needs your Gemini key, persona.json and locally saved auth.json.")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except subprocess.CalledProcessError as error:
        print("Setup failed; fix the error above and rerun this command.")
        sys.exit(error.returncode or 1)
