# Connector implementation contract

Create one adapter module per approved source. A connector should:
1. Use official APIs, permitted feeds, partnership access or another explicitly authorized method.
2. Respect source terms, robots directives, rate limits and deletion/update policies.
3. Collect only necessary listing fields; avoid personal data.
4. Preserve source URL, source identifier and observation timestamp.
5. Normalize currency, category, condition and location.
6. Deduplicate using a stable source listing ID or conservative fingerprint.
7. Never bypass login, CAPTCHA, paywalls, access controls or anti-bot protections.

Suggested interface:
- `discover_listings(since: datetime) -> list[RawListing]`
- `normalize(raw: RawListing) -> ListingPayload`
- `healthcheck() -> ConnectorStatus`

The Jiji adapter is registered, but every source starts disabled and unapproved.

The shared contract lives in `base.py` and the registry in `registry.py`. A connector must subclass `MarketplaceConnector`, implement `discover_listings()`
and `healthcheck()`, and use `self.request()` for every outbound HTTP request.
That request method applies the source's configured minimum interval, uses
bounded timeouts, does not follow redirects, and raises on HTTP errors.

The separate `app.worker` process reads due schedules from the database, persists
collection runs, ingests normalized records, and recovers runs interrupted by a
restart. It does not activate a source unless its connector is registered and its
database permission state is both approved and enabled. Keep credentials in the
backend environment; never put marketplace tokens in the frontend.

The Jiji adapter checks `robots.txt` before each run and collects only the first
result page of each explicitly permitted category. It stores listing title,
category, asking price, condition, listing URL, and coarse location; it does not
collect seller profiles or contact details. It does not paginate or infer that a
listing is expired when it disappears from the first page. Adapter behavior is
covered by offline HTML/robots fixtures; tests do not contact Jiji.

For approved dynamic collection environments, set
`MARKETPULSE_JIJI_PLAYWRIGHT=1`. This uses a headless Chromium page to render
the same approved category URLs and then reuses the existing parser and
ingestion safeguards. It remains first-page only, obeys the configured request
interval, and can optionally load an approved Playwright storage-state file
through `MARKETPULSE_PLAYWRIGHT_STORAGE_STATE`. Keep that file outside Git
because it can contain reusable authentication cookies.
