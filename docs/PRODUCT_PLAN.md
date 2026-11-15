# Product plan

## Product goal
Help researchers, resellers and businesses understand observable activity in Nigeria's second-hand goods market using responsibly collected, traceable listing data.

## Core product areas
- Listing discovery and normalization
- Category and location exploration
- Asking-price distributions and historical changes
- Listing momentum and available engagement indicators
- Watchlists and alerts
- Explainable opportunity screening
- Exportable market reports
- Source health and data provenance

## Demand measurement principles
Do not equate supply/listing volume with demand. Demand scores should use actual available signals such as views, saves, enquiries, search interest, sell-through observations or listing removal patterns, and should disclose signal coverage and confidence. If a source does not expose engagement metrics, label the metric as listing momentum or supply activity rather than demand.

## Opportunity scoring
Potential opportunity score may combine:
- Price deviation against comparable listings
- Price history and volatility
- Listing age / price reduction
- Condition and location comparability
- Estimated transport, repair, platform and transaction costs
- Confidence and sample size

Never present an asking-price difference as guaranteed profit. Use verified completed-sale data where available.

## MVP milestones
1. Confirm source permissions and data availability.
2. Implement one compliant connector.
3. Store normalized listings and observations.
4. Build deduplication and history tracking.
5. Validate price analytics against manually checked samples.
6. Add demand signals only where source data supports them.
7. Add AI summaries with citations to underlying records.
8. Deploy frontend, API and scheduled worker separately.
