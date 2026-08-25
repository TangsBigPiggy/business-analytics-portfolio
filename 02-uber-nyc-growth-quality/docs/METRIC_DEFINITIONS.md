# Core Metric Definitions

[**English**](METRIC_DEFINITIONS.md) | [**中文**](METRIC_DEFINITIONS_zh.md)

| Metric | Definition | Interpretation boundary |
|---|---|---|
| Completed trips | Count of Uber HVFHV rows where `hvfhs_license_num = 'HV0003'`. | Completed records only; not total requests, unserved demand, or unique riders. |
| Request-to-pickup time | `pickup_datetime - request_datetime`, in minutes, restricted to 0–60 inclusive. | A service proxy that may include scheduled-trip behavior; `on_scene_datetime` is monitoring-only. Chinese: **请求至上车时长**. |
| P90 request-to-pickup | 90th percentile among request-to-pickup-eligible completed trips. | Tail service measure; not a cancellation or unserved-demand measure. |
| Supply-constrained priority proxy | Taxi zones at or above the May 2026 75th percentile for completed trips and above the citywide average request-to-pickup. | Operating-priority proxy based on observed trips and service performance—not causal proof of insufficient driver supply. |
| Estimated excess request-to-pickup minutes | Eligible zone trips × `max(zone average - city average, 0)`. | Comparative burden proxy, not lost demand, customer cost, or causal impact. |
| Passenger base fare | Average non-negative `base_passenger_fare` on eligible completed trips. | Excludes tolls, tips, taxes, and fees; not platform revenue. |
| Driver pay | Average non-negative `driver_pay` on eligible completed trips. | Separate from passenger fare; their difference is not profit, margin, or take rate. |

The machine-readable source catalog is [`metric_definitions.csv`](../data/processed/analytics/metric_definitions.csv).
