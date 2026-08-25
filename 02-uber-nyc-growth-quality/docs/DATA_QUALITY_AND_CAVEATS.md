# Data Quality & Caveats

[**English**](DATA_QUALITY_AND_CAVEATS.md) | [**中文**](DATA_QUALITY_AND_CAVEATS_zh.md)

- Coverage: 193.4M completed Uber trips from May 2025 through May 2026; focal comparison is May 2026 versus May 2025.
- Request-to-pickup eligibility in May 2026 was 98.77%; metric-specific exclusions do not remove trips from the completed-trip count.
- Timestamps are treated as reported New York local time. Request-to-pickup is restricted to 0–60 minutes inclusive.
- Public TLC records omit unserved demand, cancellations, driver online time, dispatch acceptance, surge, reservations, promotions, and rider/driver identifiers.
- “Supply-constrained priority proxy” and “estimated excess request-to-pickup minutes” support operating prioritization only; they do not prove insufficient driver supply or another causal mechanism.
- Passenger base fare and driver pay are analyzed separately. Their difference is not platform revenue, profit, margin, or take rate.
- Monthly checks found isolated duration coverage, base-fare coverage, and trip-time mismatch anomalies outside the focal comparison.
- TLC states that provider-submitted trip records are not guaranteed to be complete or error-free.
