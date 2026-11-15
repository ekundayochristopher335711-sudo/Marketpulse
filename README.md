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
2. Extract this ZIP and open the project folder in VS Code.
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

## Run the API and enable AI analysis
Requires Python 3.10+. The OpenAI key and model are read only by the backend; never put them in a `VITE_` variable.
```bash
cd backend
python -m venv .venv
# Windows: .venv\\Scripts\\activate
# macOS/Linux: source .venv/bin/activate
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```
API docs: http://localhost:8000/docs

Before starting the API, copy `backend/.env.example` to `backend/.env` (PowerShell: `Copy-Item .env.example .env` while in `backend`), then set `OPENAI_API_KEY` and `OPENAI_MODEL` to values available in your OpenAI API account. The backend loads that file at startup; restart it after changing configuration. The OpenAI API is billed separately. AI analysis is local-development-only by default; do not enable remote analysis until authentication and rate limits are in place.

## Working research workflow
- Import a CSV export from a source you are authorized to use. Import replaces the active dataset after confirmation.
- Analyze listing counts, category coverage, median asking prices, and observed price reductions from the active dataset.
- Search/filter imported listings, inspect their provenance fields, and keep a browser-persisted watchlist.
- Export the active dataset as CSV or download a market snapshot report with its data source and caveats.
- With explicit consent, request an AI interpretation of aggregated listing counts, category-level median asking prices, price reductions, and engagement coverage. Individual listing text, exact locations, source names, and seller details are not sent.
- Restore the bundled demonstration dataset from **Data sources** at any time.

CSV import requires `title`, `category`, `price` (or `asking_price`), `location`, and `source` (or `source_name`). Optional columns are `previous_price`, `condition`, `listed` (or `observed_at`), `views`, `saves`, `trend`, and `description`. Use standard CSV quoting for values containing commas, such as `"465,000"`. Download the template from **Data sources**.

Imported listings and the watchlist are stored in the browser's local storage; they are not sent to a server. Imports are not independently verified. Asking prices do not establish sale prices, profit, or buyer demand. Trend rankings only use a non-zero `trend` value supplied in the dataset.
When AI analysis is requested, only aggregate statistics and category labels go to OpenAI. The Responses API request disables application-state storage, but OpenAI's API data-retention policies may still apply; review the provider's current data controls before sending sensitive aggregates.

## Still not connected
- No marketplace API/feed connector or scheduled collection is configured.
- Imported CSV data remains in browser storage; it is not synchronized to the API or shared between devices.
- No historical observations, verified transactions, or independently collected demand signals are available.
- OpenAI analysis requires a configured backend key/model and an available API connection.
- User accounts, cloud sync, and team features are not configured.

These require approved source access, deployment, server-side credentials, persistent backend storage, and a background worker. The app deliberately avoids presenting mock data as real.

## Suggested next implementation sequence
1. Choose the first permitted source and verify its access rules.
2. Implement and test one connector with rate limiting and provenance.
3. Add durable PostgreSQL storage for deployment.
4. Add a separate worker service for scheduled collection; do not run continuous Playwright crawling inside Vercel Functions.
5. Add real signal ingestion and validate explainable demand measurements.
6. Add authentication and rate limits before exposing paid AI or ingestion endpoints remotely.

## Vercel deployment
The frontend can be deployed to Vercel as a Vite project. The FastAPI service and crawler worker should be deployed separately to a Python-capable host. Configure `VITE_API_BASE_URL` with the deployed API URL. Never place OpenAI secrets or marketplace credentials in frontend environment variables.
