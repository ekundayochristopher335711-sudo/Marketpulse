# MarketPulse — Nigeria Market Intelligence

A responsive starter application for researching Nigeria's second-hand marketplace. It includes a polished React dashboard, searchable product explorer, price and trend views, watchlist, source monitoring, reports, and a FastAPI backend scaffold.

## Important data note
The included listings and analytics are **clearly labelled demonstration data**. They are not live marketplace results and do not prove buyer demand. A real connector must be implemented for each source using its permitted API, feed, partnership, or other authorized access method. Do not bypass logins, CAPTCHAs, rate limits, or site restrictions, and do not collect personal contact details unnecessarily.

## Stack
- React 19, TypeScript, Vite, Tailwind CSS
- Recharts and Lucide
- FastAPI backend scaffold
- SQLite for local development (easy to replace with PostgreSQL)
- Optional OpenAI analysis through backend-only environment variables

## Run the frontend
1. Install Node.js 20 or newer.
2. Open the `MarketPulse-Nigeria-Market-Intelligence` folder in VS Code. It is the actual project folder inside the outer archive folder.
3. In a terminal run:
   ```bash
   npm install
   npm run dev
   ```
4. Open the local URL printed by Vite.

To create a production build:
```bash
npm run build
```

On Windows, run `powershell -ExecutionPolicy Bypass -File scripts/setup.ps1` once, then `powershell -ExecutionPolicy Bypass -File scripts/dev.ps1` to start the frontend, API and worker. Run `scripts/check.ps1` before committing changes.

## Run the API and enable AI analysis
Requires Python 3.10+. The OpenAI key and model are read only by the backend; never put them in a `VITE_` variable.
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements-dev.txt
python -m alembic upgrade head
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

### Scheduled production collection without Render

The production web app and API share the Vercel project. Supabase holds the
durable database. GitHub Actions runs one collection pass twice a day at 03:17
and 15:17 Nigeria time, plus on demand from the repository's **Actions** tab.
The scheduled worker connects directly to Supabase, so a computer does not need
to stay on.

Before collection can run, add a repository Actions secret named `DATABASE_URL`
with the Supabase Session Pooler PostgreSQL URI. Add it under GitHub **Settings
→ Secrets and variables → Actions**. The workflow applies pending migrations,
installs Chromium for the authorized NaijaBargains connector, and runs the
enabled due sources once. Facebook remains off until its approved API token is
configured as the `MARKETPULSE_FACEBOOK_ACCESS_TOKEN` Actions secret and enabled
in the database. Keep all database and marketplace credentials out of frontend
variables and Git.

On a private GitHub Free repository, scheduled minutes use the plan's included
compute allowance. The schedule is intentionally twice daily; if the account's
allowance is exhausted, GitHub blocks further private-runner use unless paid
usage is enabled. Public repositories use standard runners free of charge.

### Move the local database to Supabase

The migration helper copies the local backend database, including listings,
price history, source approvals, collection runs, and audit history, into the
new Supabase project. It snapshots SQLite while the worker is running, checks
that the destination does not already contain MarketPulse data, and asks for
the Supabase URI and database password separately. The password is entered at
a hidden prompt, encoded for the URI, used for this run only, and never written
to the repository. Facebook stays approved but disabled until its API token
is configured.

1. In the MarketPulse Supabase project, choose **Connect**, then **Session
   pooler**, and copy its PostgreSQL URI, leaving the password placeholder as
   shown.
2. From the repository folder, run:

       powershell -ExecutionPolicy Bypass -File .\scripts\migrate-local-db-to-supabase.ps1

3. Paste the URI and press Enter. Enter the database password at the hidden
   prompt. Confirm that the script prints the final row counts.
4. After the migration, copy the Session Pooler URI template from Supabase to
   the clipboard, then run
   `powershell -ExecutionPolicy Bypass -File .\scripts\copy-supabase-database-url.ps1 -UseClipboard`.
   The helper reads the URI from the clipboard, asks for the database password
   with hidden input, saves `DATABASE_URL` as a secret in Vercel production,
   and copies it for the GitHub secret.
   In GitHub, open **Settings → Secrets and variables → Actions → New
   repository secret**, name it `DATABASE_URL`, and paste the copied value.
   Return to PowerShell and press Enter to clear the clipboard.

The local SQLite database remains unchanged. The migration was verified in the
Supabase project; the scheduled worker applies any later Alembic migration
before collecting.

The helper does not print or save the database password. It requires the Vercel
CLI to be signed in to the `arlotech` team and the GitHub secret to be entered
once in the repository settings.

If that reset has already happened, the source helper can read the saved admin
token from the root `.env`, without a clipboard or hidden prompt:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\configure-production-sources.ps1 -UseEnvFile
```

This restores the previously confirmed source configuration only. Run the
publisher again to send records. This recovery does not replace permanent
database storage.

### CSV and PDF exports

The heading offers **Export CSV** and **Export PDF**. Reports also download as
PDF. Live exports fetch all active database records, not just the 50 displayed
cards. Products-page search/category/location filters and the Watchlist apply
to both exports. Other pages export the full dataset.

Records are ordered by category and product name. CSV includes numbered rows,
NGN currency, observation timestamps, and source links, with Excel-compatible
UTF-8 encoding and protection against spreadsheet formula interpretation.
PDF includes a dated summary, category medians, wrapped product tables,
clickable source links, repeating headings, and page numbers. Generation runs
locally in the browser with no paid API. CSV supports up to 50,000 records;
PDF supports 5,000. The report records its generation time in Africa/Lagos.

Copy `backend/.env.example` to `backend/.env` (PowerShell: `Copy-Item .env.example .env` while in `backend`). Generate separate long random values for `MARKETPULSE_ADMIN_TOKEN` and `MARKETPULSE_INGEST_TOKEN`; never commit them. OpenAI analysis is optional and billed separately. To enable the remote Reports feature, configure `OPENAI_API_KEY`, `OPENAI_MODEL`, `SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and a comma-separated `MARKETPULSE_AI_ALLOWED_EMAILS` allowlist on the API server. The Vercel frontend needs the public `VITE_SUPABASE_URL` and `VITE_SUPABASE_PUBLISHABLE_KEY` values for sign-in. The API verifies each Supabase Auth session, allows only listed email addresses, and enforces a persistent per-user daily limit plus a per-minute limit before contacting OpenAI. The default daily cap is 10 analyses and resets at midnight in Nigeria.

The database schema is managed by Alembic. Run migrations before starting the API and after each backend update. SQLite is the local default; production should use a managed PostgreSQL URL with the `postgresql+psycopg://` driver.

### Collection worker and source permissions
Run the collector as a separate process from the API:
```bash
cd backend
python -m app.worker
```
The worker only schedules sources that are enabled, marked approved, and have a registered connector. The source catalog starts with every platform disabled and permission status `unknown`. A shared admin token protects `PUT /api/admin/sources/{source_id}` and `GET /api/admin/audit`; an ingestion token protects `POST /api/listings`. The API refuses to enable a source without a connector, an explicit permission reference, categories, fields, and an allowed access method. Never set these values based only on the fact that a page is publicly reachable.

The backend registers bounded adapters for Jiji, AAE.NG, EnytinPlus, Jax.ng, NaijaBargains, and Facebook Marketplace. They check `robots.txt`, use only public source endpoints/pages allowed by the recorded authorization scope, preserve stable listing identity, and omit seller profiles/contact details. AAE uses its public vehicle function, EnytinPlus its public shop page, Jax its public ads page, NaijaBargains its public homepage because its robots file disallows `/api/`, and Facebook Marketplace uses Meta Content Library's official API. Facebook also requires a server-only `MARKETPULSE_FACEBOOK_ACCESS_TOKEN`; a normal Facebook login is not substituted for that credential. These are bounded first-page/first-response integrations, not full-site coverage, and the worker does not follow redirects or access login/admin/anti-bot paths.

The Overview page also reads database-backed market metrics and a small page of active listings from the API, kept visibly separate from the local demo/imported workspace. The Data Sources page reads API health and the non-secret source catalog. Neither view configures permissions, enables a connector, nor starts collection.

The listing and analytics read endpoints are open in local development when `MARKETPULSE_READ_TOKEN` is empty. For a private deployment, set that backend token and the matching frontend `VITE_API_READ_TOKEN`; the API also applies a dependency-free per-process rate limit. This is a useful baseline, not a replacement for accounts, roles, a shared rate limiter, or a managed gateway.

Backend tests:
```bash
cd ..
python -m unittest discover -s backend/tests -v
cd backend
python -m alembic check
```

## Working research workflow
- Import a CSV export from a source you are authorized to use. Import replaces the active dataset after confirmation.
- Analyze listing counts, category coverage, median asking prices, and observed price reductions from the active dataset.
- Search/filter imported listings, inspect their provenance fields, and keep a browser-persisted watchlist.
- Export the active dataset as CSV or download a market snapshot report with its data source and caveats.
- Run the free local analysis without an API key, or, with explicit consent, request an optional OpenAI interpretation of aggregated listing counts, category-level median asking prices, price reductions, and engagement coverage. Individual listing text, exact locations, source names, and seller details are not sent.
- Restore the bundled demonstration dataset from **Data sources** at any time.

CSV import requires `title`, `category`, `price` (or `asking_price`), `location`, and `source` (or `source_name`). Optional columns are `previous_price`, `condition`, `listed` (or `observed_at`), `views`, `saves`, `trend`, and `description`. Use standard CSV quoting for values containing commas, such as `"465,000"`. Download the template from **Data sources**.

Imported listings, the watchlist, price alerts, and workspace preferences are stored in the browser's versioned local storage; they are not sent to a server. Imports are not independently verified. Asking prices do not establish sale prices, profit, or buyer demand. Trend rankings only use a non-zero `trend` value supplied in the dataset. CSV imports are limited to 10 MB and 50,000 rows to keep the browser responsive.
When AI analysis is requested, only aggregate statistics and category labels go to OpenAI. The Responses API request disables application-state storage, but OpenAI's API data-retention policies may still apply; review the provider's current data controls before sending sensitive aggregates.

## Still not connected
- Five approved sources are enabled in Supabase. Scheduled collection still needs the production database URL secret in GitHub Actions and the first workflow run. Facebook remains disabled until its Meta Content Library token is supplied.
- Imported CSV data remains in browser storage; it is not synchronized to the API or shared between devices.
- The database-backed Overview is read-only and shows only records already ingested into the backend; it does not merge them into the local workspace dataset.
- The database can store price observations, but there are no live observations, verified transactions, or independently collected demand signals yet.
- OpenAI analysis requires a configured backend key/model and an available API connection. A free rule-based local analysis is available without OpenAI.
- General user accounts, per-user roles, cloud sync, and team features are not configured. Supabase Auth gates only the optional OpenAI Reports action for explicitly allowlisted email addresses. Admin and worker access still use separate shared server-side tokens; do not expose them in browser code.

## Remaining deployment steps
1. Save the Supabase `DATABASE_URL` in Vercel and as a GitHub Actions secret using the copy helper described above.
2. Push the updated `main` branch. Vercel will deploy the frontend and API; GitHub will activate the scheduled collector.
3. Check `https://marketpulse-nigeria-pi.vercel.app/api/health` for `status: ok` and `database: ok`.
4. Start **Collect authorized market data** once from GitHub **Actions**, then confirm the newest collection run and listings in the app.
5. Add the Facebook API token later if you want to enable that source.

## Vercel deployment

The root `vercel.json` deploys the Vite frontend and FastAPI API as Vercel
Services. Set the Vercel project's framework preset to **Services** so the
configuration is used. `/api/*` requests route to FastAPI and all other paths
route to the frontend on the same domain. In the Vercel project environment,
set server-side `DATABASE_URL`, `MARKETPULSE_READ_TOKEN`,
`MARKETPULSE_ADMIN_TOKEN`, and `MARKETPULSE_INGEST_TOKEN`. To enable private
OpenAI analysis, also set server-side `OPENAI_API_KEY`, `OPENAI_MODEL`,
`SUPABASE_URL`, `SUPABASE_PUBLISHABLE_KEY`, and
`MARKETPULSE_AI_ALLOWED_EMAILS` to the email of the Supabase Auth user you
created. The frontend needs `VITE_SUPABASE_URL` and
`VITE_SUPABASE_PUBLISHABLE_KEY`; the publishable key is safe to expose, while
the OpenAI key must remain server-side. `MARKETPULSE_AI_DAILY_LIMIT` defaults
to 10 analyses per account per Nigeria calendar day, and
`MARKETPULSE_AI_REQUESTS_PER_MINUTE` defaults to 3. Create your account under
Supabase Authentication → Users before signing in on Reports. The matching
`VITE_API_READ_TOKEN` is browser-visible because the app calls the read API
from the browser; it is not an admin or database credential. Add optional
Facebook credentials only when that feature is configured.

The background worker runs from `.github/workflows/collect-market-data.yml` on
GitHub Actions, not as a Vercel request handler. This avoids the Vercel function
time limit for a full collection pass. Vercel Services are available on Hobby;
function compute and transfer still follow the plan's usage limits. The
frontend uses a same-origin `/api` path in production and keeps
`http://localhost:8000` for local Vite development.
