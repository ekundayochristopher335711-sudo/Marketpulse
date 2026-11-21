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

The registry contains bounded adapters for Jiji, AAE.NG, EnytinPlus, Jax.ng,
NaijaBargains, and Facebook Marketplace. Database approval and enablement are
still required before any adapter can make a request.

The shared contract lives in `base.py` and the registry in `registry.py`. A connector must subclass `MarketplaceConnector`, implement `discover_listings()`
and `healthcheck()`, and use `self.request()` for every outbound HTTP request.
That request method applies the source's configured minimum interval, uses
bounded timeouts, does not follow redirects, and raises on HTTP errors.

The separate `app.worker` process reads due schedules from the database, persists
collection runs, ingests normalized records, and recovers runs interrupted by a
restart. It does not activate a source unless its connector is registered and its
database permission state is both approved and enabled. Keep credentials in the
backend environment; never put marketplace tokens in the frontend.

All adapters are bounded first-page/public-endpoint integrations. They check
`robots.txt`, respect the configured request interval, preserve a stable source
listing ID or URL, and omit seller profiles/contact details. The AAE adapter
uses AAE's own public vehicle function; EnytinPlus uses its public shop page;
Jax uses its public ads page; NaijaBargains uses its public homepage because
its robots file disallows `/api/`; and Facebook Marketplace uses Meta Content
Library's official API and therefore needs `MARKETPULSE_FACEBOOK_ACCESS_TOKEN`.
None of them bypasses login, CAPTCHA, paywalls, or anti-bot controls.

The AAE, EnytinPlus, Jax, NaijaBargains, and Facebook parsers are covered by
offline fixtures in `backend/tests/test_marketplace_connectors.py`; tests do
not contact marketplaces.

For approved dynamic collection environments, set
`MARKETPULSE_JIJI_PLAYWRIGHT=1`. This uses a headless Chromium page to render
the same approved category URLs and then reuses the existing parser and
ingestion safeguards. It remains first-page only, obeys the configured request
interval, and can optionally load an approved Playwright storage-state file
through `MARKETPULSE_PLAYWRIGHT_STORAGE_STATE`. Keep that file outside Git
because it can contain reusable authentication cookies.
