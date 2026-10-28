# SurveySide — Qmee companion

A small local web app that explains confusing survey questions and answer choices, notices explicit instructions, and helps match an answer to the facts you provide. It also compares estimated survey value and tracks manually logged rewards. It is an independent companion, not a Qmee integration; it cannot see your Qmee account or submit surveys. Qualification depends on each survey’s criteria and quotas.

## Run

For Cloudflare hosting, use the included [Cloudflare Workers deployment guide](CLOUDFLARE.md). It uses D1 for persistence and a password to protect the hosted app. The commands below run the local Node version.

Requires Node.js 24.5 or newer and npm. From this folder:

```sh
npm ci --ignore-scripts --no-audit --no-fund --cache /workspace/.npm-cache
npm start
```

The server listens on the local machine’s port 3000. `PORT` overrides it. `npm run dev` restarts the server when its files change. No build, database server, or Qmee login is required.

## Connect the AI

Set `QMEE_AI_API_KEY` securely in your cloud environment settings and restart the app. For a local checkout, copy `.env.example` to the ignored `.env` file and enter your own key there. Never commit that file. This key is for the OpenAI API, which has its own usage billing. It is not your Qmee or ChatGPT password. The optional `QMEE_AI_MODEL` defaults to `gpt-4.1-mini`.

The server calls the official OpenAI Responses API over HTTPS. The key stays on the server. Submitted question text, chat context, and a limited dashboard summary are sent to that provider when you request an explanation; `store: false` is requested. This is not a promise about the provider’s independent retention policies. Chat is held in the current browser tab and clears on reload; it is not saved in the dashboard data file. Without a key the log and comparison tools work, and AI controls show that a connection is needed. Live AI quality must be checked after a credential is supplied.

## Use

1. Paste the complete survey question and its choices into the question coach. Add a short explanation of what is confusing, if useful.
2. Choose **Explain my choices**. The answer guide explains wording and conditional choices based on your context. You can ask follow-up questions in the guide.
3. Add survey reward/time estimates to your shortlist. Available surveys sort by estimated reward per hour.
4. Use each record’s actions menu to mark it completed or screened out. Only completed records count toward earnings. These are your own logs, not verified Qmee payments.
5. Set your currency before adding records. Currency changes are blocked while records exist to avoid relabeling past amounts. Export CSV before removing any records you want to keep.

Dashboard data lives in the ignored `.data/dashboard.json`, written atomically with restricted file permissions. `QMEE_DATA_FILE` can select another path. Keep a backup if needed. The app is intended for one person on a local machine; it has no hosted multi-user account system.

## Validate

```sh
npm run check
npm test
npm run test:browser
```

The tests exercise the HTTP server, persistence across restart and concurrent writes, earnings calculations, validation, and the official SDK against a local simulated provider. The browser smoke test uses the cloud image’s Chromium at `/usr/bin/chromium`; `CHROMIUM_PATH` can override it. It checks desktop and mobile workflows and simulated AI interactions. They do not call paid AI services or Qmee. After connecting a real key, submit a representative question to validate the live provider. No application build is needed; the browser loads static HTML, CSS, and JavaScript directly.

The repository’s original root `README.md` is unrelated GameGuardian Lua code and is preserved unchanged.
