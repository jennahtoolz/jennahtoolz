# SurveySide Chrome extension

A Chrome side panel for Qmee and survey pages. It reads a question, lets you review the capture, and asks Gemini to explain the choices using your own facts. **Explain & circle best match** draws an orange oval around a supported matching option directly on the survey page. It uses the current question and supplied facts; it cannot know hidden screening preferences from the survey's topic. If there is not enough information for one answer, it explains what is missing without drawing a circle. You select and submit answers yourself.

## Install

1. Download and extract `surveyside-chrome-extension.zip` into a permanent folder.
2. In Chrome, open `chrome://extensions` and turn on **Developer mode**.
3. Click **Load unpacked** and choose the extracted folder containing `manifest.json`.
4. Pin SurveySide in Chrome's extensions menu. Open your survey and click its toolbar icon.
5. In **Setup**, enter a Gemini API key from https://aistudio.google.com/apikey and click **Save setup**. You can add your own relevant facts. The default model is `gemini-flash-latest`; Google controls model availability, quotas and any charges.

No Python, Node, Cloudflare account or web server is needed to use the extension. Chrome 116+ is required. Keep the extracted folder; Chrome loads the extension from it. It is an unpacked extension, not a Chrome Web Store publication.

To update an existing installation, replace the files in the same extracted folder with version **1.1.0**, then click **Reload** on SurveySide's card at `chrome://extensions`. Refresh the survey tab and reopen the side panel. Chrome clears the session key when reloading the extension, so enter it again in Setup.

## Circle the matching option

1. Open the survey and click **Scan current page**. Provide your relevant facts in Setup or the question note.
2. Click **Explain & circle best match**. When a captured option is supported by the question and facts, the extension scrolls to it and draws a click-through orange circle.
3. Review the explanation and press the actual answer yourself. For a dropdown, the circle surrounds the dropdown and a badge names the option to choose; the extension does not open or change it.

Circles work with visible radio/checkbox labels, supported custom controls/buttons, dropdowns and permitted frames/open shadow roots. They identify an exact option captured by the latest scan. Unknown model IDs, missing facts, an edited question preview, screenshot-only questions without captured controls, ambiguous/multiple-answer questions and changed pages do not produce a circle. Scan again after editing the preview if you want circling enabled. Image-only or inaccessible controls may still receive an explanation.

Click **Hide circle** or **Clear** to remove a circle. A new scan/analysis also removes it. It expires after two minutes and clears when detected question text changes, the target disappears/becomes unavailable, a survey field changes or the page navigates. Pressing Escape on the survey page removes it too. It is a visual suggestion and does not change survey answers or bypass eligibility checks.

## Does it read the screen?

**Text scan:** Click **Scan current page** to read CSS-visible page text, including permitted survey frames and open shadow roots. It does not read password fields, input values, textareas or hidden text. Review or edit the captured question before sending it. Large pages are shortened. It does not monitor the screen in the background, capture your desktop, access microphone/camera, or store your survey login.

**Screenshot:** Turn on **Include a screenshot of the visible tab**, then scan. Chrome requires clicking the extension's toolbar icon on that tab to grant capture access. The image covers the visible part of the web page, not the full scrolling page or other windows. You can remove it before asking Gemini. It can help with image-based questions or embedded pages whose text Chrome cannot expose. Review it for information you do not want to share. Scrolling or moving to another question requires a fresh scan; captured images do not update automatically.

**Embedded surveys:** Qmee often opens another provider's frame or website. The side panel lists detected embedded origins that lack access. Click **Allow embedded survey sites** to grant those particular origins through Chrome's own permission dialog, then scan again. Permissions are optional and can be revoked in the extension's Chrome settings. For a separate survey tab, click the extension icon on that tab first. Restricted browser pages, inaccessible/sandboxed frames and closed shadow roots may require a screenshot or manually pasted text.

The scanner does not click, fill or submit a survey. AI explanations cannot guarantee qualification or prevent a provider from screening you out.

## Data and permissions

- `activeTab` and `scripting`: read the selected website only when you scan; `sidePanel`: keep the helper beside it.
- Qmee host access is declared for Qmee page/frame reading. Gemini host access is used for AI requests. Optional HTTP/HTTPS host access is requested for specific embedded survey origins you choose; there is no installed content script that reads all sites automatically.
- **Scan** captures locally; **Explain & circle best match** sends the editable question preview, option labels and nearby question context, current facts/note and any included image directly to `generativelanguage.googleapis.com` using your key. The local element references are not sent. No developer server receives it. Google's API data policies apply.
- The key is in `chrome.storage.session`, which is restricted to extension contexts and cleared when Chrome restarts or the extension reloads. It is not encrypted by the extension and is not saved to GitHub. Your facts/model preferences use local extension storage (not Chrome Sync).
- Captures and explanations are kept in panel memory and disappear when the panel reloads. **Clear** removes the current capture; **Forget key** removes the saved session key. Remove saved facts in Setup and save again to delete them.

## Development validation

From the repository root, using Node 24+ and the existing companion's Playwright development dependency:

```sh
node --test surveyside-extension/test/ai.test.mjs
node surveyside-extension/test/browser.mjs
```

The Chromium browser harness runs the actual scanner, circle renderer and side-panel code on intercepted fixture pages and frames. It checks hidden/input exclusion (including option contexts), exact iframe-radio targeting, circle placement, unchanged form values, dropdown badges, removal on question changes, rejection of stale/unknown IDs, screenshots and recoverable provider errors. Chrome APIs and model responses are simulated. Eight unit tests also check the image transport, exact captured IDs, targeting the scanned document and rejecting changed active tabs. It makes no real Qmee or Gemini requests. This cloud browser's administrator policy blocks unpacked extension installation, so actual Chrome installation, permission dialogs, live Gemini and real Qmee pages remain unverified.

This extension is a standalone JavaScript adaptation of the earlier SurveySide helper, not a package that runs the Python SurveyBot inside Chrome. The Python version uses Playwright HTML extraction plus full-page screenshots; this extension uses Chrome's page-reading and visible-tab capture APIs.
