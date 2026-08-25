"""Run the first decision-focused deep dive on the Uber NYC analytics layer.

The analysis uses only compact aggregate marts produced by
03_build_analytics_layer.py. It does not rescan the 193 million raw trip rows.

Primary decision question
-------------------------
Did May 2026 trip growth represent healthy marketplace growth, or did it come
with worsening request-to-pickup performance and geographic/time-window supply
pressure?

Important interpretation boundary
---------------------------------
The public TLC data contains completed trips, not total demand, unserved demand,
driver online time, cancellations, promotions, or surge multipliers. Therefore
"supply constrained" and "excess request-to-pickup minutes" are operational
proxies for prioritization, not causal proof of an Uber supply shortage.
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb


PRIOR_MONTH = "2025-05-01"
CURRENT_MONTH = "2026-05-01"


MONTHLY_TREND_SQL = """
SELECT
    month,
    STRFTIME(month, '%Y-%m') AS month_label,
    trips,
    trips_per_active_day,
    avg_request_to_pickup_minutes,
    p50_request_to_pickup_minutes,
    p90_request_to_pickup_minutes,
    p95_request_to_pickup_minutes,
    p99_request_to_pickup_minutes,
    wait_coverage_pct,
    avg_trip_miles,
    avg_trip_duration_minutes,
    weighted_speed_mph,
    avg_base_fare_eligible,
    avg_driver_pay_eligible,
    weighted_base_fare_per_mile,
    weighted_driver_pay_per_mile,
    driver_pay_per_occupied_hour,
    airport_fee_trip_share_pct,
    cbd_fee_trip_share_pct,
    shared_request_share_pct,
    shared_match_share_pct,
    ROUND(100.0 * (trips / NULLIF(LAG(trips) OVER (ORDER BY month), 0) - 1), 3)
        AS trips_mom_pct,
    ROUND(
        100.0 * (
            avg_request_to_pickup_minutes
            / NULLIF(LAG(avg_request_to_pickup_minutes) OVER (ORDER BY month), 0)
            - 1
        ),
        3
    ) AS request_to_pickup_mom_pct,
    ROUND(
        100.0 * (
            avg_base_fare_eligible
            / NULLIF(LAG(avg_base_fare_eligible) OVER (ORDER BY month), 0)
            - 1
        ),
        3
    ) AS base_fare_mom_pct,
    ROUND(
        100.0 * (
            avg_driver_pay_eligible
            / NULLIF(LAG(avg_driver_pay_eligible) OVER (ORDER BY month), 0)
            - 1
        ),
        3
    ) AS driver_pay_mom_pct,
    ROUND(100.0 * (trips / NULLIF(LAG(trips, 12) OVER (ORDER BY month), 0) - 1), 3)
        AS trips_yoy_pct,
    ROUND(
        100.0 * (
            avg_request_to_pickup_minutes
            / NULLIF(LAG(avg_request_to_pickup_minutes, 12) OVER (ORDER BY month), 0)
            - 1
        ),
        3
    ) AS request_to_pickup_yoy_pct
FROM monthly_metrics
ORDER BY month
"""


MONTHLY_WAIT_TREND_SQL = """
SELECT
    month,
    STRFTIME(month, '%Y-%m') AS month_label,
    metric,
    value_minutes,
    trips,
    wait_coverage_pct
FROM monthly_metrics
UNPIVOT (
    value_minutes FOR metric IN (
        avg_request_to_pickup_minutes AS 'Average',
        p50_request_to_pickup_minutes AS 'Median',
        p90_request_to_pickup_minutes AS 'P90'
    )
)
ORDER BY month, metric
"""


MAY_YOY_SUMMARY_SQL = """
WITH values_by_period AS (
    SELECT
        MAX(trips) FILTER (WHERE month = DATE '2025-05-01') AS trips_prior,
        MAX(trips) FILTER (WHERE month = DATE '2026-05-01') AS trips_current,
        MAX(avg_request_to_pickup_minutes) FILTER (WHERE month = DATE '2025-05-01')
            AS wait_prior,
        MAX(avg_request_to_pickup_minutes) FILTER (WHERE month = DATE '2026-05-01')
            AS wait_current,
        MAX(p90_request_to_pickup_minutes) FILTER (WHERE month = DATE '2025-05-01')
            AS wait_p90_prior,
        MAX(p90_request_to_pickup_minutes) FILTER (WHERE month = DATE '2026-05-01')
            AS wait_p90_current,
        MAX(avg_trip_miles) FILTER (WHERE month = DATE '2025-05-01') AS miles_prior,
        MAX(avg_trip_miles) FILTER (WHERE month = DATE '2026-05-01') AS miles_current,
        MAX(avg_trip_duration_minutes) FILTER (WHERE month = DATE '2025-05-01')
            AS duration_prior,
        MAX(avg_trip_duration_minutes) FILTER (WHERE month = DATE '2026-05-01')
            AS duration_current,
        MAX(avg_base_fare_eligible) FILTER (WHERE month = DATE '2025-05-01') AS fare_prior,
        MAX(avg_base_fare_eligible) FILTER (WHERE month = DATE '2026-05-01') AS fare_current,
        MAX(avg_driver_pay_eligible) FILTER (WHERE month = DATE '2025-05-01') AS pay_prior,
        MAX(avg_driver_pay_eligible) FILTER (WHERE month = DATE '2026-05-01') AS pay_current,
        MAX(weighted_base_fare_per_mile) FILTER (WHERE month = DATE '2025-05-01')
            AS fare_mile_prior,
        MAX(weighted_base_fare_per_mile) FILTER (WHERE month = DATE '2026-05-01')
            AS fare_mile_current,
        MAX(weighted_driver_pay_per_mile) FILTER (WHERE month = DATE '2025-05-01')
            AS pay_mile_prior,
        MAX(weighted_driver_pay_per_mile) FILTER (WHERE month = DATE '2026-05-01')
            AS pay_mile_current,
        MAX(driver_pay_per_occupied_hour) FILTER (WHERE month = DATE '2025-05-01')
            AS pay_hour_prior,
        MAX(driver_pay_per_occupied_hour) FILTER (WHERE month = DATE '2026-05-01')
            AS pay_hour_current,
        MAX(wait_coverage_pct) FILTER (WHERE month = DATE '2025-05-01') AS wait_cov_prior,
        MAX(wait_coverage_pct) FILTER (WHERE month = DATE '2026-05-01') AS wait_cov_current
    FROM monthly_metrics
), long_form AS (
    SELECT 1 AS display_order, 'Trips' AS metric, 'trips' AS unit,
        trips_prior::DOUBLE AS may_2025, trips_current::DOUBLE AS may_2026
    FROM values_by_period
    UNION ALL SELECT 2, 'Average request-to-pickup', 'minutes', wait_prior, wait_current
    FROM values_by_period
    UNION ALL SELECT 3, 'P90 request-to-pickup', 'minutes', wait_p90_prior, wait_p90_current
    FROM values_by_period
    UNION ALL SELECT 4, 'Average trip distance', 'miles', miles_prior, miles_current
    FROM values_by_period
    UNION ALL SELECT 5, 'Average trip duration', 'minutes', duration_prior, duration_current
    FROM values_by_period
    UNION ALL SELECT 6, 'Average eligible base fare', 'USD/trip', fare_prior, fare_current
    FROM values_by_period
    UNION ALL SELECT 7, 'Average eligible driver pay', 'USD/trip', pay_prior, pay_current
    FROM values_by_period
    UNION ALL SELECT 8, 'Weighted base fare per mile', 'USD/mile', fare_mile_prior, fare_mile_current
    FROM values_by_period
    UNION ALL SELECT 9, 'Weighted driver pay per mile', 'USD/mile', pay_mile_prior, pay_mile_current
    FROM values_by_period
    UNION ALL SELECT 10, 'Driver pay per occupied hour', 'USD/occupied hour', pay_hour_prior, pay_hour_current
    FROM values_by_period
    UNION ALL SELECT 11, 'Wait eligibility coverage', 'percent', wait_cov_prior, wait_cov_current
    FROM values_by_period
)
SELECT
    display_order,
    metric,
    unit,
    ROUND(may_2025, 4) AS may_2025,
    ROUND(may_2026, 4) AS may_2026,
    ROUND(may_2026 - may_2025, 4) AS absolute_change,
    ROUND(100.0 * (may_2026 / NULLIF(may_2025, 0) - 1), 3) AS change_pct
FROM long_form
ORDER BY display_order
"""


BOROUGH_YOY_SQL = """
WITH borough_month AS (
    SELECT
        z.month,
        COALESCE(l.Borough, 'Unmapped') AS borough,
        SUM(z.trips) AS trips,
        SUM(z.wait_eligible_trips) AS wait_eligible_trips,
        SUM(z.avg_request_to_pickup_minutes * z.wait_eligible_trips)
            / NULLIF(SUM(z.wait_eligible_trips), 0) AS avg_wait,
        SUM(z.duration_eligible_trips) AS duration_eligible_trips,
        SUM(z.avg_trip_duration_minutes * z.duration_eligible_trips)
            / NULLIF(SUM(z.duration_eligible_trips), 0) AS avg_duration,
        SUM(z.distance_eligible_trips) AS distance_eligible_trips,
        SUM(z.avg_trip_miles * z.distance_eligible_trips)
            / NULLIF(SUM(z.distance_eligible_trips), 0) AS avg_miles,
        SUM(z.base_fare_eligible_trips) AS fare_eligible_trips,
        SUM(z.avg_base_fare_eligible * z.base_fare_eligible_trips)
            / NULLIF(SUM(z.base_fare_eligible_trips), 0) AS avg_fare,
        SUM(z.driver_pay_eligible_trips) AS pay_eligible_trips,
        SUM(z.avg_driver_pay_eligible * z.driver_pay_eligible_trips)
            / NULLIF(SUM(z.driver_pay_eligible_trips), 0) AS avg_driver_pay,
        SUM(z.total_base_fare_reported) AS total_base_fare_reported,
        SUM(z.total_driver_pay_reported) AS total_driver_pay_reported,
        SUM(z.airport_fee_trips) AS airport_fee_trips,
        SUM(z.cbd_fee_trips) AS cbd_fee_trips
    FROM zone_daily_metrics z
    LEFT JOIN taxi_zones l
      ON z.pickup_location_id = l.LocationID
    WHERE z.month IN (DATE '2025-05-01', DATE '2026-05-01')
    GROUP BY z.month, COALESCE(l.Borough, 'Unmapped')
), pivoted AS (
    SELECT
        borough,
        SUM(trips) FILTER (WHERE month = DATE '2025-05-01') AS trips_2025_05,
        SUM(trips) FILTER (WHERE month = DATE '2026-05-01') AS trips_2026_05,
        SUM(wait_eligible_trips) FILTER (WHERE month = DATE '2025-05-01')
            AS wait_eligible_trips_2025_05,
        SUM(wait_eligible_trips) FILTER (WHERE month = DATE '2026-05-01')
            AS wait_eligible_trips_2026_05,
        MAX(avg_wait) FILTER (WHERE month = DATE '2025-05-01') AS avg_wait_2025_05,
        MAX(avg_wait) FILTER (WHERE month = DATE '2026-05-01') AS avg_wait_2026_05,
        MAX(avg_miles) FILTER (WHERE month = DATE '2025-05-01') AS avg_miles_2025_05,
        MAX(avg_miles) FILTER (WHERE month = DATE '2026-05-01') AS avg_miles_2026_05,
        MAX(avg_duration) FILTER (WHERE month = DATE '2025-05-01') AS avg_duration_2025_05,
        MAX(avg_duration) FILTER (WHERE month = DATE '2026-05-01') AS avg_duration_2026_05,
        MAX(avg_fare) FILTER (WHERE month = DATE '2025-05-01') AS avg_fare_2025_05,
        MAX(avg_fare) FILTER (WHERE month = DATE '2026-05-01') AS avg_fare_2026_05,
        MAX(avg_driver_pay) FILTER (WHERE month = DATE '2025-05-01') AS avg_driver_pay_2025_05,
        MAX(avg_driver_pay) FILTER (WHERE month = DATE '2026-05-01') AS avg_driver_pay_2026_05,
        SUM(total_base_fare_reported) FILTER (WHERE month = DATE '2025-05-01') AS fare_2025_05,
        SUM(total_base_fare_reported) FILTER (WHERE month = DATE '2026-05-01') AS fare_2026_05,
        SUM(total_driver_pay_reported) FILTER (WHERE month = DATE '2025-05-01') AS pay_2025_05,
        SUM(total_driver_pay_reported) FILTER (WHERE month = DATE '2026-05-01') AS pay_2026_05
    FROM borough_month
    GROUP BY borough
), totals AS (
    SELECT
        SUM(trips_2025_05) AS total_trips_prior,
        SUM(trips_2026_05) AS total_trips_current,
        SUM(trips_2026_05 - trips_2025_05) AS total_trip_delta
    FROM pivoted
)
SELECT
    p.borough,
    p.trips_2025_05,
    p.trips_2026_05,
    p.trips_2026_05 - p.trips_2025_05 AS trip_delta,
    ROUND(100.0 * (p.trips_2026_05 / NULLIF(p.trips_2025_05, 0) - 1), 3) AS trip_growth_pct,
    ROUND(100.0 * p.trips_2026_05 / t.total_trips_current, 3) AS trip_share_2026_pct,
    ROUND(100.0 * (p.trips_2026_05 - p.trips_2025_05) / NULLIF(t.total_trip_delta, 0), 3)
        AS contribution_to_city_trip_growth_pct,
    p.wait_eligible_trips_2025_05,
    p.wait_eligible_trips_2026_05,
    ROUND(p.avg_wait_2025_05, 3) AS avg_wait_2025_05,
    ROUND(p.avg_wait_2026_05, 3) AS avg_wait_2026_05,
    ROUND(100.0 * (p.avg_wait_2026_05 / NULLIF(p.avg_wait_2025_05, 0) - 1), 3)
        AS avg_wait_change_pct,
    ROUND(p.avg_miles_2025_05, 3) AS avg_miles_2025_05,
    ROUND(p.avg_miles_2026_05, 3) AS avg_miles_2026_05,
    ROUND(p.avg_fare_2025_05, 2) AS avg_fare_2025_05,
    ROUND(p.avg_fare_2026_05, 2) AS avg_fare_2026_05,
    ROUND(p.avg_driver_pay_2025_05, 2) AS avg_driver_pay_2025_05,
    ROUND(p.avg_driver_pay_2026_05, 2) AS avg_driver_pay_2026_05,
    ROUND(p.fare_2025_05, 2) AS total_base_fare_2025_05,
    ROUND(p.fare_2026_05, 2) AS total_base_fare_2026_05,
    ROUND(p.pay_2025_05, 2) AS total_driver_pay_2025_05,
    ROUND(p.pay_2026_05, 2) AS total_driver_pay_2026_05
FROM pivoted p
CROSS JOIN totals t
ORDER BY trip_delta DESC
"""


WAIT_DECOMPOSITION_SQL = """
WITH totals AS (
    SELECT
        SUM(wait_eligible_trips_2025_05) AS wait_trips_prior,
        SUM(wait_eligible_trips_2026_05) AS wait_trips_current,
        SUM(avg_wait_2025_05 * wait_eligible_trips_2025_05)
            / SUM(wait_eligible_trips_2025_05) AS city_wait_prior,
        SUM(avg_wait_2026_05 * wait_eligible_trips_2026_05)
            / SUM(wait_eligible_trips_2026_05) AS city_wait_current
    FROM borough_yoy
), detail AS (
    SELECT
        b.borough,
        b.wait_eligible_trips_2025_05 / t.wait_trips_prior AS prior_weight,
        b.wait_eligible_trips_2026_05 / t.wait_trips_current AS current_weight,
        b.avg_wait_2025_05,
        b.avg_wait_2026_05,
        (b.wait_eligible_trips_2025_05 / t.wait_trips_prior)
            * (b.avg_wait_2026_05 - b.avg_wait_2025_05)
            AS within_borough_contribution_minutes,
        (
            b.wait_eligible_trips_2026_05 / t.wait_trips_current
            - b.wait_eligible_trips_2025_05 / t.wait_trips_prior
        ) * b.avg_wait_2026_05 AS geographic_mix_contribution_minutes,
        t.city_wait_current - t.city_wait_prior AS city_wait_change_minutes
    FROM borough_yoy b
    CROSS JOIN totals t
)
SELECT
    borough,
    ROUND(100.0 * prior_weight, 4) AS prior_wait_trip_share_pct,
    ROUND(100.0 * current_weight, 4) AS current_wait_trip_share_pct,
    ROUND(avg_wait_2025_05, 4) AS avg_wait_2025_05,
    ROUND(avg_wait_2026_05, 4) AS avg_wait_2026_05,
    ROUND(avg_wait_2026_05 - avg_wait_2025_05, 4) AS within_borough_wait_change_minutes,
    ROUND(within_borough_contribution_minutes, 6) AS within_borough_contribution_minutes,
    ROUND(geographic_mix_contribution_minutes, 6) AS geographic_mix_contribution_minutes,
    ROUND(
        within_borough_contribution_minutes + geographic_mix_contribution_minutes,
        6
    ) AS total_contribution_minutes,
    ROUND(
        100.0 * within_borough_contribution_minutes / NULLIF(city_wait_change_minutes, 0),
        3
    ) AS within_contribution_share_of_city_change_pct,
    ROUND(
        100.0 * geographic_mix_contribution_minutes / NULLIF(city_wait_change_minutes, 0),
        3
    ) AS mix_contribution_share_of_city_change_pct
FROM detail
ORDER BY total_contribution_minutes DESC
"""


ZONE_YOY_SQL = """
WITH zone_month AS (
    SELECT
        z.month,
        z.pickup_location_id,
        COALESCE(l.Borough, 'Unmapped') AS borough,
        COALESCE(l.Zone, 'Unmapped') AS zone,
        COALESCE(l.service_zone, 'Unmapped') AS service_zone,
        SUM(z.trips) AS trips,
        SUM(z.wait_eligible_trips) AS wait_eligible_trips,
        SUM(z.avg_request_to_pickup_minutes * z.wait_eligible_trips)
            / NULLIF(SUM(z.wait_eligible_trips), 0) AS avg_wait,
        SUM(z.distance_eligible_trips) AS distance_eligible_trips,
        SUM(z.avg_trip_miles * z.distance_eligible_trips)
            / NULLIF(SUM(z.distance_eligible_trips), 0) AS avg_miles,
        SUM(z.duration_eligible_trips) AS duration_eligible_trips,
        SUM(z.avg_trip_duration_minutes * z.duration_eligible_trips)
            / NULLIF(SUM(z.duration_eligible_trips), 0) AS avg_duration,
        SUM(z.base_fare_eligible_trips) AS fare_eligible_trips,
        SUM(z.avg_base_fare_eligible * z.base_fare_eligible_trips)
            / NULLIF(SUM(z.base_fare_eligible_trips), 0) AS avg_fare,
        SUM(z.driver_pay_eligible_trips) AS pay_eligible_trips,
        SUM(z.avg_driver_pay_eligible * z.driver_pay_eligible_trips)
            / NULLIF(SUM(z.driver_pay_eligible_trips), 0) AS avg_driver_pay
    FROM zone_daily_metrics z
    LEFT JOIN taxi_zones l
      ON z.pickup_location_id = l.LocationID
    WHERE z.month IN (DATE '2025-05-01', DATE '2026-05-01')
    GROUP BY
        z.month,
        z.pickup_location_id,
        COALESCE(l.Borough, 'Unmapped'),
        COALESCE(l.Zone, 'Unmapped'),
        COALESCE(l.service_zone, 'Unmapped')
), pivoted AS (
    SELECT
        pickup_location_id,
        MAX(borough) AS borough,
        MAX(zone) AS zone,
        MAX(service_zone) AS service_zone,
        COALESCE(SUM(trips) FILTER (WHERE month = DATE '2025-05-01'), 0) AS trips_2025_05,
        COALESCE(SUM(trips) FILTER (WHERE month = DATE '2026-05-01'), 0) AS trips_2026_05,
        COALESCE(SUM(wait_eligible_trips) FILTER (WHERE month = DATE '2026-05-01'), 0)
            AS wait_eligible_trips_2026_05,
        MAX(avg_wait) FILTER (WHERE month = DATE '2025-05-01') AS avg_wait_2025_05,
        MAX(avg_wait) FILTER (WHERE month = DATE '2026-05-01') AS avg_wait_2026_05,
        MAX(avg_miles) FILTER (WHERE month = DATE '2025-05-01') AS avg_miles_2025_05,
        MAX(avg_miles) FILTER (WHERE month = DATE '2026-05-01') AS avg_miles_2026_05,
        MAX(avg_duration) FILTER (WHERE month = DATE '2025-05-01') AS avg_duration_2025_05,
        MAX(avg_duration) FILTER (WHERE month = DATE '2026-05-01') AS avg_duration_2026_05,
        MAX(avg_fare) FILTER (WHERE month = DATE '2025-05-01') AS avg_fare_2025_05,
        MAX(avg_fare) FILTER (WHERE month = DATE '2026-05-01') AS avg_fare_2026_05,
        MAX(avg_driver_pay) FILTER (WHERE month = DATE '2025-05-01') AS avg_driver_pay_2025_05,
        MAX(avg_driver_pay) FILTER (WHERE month = DATE '2026-05-01') AS avg_driver_pay_2026_05
    FROM zone_month
    GROUP BY pickup_location_id
), benchmarks AS (
    SELECT
        QUANTILE_CONT(trips_2026_05, 0.75) AS p75_zone_trips,
        SUM(avg_wait_2026_05 * wait_eligible_trips_2026_05)
            / NULLIF(SUM(wait_eligible_trips_2026_05), 0) AS city_avg_wait,
        SUM(trips_2026_05) AS city_trips_current,
        SUM(trips_2026_05 - trips_2025_05) AS city_trip_delta
    FROM pivoted
)
SELECT
    p.pickup_location_id,
    p.borough,
    p.zone,
    p.service_zone,
    p.borough || ' — ' || p.zone AS zone_label,
    p.trips_2025_05,
    p.trips_2026_05,
    p.trips_2026_05 - p.trips_2025_05 AS trip_delta,
    ROUND(100.0 * (p.trips_2026_05 / NULLIF(p.trips_2025_05, 0) - 1), 3) AS trip_growth_pct,
    ROUND(100.0 * p.trips_2026_05 / b.city_trips_current, 4) AS trip_share_2026_pct,
    ROUND(100.0 * (p.trips_2026_05 - p.trips_2025_05) / NULLIF(b.city_trip_delta, 0), 3)
        AS contribution_to_city_trip_growth_pct,
    p.wait_eligible_trips_2026_05,
    ROUND(p.avg_wait_2025_05, 3) AS avg_wait_2025_05,
    ROUND(p.avg_wait_2026_05, 3) AS avg_wait_2026_05,
    ROUND(p.avg_wait_2026_05 - p.avg_wait_2025_05, 3) AS avg_wait_change_minutes,
    ROUND(100.0 * (p.avg_wait_2026_05 / NULLIF(p.avg_wait_2025_05, 0) - 1), 3)
        AS avg_wait_change_pct,
    ROUND(p.avg_wait_2026_05 - b.city_avg_wait, 3) AS wait_gap_to_city_minutes,
    ROUND(
        p.wait_eligible_trips_2026_05 * GREATEST(p.avg_wait_2026_05 - b.city_avg_wait, 0),
        0
    ) AS estimated_excess_request_to_pickup_minutes,
    ROUND(p.avg_miles_2025_05, 3) AS avg_miles_2025_05,
    ROUND(p.avg_miles_2026_05, 3) AS avg_miles_2026_05,
    ROUND(p.avg_fare_2025_05, 2) AS avg_fare_2025_05,
    ROUND(p.avg_fare_2026_05, 2) AS avg_fare_2026_05,
    ROUND(p.avg_driver_pay_2025_05, 2) AS avg_driver_pay_2025_05,
    ROUND(p.avg_driver_pay_2026_05, 2) AS avg_driver_pay_2026_05,
    ROUND(b.p75_zone_trips, 0) AS p75_zone_trips_benchmark,
    ROUND(b.city_avg_wait, 3) AS city_avg_wait_benchmark,
    CASE
        WHEN p.trips_2026_05 >= b.p75_zone_trips
         AND p.avg_wait_2026_05 > b.city_avg_wait
        THEN 'Supply-constrained priority'
        WHEN p.trips_2026_05 >= b.p75_zone_trips
        THEN 'High-demand core'
        WHEN p.avg_wait_2026_05 > b.city_avg_wait
        THEN 'Service-risk watchlist'
        ELSE 'Lower-priority / balanced'
    END AS marketplace_quadrant
FROM pivoted p
CROSS JOIN benchmarks b
ORDER BY estimated_excess_request_to_pickup_minutes DESC, trips_2026_05 DESC
"""


HOURLY_YOY_SQL = """
WITH hourly_month AS (
    SELECT
        month,
        pickup_hour,
        SUM(trips) AS trips,
        SUM(wait_eligible_trips) AS wait_eligible_trips,
        SUM(avg_request_to_pickup_minutes * wait_eligible_trips)
            / NULLIF(SUM(wait_eligible_trips), 0) AS avg_wait,
        SUM(base_fare_eligible_trips) AS fare_eligible_trips,
        SUM(avg_base_fare_eligible * base_fare_eligible_trips)
            / NULLIF(SUM(base_fare_eligible_trips), 0) AS avg_fare,
        SUM(driver_pay_eligible_trips) AS pay_eligible_trips,
        SUM(avg_driver_pay_eligible * driver_pay_eligible_trips)
            / NULLIF(SUM(driver_pay_eligible_trips), 0) AS avg_driver_pay
    FROM zone_hour_metrics
    WHERE month IN (DATE '2025-05-01', DATE '2026-05-01')
    GROUP BY month, pickup_hour
), pivoted AS (
    SELECT
        pickup_hour,
        SUM(trips) FILTER (WHERE month = DATE '2025-05-01') AS trips_2025_05,
        SUM(trips) FILTER (WHERE month = DATE '2026-05-01') AS trips_2026_05,
        MAX(avg_wait) FILTER (WHERE month = DATE '2025-05-01') AS avg_wait_2025_05,
        MAX(avg_wait) FILTER (WHERE month = DATE '2026-05-01') AS avg_wait_2026_05,
        MAX(avg_fare) FILTER (WHERE month = DATE '2025-05-01') AS avg_fare_2025_05,
        MAX(avg_fare) FILTER (WHERE month = DATE '2026-05-01') AS avg_fare_2026_05,
        MAX(avg_driver_pay) FILTER (WHERE month = DATE '2025-05-01') AS avg_driver_pay_2025_05,
        MAX(avg_driver_pay) FILTER (WHERE month = DATE '2026-05-01') AS avg_driver_pay_2026_05
    FROM hourly_month
    GROUP BY pickup_hour
), totals AS (
    SELECT SUM(trips_2026_05 - trips_2025_05) AS city_trip_delta
    FROM pivoted
)
SELECT
    p.pickup_hour,
    p.trips_2025_05,
    p.trips_2026_05,
    ROUND(p.trips_2025_05 / 31.0, 1) AS avg_daily_trips_2025_05,
    ROUND(p.trips_2026_05 / 31.0, 1) AS avg_daily_trips_2026_05,
    p.trips_2026_05 - p.trips_2025_05 AS trip_delta,
    ROUND(100.0 * (p.trips_2026_05 / NULLIF(p.trips_2025_05, 0) - 1), 3) AS trip_growth_pct,
    ROUND(100.0 * (p.trips_2026_05 - p.trips_2025_05) / NULLIF(t.city_trip_delta, 0), 3)
        AS contribution_to_city_trip_growth_pct,
    ROUND(p.avg_wait_2025_05, 3) AS avg_wait_2025_05,
    ROUND(p.avg_wait_2026_05, 3) AS avg_wait_2026_05,
    ROUND(100.0 * (p.avg_wait_2026_05 / NULLIF(p.avg_wait_2025_05, 0) - 1), 3)
        AS avg_wait_change_pct,
    ROUND(p.avg_fare_2025_05, 2) AS avg_fare_2025_05,
    ROUND(p.avg_fare_2026_05, 2) AS avg_fare_2026_05,
    ROUND(p.avg_driver_pay_2025_05, 2) AS avg_driver_pay_2025_05,
    ROUND(p.avg_driver_pay_2026_05, 2) AS avg_driver_pay_2026_05
FROM pivoted p
CROSS JOIN totals t
ORDER BY p.pickup_hour
"""


PRIORITY_WINDOWS_SQL = """
WITH window_current AS (
    SELECT
        h.iso_weekday,
        h.weekday_name,
        h.day_type,
        h.pickup_hour,
        h.pickup_location_id,
        COALESCE(l.Borough, 'Unmapped') AS borough,
        COALESCE(l.Zone, 'Unmapped') AS zone,
        h.trips,
        h.contributing_days,
        h.avg_trips_per_contributing_day,
        h.wait_eligible_trips,
        h.avg_request_to_pickup_minutes,
        h.avg_base_fare_eligible,
        h.avg_driver_pay_eligible
    FROM zone_hour_metrics h
    LEFT JOIN taxi_zones l
      ON h.pickup_location_id = l.LocationID
    WHERE h.month = DATE '2026-05-01'
      AND h.trips >= 500
), benchmarks AS (
    SELECT
        SUM(avg_request_to_pickup_minutes * wait_eligible_trips)
            / NULLIF(SUM(wait_eligible_trips), 0) AS city_avg_wait,
        QUANTILE_CONT(avg_trips_per_contributing_day, 0.75) AS p75_daily_trips
    FROM window_current
)
SELECT
    w.iso_weekday,
    w.weekday_name,
    w.day_type,
    w.pickup_hour,
    LPAD(w.pickup_hour::VARCHAR, 2, '0') || ':00' AS pickup_hour_label,
    w.pickup_location_id,
    w.borough,
    w.zone,
    w.borough || ' — ' || w.zone AS zone_label,
    w.trips,
    w.contributing_days,
    ROUND(w.avg_trips_per_contributing_day, 2) AS avg_trips_per_contributing_day,
    w.wait_eligible_trips,
    ROUND(w.avg_request_to_pickup_minutes, 3) AS avg_request_to_pickup_minutes,
    ROUND(w.avg_request_to_pickup_minutes - b.city_avg_wait, 3) AS wait_gap_to_city_minutes,
    ROUND(
        w.wait_eligible_trips / w.contributing_days
            * GREATEST(w.avg_request_to_pickup_minutes - b.city_avg_wait, 0),
        1
    ) AS estimated_excess_request_to_pickup_minutes_per_day,
    ROUND(w.avg_base_fare_eligible, 2) AS avg_base_fare_eligible,
    ROUND(w.avg_driver_pay_eligible, 2) AS avg_driver_pay_eligible,
    ROUND(b.city_avg_wait, 3) AS city_avg_wait_benchmark,
    ROUND(b.p75_daily_trips, 2) AS p75_daily_trips_benchmark
FROM window_current w
CROSS JOIN benchmarks b
WHERE w.avg_request_to_pickup_minutes > b.city_avg_wait
ORDER BY estimated_excess_request_to_pickup_minutes_per_day DESC
LIMIT 100
"""


DATA_QUALITY_REVIEW_SQL = """
SELECT
    month,
    trips,
    wait_coverage_pct,
    duration_coverage_pct,
    distance_coverage_pct,
    base_fare_coverage_pct,
    driver_pay_coverage_pct,
    pickup_zone_coverage_pct,
    negative_request_to_pickup_trips,
    request_to_pickup_gt_60min_trips,
    invalid_dropoff_trips,
    trip_time_mismatch_gt_60sec_trips,
    negative_base_fare_trips,
    negative_driver_pay_trips,
    driver_pay_gt_base_fare_pct,
    CASE
        WHEN duration_coverage_pct < 99.99 THEN 'Duration coverage anomaly'
        WHEN base_fare_coverage_pct < 99.90 THEN 'Base-fare coverage anomaly'
        WHEN trip_time_mismatch_gt_60sec_trips > 5000 THEN 'Trip-time mismatch anomaly'
        ELSE 'No material monthly anomaly'
    END AS review_note
FROM data_quality_by_month
ORDER BY month
"""


TABLE_QUERIES = [
    ("monthly_trend", MONTHLY_TREND_SQL),
    ("monthly_wait_trend", MONTHLY_WAIT_TREND_SQL),
    ("may_yoy_summary", MAY_YOY_SUMMARY_SQL),
    ("borough_yoy", BOROUGH_YOY_SQL),
    ("wait_change_decomposition", WAIT_DECOMPOSITION_SQL),
    ("zone_yoy", ZONE_YOY_SQL),
    ("hourly_yoy", HOURLY_YOY_SQL),
    ("priority_windows", PRIORITY_WINDOWS_SQL),
    ("data_quality_review", DATA_QUALITY_REVIEW_SQL),
]


def sql_literal(value: str | Path) -> str:
    return "'" + str(value).replace("\\", "/").replace("'", "''") + "'"


def repository_path(path: Path, project_dir: Path) -> str:
    """Return a portable source label without exposing a local absolute path."""
    try:
        return path.relative_to(project_dir).as_posix()
    except ValueError:
        return path.name


def export_atomic(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    target: Path,
    output_format: str,
) -> None:
    extension = ".parquet" if output_format == "parquet" else ".csv"
    temp = target.with_name(f"_{target.stem}.{uuid.uuid4().hex}{extension}")
    try:
        if output_format == "parquet":
            options = "FORMAT PARQUET, COMPRESSION ZSTD"
        elif output_format == "csv":
            options = "FORMAT CSV, HEADER TRUE"
        else:
            raise ValueError(output_format)
        con.execute(f"COPY {table_name} TO {sql_literal(temp)} ({options})")
        os.replace(temp, target)
    finally:
        temp.unlink(missing_ok=True)


def write_csv_atomic(path: Path, rows: list[dict[str, object]]) -> None:
    fields = ["check_name", "actual", "expected", "passed"]
    temp = path.with_name(f"_{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fields)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    temp = path.with_name(f"_{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def build_views(
    con: duckdb.DuckDBPyConnection,
    analytics_dir: Path,
    zone_lookup: Path,
) -> None:
    con.execute(
        f"""
        CREATE OR REPLACE VIEW monthly_metrics AS
        SELECT * FROM read_parquet({sql_literal(analytics_dir / 'monthly_metrics.parquet')});

        CREATE OR REPLACE VIEW zone_daily_metrics AS
        SELECT * FROM read_parquet({sql_literal(analytics_dir / 'zone_daily_metrics.parquet')});

        CREATE OR REPLACE VIEW zone_hour_metrics AS
        SELECT * FROM read_parquet({sql_literal(analytics_dir / 'zone_hour_metrics.parquet')});

        CREATE OR REPLACE VIEW data_quality_by_month AS
        SELECT * FROM read_parquet({sql_literal(analytics_dir / 'data_quality_by_month.parquet')});

        CREATE OR REPLACE VIEW taxi_zones AS
        SELECT
            CAST(LocationID AS INTEGER) AS LocationID,
            Borough,
            Zone,
            service_zone
        FROM read_csv_auto({sql_literal(zone_lookup)}, HEADER = TRUE, ALL_VARCHAR = TRUE);
        """
    )


def validate_inputs(con: duckdb.DuckDBPyConnection) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []

    def add(name: str, actual: object, expected: object, passed: bool) -> None:
        checks.append(
            {"check_name": name, "actual": actual, "expected": expected, "passed": passed}
        )

    zone_rows, zone_ids = con.execute(
        "SELECT COUNT(*), COUNT(DISTINCT LocationID) FROM taxi_zones"
    ).fetchone()
    add("zone lookup row count", zone_rows, 265, zone_rows == 265)
    add("zone lookup key uniqueness", zone_ids, 265, zone_ids == 265)

    monthly_rows = con.execute("SELECT COUNT(*) FROM monthly_metrics").fetchone()[0]
    add("monthly source row count", monthly_rows, 13, monthly_rows == 13)

    source_months = con.execute(
        "SELECT MIN(month), MAX(month) FROM monthly_metrics"
    ).fetchone()
    add(
        "analysis month range",
        f"{source_months[0]} to {source_months[1]}",
        "2025-05-01 to 2026-05-01",
        str(source_months[0]) == PRIOR_MONTH and str(source_months[1]) == CURRENT_MONTH,
    )

    unmatched = con.execute(
        """
        SELECT COUNT(DISTINCT z.pickup_location_id)
        FROM zone_daily_metrics z
        LEFT JOIN taxi_zones l ON z.pickup_location_id = l.LocationID
        WHERE l.LocationID IS NULL
        """
    ).fetchone()[0]
    add("pickup-zone join coverage", unmatched, 0, unmatched == 0)
    return checks


def validate_outputs(
    con: duckdb.DuckDBPyConnection,
    prior_trips: int,
    current_trips: int,
) -> list[dict[str, object]]:
    checks: list[dict[str, object]] = []

    def add(name: str, actual: object, expected: object, passed: bool) -> None:
        checks.append(
            {"check_name": name, "actual": actual, "expected": expected, "passed": passed}
        )

    borough_totals = con.execute(
        "SELECT SUM(trips_2025_05), SUM(trips_2026_05), SUM(trip_delta) FROM borough_yoy"
    ).fetchone()
    add("borough prior trips reconcile", borough_totals[0], prior_trips, borough_totals[0] == prior_trips)
    add("borough current trips reconcile", borough_totals[1], current_trips, borough_totals[1] == current_trips)
    add(
        "borough trip delta reconciles",
        borough_totals[2],
        current_trips - prior_trips,
        borough_totals[2] == current_trips - prior_trips,
    )

    zone_totals = con.execute(
        "SELECT SUM(trips_2025_05), SUM(trips_2026_05), SUM(trip_delta) FROM zone_yoy"
    ).fetchone()
    add("zone prior trips reconcile", zone_totals[0], prior_trips, zone_totals[0] == prior_trips)
    add("zone current trips reconcile", zone_totals[1], current_trips, zone_totals[1] == current_trips)
    add(
        "zone trip delta reconciles",
        zone_totals[2],
        current_trips - prior_trips,
        zone_totals[2] == current_trips - prior_trips,
    )

    hourly_totals = con.execute(
        "SELECT SUM(trips_2025_05), SUM(trips_2026_05), SUM(trip_delta) FROM hourly_yoy"
    ).fetchone()
    add("hour prior trips reconcile", hourly_totals[0], prior_trips, hourly_totals[0] == prior_trips)
    add("hour current trips reconcile", hourly_totals[1], current_trips, hourly_totals[1] == current_trips)
    add(
        "hour trip delta reconciles",
        hourly_totals[2],
        current_trips - prior_trips,
        hourly_totals[2] == current_trips - prior_trips,
    )

    zone_key_dupes = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT pickup_location_id) FROM zone_yoy"
    ).fetchone()[0]
    add("zone output key uniqueness", zone_key_dupes, 0, zone_key_dupes == 0)

    month_key_dupes = con.execute(
        "SELECT COUNT(*) - COUNT(DISTINCT month) FROM monthly_trend"
    ).fetchone()[0]
    add("monthly output key uniqueness", month_key_dupes, 0, month_key_dupes == 0)

    decomposition_total = float(
        con.execute(
            "SELECT SUM(total_contribution_minutes) FROM wait_change_decomposition"
        ).fetchone()[0]
    )
    headline_wait_change = float(
        con.execute(
            """
            SELECT absolute_change
            FROM may_yoy_summary
            WHERE metric = 'Average request-to-pickup'
            """
        ).fetchone()[0]
    )
    add(
        "wait decomposition reconciles",
        round(decomposition_total, 4),
        round(headline_wait_change, 4),
        abs(decomposition_total - headline_wait_change) < 0.001,
    )
    return checks


def build_summary(con: duckdb.DuckDBPyConnection) -> dict[str, object]:
    yoy_rows = con.execute(
        """
        SELECT metric, unit, may_2025, may_2026, absolute_change, change_pct
        FROM may_yoy_summary
        ORDER BY display_order
        """
    ).fetchall()
    yoy = {
        row[0]: {
            "unit": row[1],
            "may_2025": row[2],
            "may_2026": row[3],
            "absolute_change": row[4],
            "change_pct": row[5],
        }
        for row in yoy_rows
    }

    top_boroughs = con.execute(
        """
        SELECT borough, trip_delta, trip_growth_pct, contribution_to_city_trip_growth_pct,
               avg_wait_change_pct
        FROM borough_yoy
        ORDER BY trip_delta DESC
        LIMIT 5
        """
    ).fetchall()
    top_zones = con.execute(
        """
        SELECT zone_label, trips_2026_05, trip_delta, avg_wait_2026_05,
               avg_wait_change_pct, estimated_excess_request_to_pickup_minutes,
               marketplace_quadrant
        FROM zone_yoy
        WHERE marketplace_quadrant = 'Supply-constrained priority'
        ORDER BY estimated_excess_request_to_pickup_minutes DESC
        LIMIT 12
        """
    ).fetchall()
    priority_windows = con.execute(
        """
        SELECT weekday_name, pickup_hour_label, zone_label,
               avg_trips_per_contributing_day, avg_request_to_pickup_minutes,
               estimated_excess_request_to_pickup_minutes_per_day
        FROM priority_windows
        ORDER BY estimated_excess_request_to_pickup_minutes_per_day DESC
        LIMIT 12
        """
    ).fetchall()
    anomalies = con.execute(
        """
        SELECT month, review_note, duration_coverage_pct, base_fare_coverage_pct,
               trip_time_mismatch_gt_60sec_trips
        FROM data_quality_review
        WHERE review_note <> 'No material monthly anomaly'
        ORDER BY month
        """
    ).fetchall()
    decomposition = con.execute(
        """
        SELECT
            SUM(within_borough_contribution_minutes) AS within_minutes,
            SUM(geographic_mix_contribution_minutes) AS mix_minutes,
            SUM(total_contribution_minutes) AS total_minutes
        FROM wait_change_decomposition
        """
    ).fetchone()
    wait_driver_boroughs = con.execute(
        """
        SELECT borough, within_borough_contribution_minutes,
               geographic_mix_contribution_minutes, total_contribution_minutes
        FROM wait_change_decomposition
        ORDER BY total_contribution_minutes DESC
        LIMIT 5
        """
    ).fetchall()

    return {
        "question": (
            "Did May 2026 trip growth represent healthy marketplace growth, or did it "
            "come with worsening request-to-pickup performance and geographic/time-window pressure?"
        ),
        "comparison": "May 2026 versus May 2025",
        "headline_metrics": yoy,
        "top_borough_contributors": [
            {
                "borough": row[0],
                "trip_delta": row[1],
                "trip_growth_pct": row[2],
                "contribution_to_city_trip_growth_pct": row[3],
                "avg_wait_change_pct": row[4],
            }
            for row in top_boroughs
        ],
        "top_supply_constrained_zones": [
            {
                "zone_label": row[0],
                "trips_2026_05": row[1],
                "trip_delta": row[2],
                "avg_wait_2026_05": row[3],
                "avg_wait_change_pct": row[4],
                "estimated_excess_request_to_pickup_minutes": row[5],
                "marketplace_quadrant": row[6],
            }
            for row in top_zones
        ],
        "top_priority_windows": [
            {
                "weekday_name": row[0],
                "pickup_hour": row[1],
                "zone_label": row[2],
                "avg_trips_per_contributing_day": row[3],
                "avg_request_to_pickup_minutes": row[4],
                "estimated_excess_request_to_pickup_minutes_per_day": row[5],
            }
            for row in priority_windows
        ],
        "wait_change_decomposition": {
            "within_borough_contribution_minutes": decomposition[0],
            "geographic_mix_contribution_minutes": decomposition[1],
            "total_change_minutes": decomposition[2],
            "top_borough_drivers": [
                {
                    "borough": row[0],
                    "within_borough_contribution_minutes": row[1],
                    "geographic_mix_contribution_minutes": row[2],
                    "total_contribution_minutes": row[3],
                }
                for row in wait_driver_boroughs
            ],
        },
        "data_quality_anomalies": [
            {
                "month": row[0],
                "review_note": row[1],
                "duration_coverage_pct": row[2],
                "base_fare_coverage_pct": row[3],
                "trip_time_mismatch_gt_60sec_trips": row[4],
            }
            for row in anomalies
        ],
        "interpretation_boundary": (
            "Completed-trip data cannot measure unserved demand, cancellations, driver online time, "
            "surge pricing, promotion effects, or causal supply shortages."
        ),
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--analytics-dir", type=Path, default=None)
    parser.add_argument("--zone-lookup", type=Path, default=None)
    parser.add_argument("--output-dir", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.resolve()
    analytics_dir = (
        args.analytics_dir or project_dir / "data" / "processed" / "analytics"
    ).resolve()
    zone_lookup = (
        args.zone_lookup or project_dir / "data" / "reference" / "taxi_zone_lookup.csv"
    ).resolve()
    output_dir = (
        args.output_dir or project_dir / "data" / "processed" / "analysis"
    ).resolve()

    required = [
        analytics_dir / "monthly_metrics.parquet",
        analytics_dir / "zone_daily_metrics.parquet",
        analytics_dir / "zone_hour_metrics.parquet",
        analytics_dir / "data_quality_by_month.parquet",
        zone_lookup,
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing required inputs:\n" + "\n".join(map(str, missing)))

    output_dir.mkdir(parents=True, exist_ok=True)
    started = time.perf_counter()
    generated_at = datetime.now(timezone.utc).isoformat()
    print("=" * 88)
    print("UBER NYC DEEP ANALYSIS")
    print("=" * 88)
    print(f"Analytics layer: {analytics_dir}")
    print(f"Zone lookup    : {zone_lookup}")
    print(f"Output         : {output_dir}")

    con = duckdb.connect(database=":memory:")
    try:
        con.execute("SET threads = 8")
        build_views(con, analytics_dir, zone_lookup)
        validation = validate_inputs(con)

        table_stats: dict[str, int] = {}
        for table_name, query in TABLE_QUERIES:
            print(f"\n[BUILD] {table_name}", flush=True)
            con.execute(f"CREATE OR REPLACE TEMP TABLE {table_name} AS {query}")
            row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
            export_atomic(con, table_name, output_dir / f"{table_name}.parquet", "parquet")
            export_atomic(con, table_name, output_dir / f"{table_name}.csv", "csv")
            table_stats[table_name] = row_count
            print(f"[DONE ] {table_name}: {row_count:,} rows", flush=True)

        prior_trips, current_trips = con.execute(
            """
            SELECT
                MAX(trips) FILTER (WHERE month = DATE '2025-05-01'),
                MAX(trips) FILTER (WHERE month = DATE '2026-05-01')
            FROM monthly_metrics
            """
        ).fetchone()
        validation.extend(validate_outputs(con, prior_trips, current_trips))
        failures = [row for row in validation if not row["passed"]]
        write_csv_atomic(output_dir / "analysis_validation.csv", validation)
        if failures:
            raise RuntimeError(
                "Analysis validation failed: "
                + "; ".join(str(row["check_name"]) for row in failures)
            )

        summary = build_summary(con)
        summary["generated_at_utc"] = generated_at
        summary["source_files"] = [
            repository_path(path, project_dir) for path in required
        ]
        summary["table_rows"] = table_stats
        summary["validation_checks_passed"] = len(validation)
        write_json_atomic(output_dir / "analysis_summary.json", summary)
    finally:
        con.close()

    elapsed = time.perf_counter() - started
    print("\n" + "=" * 88)
    print("DEEP ANALYSIS COMPLETE")
    print("=" * 88)
    print(f"Validation checks passed: {len(validation)}")
    print(f"Elapsed                 : {elapsed:.1f}s")
    print(f"Output                  : {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
