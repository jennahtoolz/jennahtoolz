# SurveySide Chrome extension

A Chrome side panel for Qmee and survey pages. It reads a question, lets you review the capture, and asks Gemini to explain the choices using your own facts. It names a choice when the supplied facts or an explicit instruction justify one; otherwise it asks what is missing. You select and submit answers yourself.

## Install

1. Download and extract `surveyside-chrome-extension.zip` into a permanent folder.
2. In Chrome, open `chrome://extensions` and turn on **Developer mode**.
3. Click **Load unpacked** and choose the extracted folder containing `manifest.json`.
4. Pin SurveySide in Chrome's extensions menu. Open your survey and click its toolbar icon.
5. In **Setup**, enter a Gemini API key from https://aistudio.google.com/apikey and click **Save setup**. You can add your own relevant facts. The default model is `gemini-flash-latest`; Google controls model availability, quotas and any charges.

No Python, Node, Cloudflare account or web server is needed to use the extension. Chrome 116+ is required. Keep the extracted folder; Chrome loads the extension from it. It is an unpacked extension, not a Chrome Web Store publication.

## Does it read the screen?

**Text scan:** Click **Scan current page** to read CSS-visible page text, including permitted survey frames and open shadow roots. It does not read password fields, input values, textareas or hidden text. Review or edit the captured question before sending it. Large pages are shortened. It does not monitor the screen in the background, capture your desktop, access microphone/camera, or store your survey login.

**Screenshot:** Turn on **Include a screenshot of the visible tab**, then scan. Chrome requires clicking the extension's toolbar icon on that tab to grant capture access. The image covers the visible part of the web page, not the full scrolling page or other windows. You can remove it before asking Gemini. It can help with image-based questions or embedded pages whose text Chrome cannot expose. Review it for information you do not want to share. Scrolling or moving to another question requires a fresh scan; captured images do not update automatically.

**Embedded surveys:** Qmee often opens another provider's frame or website. The side panel lists detected embedded origins that lack access. Click **Allow embedded survey sites** to grant those particular origins through Chrome's own permission dialog, then scan again. Permissions are optional and can be revoked in the extension's Chrome settings. For a separate survey tab, click the extension icon on that tab first. Restricted browser pages, inaccessible/sandboxed frames and closed shadow roots may require a screenshot or manually pasted text.

The scanner does not click, fill or submit a survey. AI explanations cannot guarantee qualification or prevent a provider from screening you out.

## Data and permissions

- `activeTab` and `scripting`: read the selected website only when you scan; `sidePanel`: keep the helper beside it.
- Qmee host access is declared for Qmee page/frame reading. Gemini host access is used for AI requests. Optional HTTP/HTTPS host access is requested for specific embedded survey origins you choose; there is no installed content script that reads all sites automatically.
- **Scan** captures locally; **Explain my choices** sends only the editable question preview, current facts/note and any included image directly to `generativelanguage.googleapis.com` using your key. No developer server receives it. Google's API data policies apply.
- The key is in `chrome.storage.session`, which is restricted to extension contexts and cleared when Chrome restarts or the extension reloads. It is not encrypted by the extension and is not saved to GitHub. Your facts/model preferences use local extension storage (not Chrome Sync).
- Captures and explanations are kept in panel memory and disappear when the panel reloads. **Clear** removes the current capture; **Forget key** removes the saved session key. Remove saved facts in Setup and save again to delete them.

## Development validation

From the repository root, using Node 24+ and the existing companion's Playwright development dependency:

```sh
node --test surveyside-extension/test/ai.test.mjs
node surveyside-extension/test/browser.mjs
```

The Chromium browser harness runs the actual scanner and side-panel code on intercepted fixture pages and frames, checks hidden/input exclusion and cross-site access detection, and exercises screenshots/explanations/errors against simulated Chrome APIs and a simulated provider. It makes no real Qmee or Gemini requests. Unit tests also check image payloads and rejection/discard of screenshots when the active tab changes. This cloud browser's administrator policy blocks unpacked extension installation, so actual Chrome installation, permission dialogs, live Gemini and real Qmee pages remain unverified.

This extension is a standalone JavaScript adaptation of the earlier SurveySide helper, not a package that runs the Python SurveyBot inside Chrome. The Python version uses Playwright HTML extraction plus full-page screenshots; this extension uses Chrome's page-reading and visible-tab capture APIs.
