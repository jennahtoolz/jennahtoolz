# Run SurveySide on Cloudflare Workers

This project includes a Cloudflare Workers backend, static assets, and persistent D1 storage. Deploy the complete project, including `cloudflare/`, `domain.mjs`, `public/`, the lockfile, and `wrangler.jsonc`. The root repository’s original Lua script is unrelated. The new application files must be downloaded from this workspace or committed to your repository before deploying from GitHub.

These steps run in a terminal on your own computer with Node.js 24.5+ installed. You need a Cloudflare account and an OpenAI API key. No custom domain is required: Cloudflare supplies a `workers.dev` address. API usage has its own billing; Cloudflare usage is subject to your plan’s limits.

## 1. Install and sign in

Unzip the project, then run from the folder containing `wrangler.jsonc`:

```sh
cd qmee-companion
npm ci --ignore-scripts
npx wrangler login
```

Wrangler opens a browser so you can authorize your Cloudflare account. Do not put Cloudflare credentials or API keys into source files.

## 2. Create the database

```sh
npx wrangler d1 create surveyside
```

If Wrangler asks whether it should edit your configuration, choose **No**; the project already declares the `DB` binding. Copy the returned `database_id` into `wrangler.jsonc`, replacing `00000000-0000-0000-0000-000000000000`. Keep the binding name `DB` and database name `surveyside`.

Initialize its tables:

```sh
npx wrangler d1 migrations apply surveyside --remote
```

Confirm the migration when prompted. These migrations create tables without dropping existing records. The Cloudflare database is separate from the local Node app’s `.data/dashboard.json`; local records are not automatically transferred.

## 3. Deploy and add the two secrets

```sh
npm run deploy:cloudflare
npx wrangler secret put QMEE_APP_PASSWORD
npx wrangler secret put QMEE_AI_API_KEY
```

The first deploy prints the app’s address. Until you set the app password, it returns a setup message with status 503 and does not expose the dashboard or AI API.

For `QMEE_APP_PASSWORD`, enter a unique password of at least 12 characters at the hidden prompt. This protects your single-user dashboard and paid AI endpoint. For `QMEE_AI_API_KEY`, enter your OpenAI API key at the hidden prompt. These are distinct secrets. The secret commands deploy the changes automatically.

Alternatively, add them in Cloudflare under **Workers & Pages → surveyside → Settings → Variables and Secrets**, choosing type **Secret** for each, then deploy the settings change. Secrets saved in the Codex environment do not automatically transfer to Cloudflare.

## 4. Open the app

Open the address printed by Wrangler. Your browser prompts for:

- **Username:** `surveyside`
- **Password:** the `QMEE_APP_PASSWORD` value you set

Paste a survey question and its choices, then choose **Explain my choices**. If AI reports a credential or billing error, check the OpenAI key and API billing. This app cannot verify Qmee eligibility or guarantee qualification.

For updates, run `npm run deploy:cloudflare` again. Existing Worker secrets and the D1 database remain in place. Changes to database tables need their own migration.

The password protects one shared log; this is not a multi-user account system. Use HTTPS and keep the password to yourself. A browser may remember HTTP Basic credentials until its browsing session ends.

## Local Cloudflare testing

```sh
cp .dev.vars.example .dev.vars
```

Edit the ignored `.dev.vars` file to set your own app password. The AI key is optional for checking the dashboard. Do not commit `.dev.vars`.

```sh
npx wrangler d1 migrations apply surveyside --local
npm run dev:cloudflare
```

Local mode uses a separate D1 database in `.wrangler/`. `--local` does not deploy to your Cloudflare account. `npm run build:cloudflare` bundles the Worker without deploying. `npm test` covers both the Node app and the Worker adapter with local D1; `npm run test:browser` checks the Node interface. No tests make paid AI requests.

Validated here: Worker bundling, local D1 migrations and persistence, authenticated API requests, and browser workflows. Publishing to your Cloudflare account and live AI responses require your login and secrets and have not been validated here.

Official references: [Workers static assets](https://developers.cloudflare.com/workers/static-assets/), [D1 setup](https://developers.cloudflare.com/d1/get-started/), [Worker secrets](https://developers.cloudflare.com/workers/configuration/secrets/).
