# Compact Playwright edition

Based on Ishkei/SurveyBot-v2 commit 779bf5400810c9c1a0e98816fb5a3bd7cd67bb12:
https://github.com/Ishkei/SurveyBot-v2

This package includes the supported Playwright/Chromium implementation and its offline tests. The optional upstream Selenium, desktop-control, OCR, V2Ray and proxy implementations are not included. Choose the default Playwright implementation; legacy options in the original CLI are outside this compact edition. The legacy requirements file is included for dependency-pin verification, not for installation. Setup installs only requirements_playwright.lock.txt.

No API keys, authentication state, real profile data or Python environments are included. See RUNNING.md for setup and the limits of validation. Eleven unit tests and five local browser checks passed on Linux; live Gemini and Qmee behavior and Windows execution remain unverified. This is not a Cloudflare Worker.

The companion downloads/surveybot-startup.patch applies startup repairs to the full upstream checkout at the commit above, including the optional launchers. From that checkout: git apply --check /path/to/surveybot-startup.patch, then git apply /path/to/surveybot-startup.patch.
