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

### Publish collected data to the hosted app for free

With the hosted API sources configured, put the matching Render values for
`MARKETPULSE_READ_TOKEN` and `MARKETPULSE_INGEST_TOKEN` in the **project root**
`.env` (never commit them). Then run:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\publish-live-data.ps1
```

This starts the local collection worker if one is not already running and
publishes recent real records to Render every five minutes. It sends up to 100
recent records per enabled source each cycle, preserves observation dates, and
skips unchanged records. Keep the computer and terminal on for updates. Ctrl+C
stops publishing and any worker started by this launcher. Existing worker
processes are left running. To publish one batch only, add `-Once`.

The connector request spacing and approved source/category/field limits still
apply. Independent sources run concurrently so a slower source does not block
the rest. Facebook is skipped while disabled. Local database records remain on
the computer as a separate copy; this is not a complete backup/restore system.

Render Free has an ephemeral filesystem: hosted SQLite records and source
settings can disappear on sleep, restart, or redeploy. Use managed PostgreSQL
for durable hosted storage before relying on the app long-term.

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

Copy `backend/.env.example` to `backend/.env` (PowerShell: `Copy-Item .env.example .env` while in `backend`). Generate separate long random values for `MARKETPULSE_ADMIN_TOKEN` and `MARKETPULSE_INGEST_TOKEN`; never commit them. Configure `OPENAI_API_KEY` and `OPENAI_MODEL` only if you intend to use AI analysis. The OpenAI API is billed separately. AI analysis is hard-limited to loopback requests; there is no remote-enable setting until user authentication and rate limits exist.

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
- The connectors are registered and tested, but collection still depends on each source being approved/enabled in the database. Facebook additionally remains operationally blocked until Meta Content Library credentials are supplied in the backend environment.
- Imported CSV data remains in browser storage; it is not synchronized to the API or shared between devices.
- The database-backed Overview is read-only and shows only records already ingested into the backend; it does not merge them into the local workspace dataset.
- The database can store price observations, but there are no live observations, verified transactions, or independently collected demand signals yet.
- OpenAI analysis requires a configured backend key/model and an available API connection. A free rule-based local analysis is available without OpenAI.
- User accounts, per-user roles, cloud sync, and team features are not configured. Admin and worker access currently use separate shared server-side tokens; do not expose them in browser code.

These require approved source access, deployment, server-side credentials, persistent backend storage, and a background worker. The app deliberately avoids presenting mock data as real.

## Suggested next implementation sequence
1. Record the written authorization reference and verify the exact permitted categories, fields, request interval, and retention with each source/operator.
2. Add the Facebook Content Library token to the backend environment if Facebook collection is in scope; never put it in frontend variables.
3. Configure managed PostgreSQL with `DATABASE_URL`, apply Alembic migrations, and back up the database.
4. Deploy the frontend, API, and persistent worker as separate services; configure CORS and server-only secrets.
5. Add account authentication, per-user permissions, and rate limits before enabling remote AI or browser-accessible ingestion/admin operations.
6. Add independently authorized transaction or demand signals before presenting demand, sale-price, or profit analysis.

## Vercel deployment
The frontend can be deployed to Vercel as a Vite project. The FastAPI service and crawler worker should be deployed separately to a Python-capable host. Configure `VITE_API_BASE_URL` with the deployed API URL and, when `MARKETPULSE_READ_TOKEN` is enabled, set the matching `VITE_API_READ_TOKEN`. Never place OpenAI secrets or marketplace credentials in frontend environment variables.
