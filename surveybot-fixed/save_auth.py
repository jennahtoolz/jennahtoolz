"""Save your own local browser login; credentials stay on your computer."""
import asyncio
import os
from pathlib import Path
import subprocess
import sys

ROOT = Path(__file__).resolve().parent
ENVIRONMENT = ROOT / ".venv"


async def save_auth():
    sys.path.insert(0, str(ROOT / "📁 Project Structure"))
    from config import Config
    from playwright.async_api import async_playwright
    if os.name != "nt" and not os.environ.get("DISPLAY"):
        print("Sign-in needs a visible browser on your own computer. No graphical display is available here.")
        return 2
    async with async_playwright() as playwright:
        browser = await getattr(playwright, Config.BROWSER_NAME).launch(headless=False,
            **({"executable_path": Config.BROWSER_EXECUTABLE} if Config.BROWSER_EXECUTABLE else {}))
        try:
            context = await browser.new_context()
            page = await context.new_page()
            await page.goto("https://www.qmee.com/en-us/login")
            print("Log in with your own account in the browser. Return here only after the dashboard opens.")
            await asyncio.to_thread(input, "Press Enter to save this local login, or Ctrl+C to cancel: ")
            if Config.AUTH_FILE.exists():
                answer = await asyncio.to_thread(input, "Replace the existing local authentication file? Type yes: ")
                if answer.strip().lower() != "yes":
                    return 1
            # Do not save a login state while still on the sign-in page.
            if "login" in page.url.lower() or "signin" in page.url.lower():
                print("The browser is still on a login page. No authentication file was saved.")
                return 2
            state = await context.storage_state()
            import json
            fd = os.open(Config.AUTH_FILE, os.O_WRONLY | os.O_CREAT | os.O_TRUNC, 0o600)
            with os.fdopen(fd, "w", encoding="utf-8") as stream:
                json.dump(state, stream)
            print("Saved local authentication state. Keep auth.json private.")
            return 0
        finally:
            await browser.close()


if __name__ == "__main__":
    python = ENVIRONMENT / ("Scripts/python.exe" if os.name == "nt" else "bin/python")
    if python.is_file() and Path(sys.prefix).resolve() != ENVIRONMENT.resolve():
        sys.exit(subprocess.call([str(python), str(Path(__file__).resolve())]))
    try:
        sys.exit(asyncio.run(save_auth()))
    except KeyboardInterrupt:
        print("Sign-in canceled.")
        sys.exit(130)
