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

Copy `backend/.env.example` to `backend/.env` (PowerShell: `Copy-Item .env.example .env` while in `backend`). Generate separate long random values for `MARKETPULSE_ADMIN_TOKEN` and `MARKETPULSE_INGEST_TOKEN`; never commit them. Configure `OPENAI_API_KEY` and `OPENAI_MODEL` only if you intend to use AI analysis. The OpenAI API is billed separately. AI analysis is hard-limited to loopback requests; there is no remote-enable setting until user authentication and rate limits exist.

The database schema is managed by Alembic. Run migrations before starting the API and after each backend update. SQLite is the local default; production should use a managed PostgreSQL URL with the `postgresql+psycopg://` driver.

### Collection worker and source permissions
Run the collector as a separate process from the API:
```bash
cd backend
python -m app.worker
```
The worker only schedules sources that are enabled, marked approved, and have a registered connector. The source catalog starts with every platform disabled and permission status `unknown`. A shared admin token protects `PUT /api/admin/sources/{source_id}` and `GET /api/admin/audit`; an ingestion token protects `POST /api/listings`. The API refuses to enable a source without a connector, an explicit permission reference, categories, fields, and an allowed access method. Never set these values based only on the fact that a page is publicly reachable.

The Jiji web adapter is registered but remains disabled and unapproved by default. It checks `robots.txt` and, when explicitly enabled, reads only the first public results page of each approved category. It excludes seller profiles/contact details and does not infer a listing is expired when it disappears from the first page. The current connector is a bounded first-page integration, not full-site coverage; it is not run by tests. The worker and database record source-scoped collection runs, and the adapter will not follow redirects or access login/admin/anti-bot paths.

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
- Jiji is the only registered connector; it remains idle until an operator records its permission reference and exact scope, then approves and enables it. Other sources have no adapter.
- Imported CSV data remains in browser storage; it is not synchronized to the API or shared between devices.
- The database-backed Overview is read-only and shows only records already ingested into the backend; it does not merge them into the local workspace dataset.
- The database can store price observations, but there are no live observations, verified transactions, or independently collected demand signals yet.
- OpenAI analysis requires a configured backend key/model and an available API connection. A free rule-based local analysis is available without OpenAI.
- User accounts, per-user roles, cloud sync, and team features are not configured. Admin and worker access currently use separate shared server-side tokens; do not expose them in browser code.

These require approved source access, deployment, server-side credentials, persistent backend storage, and a background worker. The app deliberately avoids presenting mock data as real.

## Suggested next implementation sequence
1. Record the written authorization reference and verify the exact permitted categories, fields, request interval, and retention with the source/operator.
2. Expand and fixture-test Jiji's authorized first-page adapter only as needed; pagination is intentionally not implemented until its page behavior and scope are confirmed.
3. Configure managed PostgreSQL with `DATABASE_URL`, apply Alembic migrations, and back up the database.
4. Deploy the frontend, API, and persistent worker as separate services; configure CORS and server-only secrets.
5. Add account authentication, per-user permissions, and rate limits before enabling remote AI or browser-accessible ingestion/admin operations.
6. Add independently authorized transaction or demand signals before presenting demand, sale-price, or profit analysis.

## Vercel deployment
The frontend can be deployed to Vercel as a Vite project. The FastAPI service and crawler worker should be deployed separately to a Python-capable host. Configure `VITE_API_BASE_URL` with the deployed API URL and, when `MARKETPULSE_READ_TOKEN` is enabled, set the matching `VITE_API_READ_TOKEN`. Never place OpenAI secrets or marketplace credentials in frontend environment variables.
