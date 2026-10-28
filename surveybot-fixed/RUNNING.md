# SurveyBot startup repairs

This branch repairs startup and setup in [Ishkei/SurveyBot-v2](https://github.com/Ishkei/SurveyBot-v2), based on commit `779bf5400810c9c1a0e98816fb5a3bd7cd67bb12`. The supported, tested workflow is **Playwright with Chromium**. Its DOM/action pipeline runs against a local fixture with a simulated AI provider. This does not establish that it completes live Qmee surveys or prevents screen-outs.

## Windows

Extract the repaired package to a regular folder, then double-click **Start_SurveyBot.cmd**. A Python 3.10+ installation is required; Python 3.12 was tested here. The script creates a fresh `.venv`, installs the pinned browser dependencies and Chromium, and runs the local browser check. It then opens the required local configuration files if missing and starts your own browser login. Python/Chromium setup happens once; the bundled upstream `venv` is never used. Windows execution itself has not been tested from this Linux environment.

You need a Gemini API key, your own profile facts, and your own saved Qmee browser login to run a live session. The wrapper prompts you to edit the key locally with Notepad. Keys are available from [Google AI Studio](https://aistudio.google.com/apikey). Do not send keys or `auth.json` through chat or commit them to GitHub. The key’s API access, quotas and any billing are managed by Google.

`persona.json` contains `{"about_you": {}}` initially. Fill it with your own relevant facts, such as an occupation or age, only if you want the bot to use those facts. Do not copy someone else’s sample identity. Missing facts should stop the generic AI action path; they are not a basis for inventing answers. The upstream project has additional platform-specific handlers that have not been validated here.

## Commands

From the repaired project folder:

```sh
python setup.py
python run_bot.py --smoke-test
python run_bot.py --config
```

After configuring `.env` and your own `persona.json`, save a login in a visible browser on your computer:

```sh
python save_auth.py
python run_bot.py --implementation playwright
```

The root launchers automatically use `.venv` after setup. Run them from any working directory using their full path. In a fresh shell, the root launcher needs only the standard library to display help. `.env`, profile and login paths are anchored to the project root. `SURVEY_AUTH_FILE` and `SURVEY_PERSONA_FILE` can override those locations. Existing `.env` and login files are preserved unless you explicitly confirm replacing a login file.

For a cloud machine with an existing Chromium binary:

```sh
python setup.py --skip-browser
python run_bot.py --headless --browser chromium --executable /usr/bin/chromium --smoke-test
```

The local fixture uses simulated AI and blocks external page requests. It does not access Qmee, use a real account, call a paid model, or submit a real survey. Live headless use also needs an authentication file created through your own visible browser; the cloud onboarding UI cannot provide that login browser.

## What changed

- Removed the conflicting Requests pins and isolated the supported browser dependencies in a hash-locked requirements file.
- Fixed syntax/import/path errors in all three auxiliary launchers, while preserving their optional desktop implementations. Those desktop modes were not installed or run here.
- Replaced the deprecated Gemini SDK in the selected Playwright path with the current REST SDK, consistently using `GOOGLE_API_KEY` or `GEMINI_API_KEY` and the configurable `AI_MODEL` alias.
- Made help/setup work before optional dependencies are installed, preserved configured headless mode, and propagated startup failures with nonzero status.
- Made profile loading explicit and shared browser/session paths between sign-in and the bot.
- Removed canned-answer and arbitrary-click fallbacks from the generic Playwright solver. Invalid or unavailable model actions stop that path. This does not audit or validate every upstream platform handler.

The broader legacy requirements file now resolves for Python 3.12, but its optional Selenium, V2Ray, desktop-control and OCR workflows remain unverified. Installing a proxy or changing your IP does not establish survey eligibility.

## Validation

```sh
python -m unittest discover -s tests -v
python run_bot.py --smoke-test
```

Use the `.venv` Python directly for unit tests if your shell’s `python` is a different interpreter. The unit suite covers setup entry points, working-directory independence, preserving local configuration, dependency pin conflicts, visibility flags, missing-credential failures, and the official Gemini SDK against a simulated HTTP transport. The browser check uses actual Chromium, frame extraction, radio selection, text entry, navigation and rejection of invalid model actions.

Eleven unit tests and five browser checks passed on Linux with Python 3.12 and system Chromium. Setup was repeated successfully. Live Gemini and Qmee account behavior are not verified; no eligibility or earnings claims have been tested.

The compact download contains the supported Playwright path and its tests. The full upstream checkout and the supplied repair patch retain the optional legacy launchers; their desktop/proxy implementations are not included in the compact edition.
