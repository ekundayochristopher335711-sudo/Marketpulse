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

No source connector is active in this starter.
