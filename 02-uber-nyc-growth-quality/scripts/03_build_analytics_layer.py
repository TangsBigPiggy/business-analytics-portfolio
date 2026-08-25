"""Build compact Uber NYC analytics marts from TLC HVFHV Parquet files.

Default source window: 2025-05 through 2026-05 (inclusive).

Design principles
-----------------
1. Keep every completed Uber trip for volume metrics.
2. Use metric-specific eligibility flags instead of deleting whole rows.
3. Keep passenger-fare and driver-pay economics separate. This script does not
   calculate or label platform revenue, margin, profit, spread, or take rate.
4. Treat request-to-pickup time as a service metric. ``on_scene_datetime`` is
   retained only for data-quality monitoring and is not a core KPI.
5. Let DuckDB stream and aggregate Parquet data; raw trip rows are never loaded
   into pandas or materialized as one giant merged dataset.

Outputs
-------
data/processed/analytics/
    data_quality_by_month.parquet
    data_quality_by_month.csv
    monthly_metrics.parquet
    daily_metrics.parquet
    zone_daily_metrics.parquet
    zone_hour_metrics.parquet
    metric_definitions.csv
    build_validation.csv
    build_manifest.json
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import platform
import sys
import tempfile
import time
import uuid
from datetime import date, datetime, timezone
from pathlib import Path

import duckdb


UBER_LICENSE = "HV0003"
DEFAULT_START_MONTH = "2025-05"
DEFAULT_END_MONTH = "2026-05"
DEFAULT_MEMORY_LIMIT = os.environ.get("UBER_DUCKDB_MEMORY_LIMIT", "4GB")
DEFAULT_THREADS = max(1, min(8, os.cpu_count() or 4))


REQUIRED_COLUMNS = {
    "hvfhs_license_num",
    "request_datetime",
    "on_scene_datetime",
    "pickup_datetime",
    "dropoff_datetime",
    "PULocationID",
    "DOLocationID",
    "trip_miles",
    "trip_time",
    "base_passenger_fare",
    "tolls",
    "bcf",
    "sales_tax",
    "congestion_surcharge",
    "airport_fee",
    "tips",
    "driver_pay",
    "shared_request_flag",
    "shared_match_flag",
    "wav_request_flag",
    "wav_match_flag",
    "cbd_congestion_fee",
}


METRIC_DEFINITIONS = [
    (
        "all",
        "trips",
        "Count of rows with hvfhs_license_num = 'HV0003'.",
        "All selected Uber rows are eligible.",
        "A row can count as a trip even when it is ineligible for another metric.",
    ),
    (
        "all",
        "request_to_pickup_minutes",
        "pickup_datetime minus request_datetime, in minutes.",
        "Both timestamps present and elapsed time between 0 and 60 minutes inclusive.",
        "Use the precise label Request-to-Pickup Time; it may include scheduled-trip behavior.",
    ),
    (
        "all",
        "trip_duration_minutes",
        "Official TLC trip_time divided by 60.",
        "trip_time > 0 and dropoff_datetime > pickup_datetime.",
        "Timestamp duration is used for QC; a mismatch over 60 seconds is flagged, not deleted.",
    ),
    (
        "all",
        "trip_miles",
        "TLC reported trip_miles.",
        "trip_miles > 0 for averages and denominator-based metrics.",
        "Long trips above 50 or 100 miles are retained as genuine long-tail observations and flagged.",
    ),
    (
        "all",
        "weighted_speed_mph",
        "Eligible miles divided by eligible official trip hours.",
        "Eligible trip duration and eligible distance.",
        "Speeds above 60, 80, and 100 mph remain in the data and are monitored in quality output.",
    ),
    (
        "all",
        "total_base_fare_reported",
        "Sum of reported base_passenger_fare, including rare negative adjustments.",
        "Non-null reported values.",
        "Passenger base fare excludes tolls, tips, taxes, and fees; it is not platform revenue.",
    ),
    (
        "all",
        "avg_base_fare_eligible",
        "Average reported base_passenger_fare among eligible trips.",
        "base_passenger_fare >= 0.",
        "Negative values remain in reported totals but are excluded from distribution and rate metrics.",
    ),
    (
        "all",
        "total_driver_pay_reported",
        "Sum of reported driver_pay, including rare negative adjustments.",
        "Non-null reported values.",
        "Driver compensation is analyzed separately from passenger fare.",
    ),
    (
        "all",
        "avg_driver_pay_eligible",
        "Average reported driver_pay among eligible trips.",
        "driver_pay >= 0.",
        "Do not infer platform margin or take rate by subtracting this from passenger fare.",
    ),
    (
        "all",
        "weighted_base_fare_per_mile",
        "Sum of eligible base fare divided by sum of miles on the same eligible trips.",
        "base_passenger_fare >= 0 and trip_miles > 0.",
        "A ratio of sums is used so very short trips do not dominate the metric.",
    ),
    (
        "all",
        "weighted_driver_pay_per_mile",
        "Sum of eligible driver pay divided by sum of miles on the same eligible trips.",
        "driver_pay >= 0 and trip_miles > 0.",
        "A ratio of sums is used so very short trips do not dominate the metric.",
    ),
    (
        "all",
        "driver_pay_per_occupied_hour",
        "Sum of eligible driver pay divided by official in-trip hours on the same trips.",
        "driver_pay >= 0 and eligible trip duration.",
        "This is occupied-trip compensation intensity, not driver online-hour earnings or utilization.",
    ),
    (
        "zone_daily_metrics",
        "table_grain",
        "One row per pickup_date and PULocationID.",
        "Pickup zone is between 1 and 265 inclusive.",
        "Invalid-zone coverage is retained in data_quality_by_month.",
    ),
    (
        "zone_hour_metrics",
        "table_grain",
        "One row per month, ISO weekday, pickup hour, and PULocationID.",
        "Pickup zone is between 1 and 265 inclusive.",
        "This is a recurring month/weekday/hour profile, not a single calendar-hour fact table.",
    ),
    (
        "data_quality_by_month",
        "eligibility_coverage_pct",
        "Eligible trip count divided by all Uber trips in the month, multiplied by 100.",
        "Metric-specific rule shown in the corresponding definition.",
        "Coverage rates make exclusions auditable without deleting source rows.",
    ),
    (
        "data_quality_by_month",
        "on_scene fields",
        "Population and chronological-integrity checks for on_scene_datetime.",
        "Monitoring only.",
        "Not used as a core KPI because the public field definition has an accessibility-vehicle caveat.",
    ),
]


DATA_QUALITY_SQL = """
SELECT
    month,
    COUNT(*) AS trips,
    COUNT(DISTINCT pickup_date) AS active_days,
    DATE_DIFF('day', month, month + INTERVAL 1 MONTH) AS calendar_days,
    DATE_DIFF('day', month, month + INTERVAL 1 MONTH)
        - COUNT(DISTINCT pickup_date) AS missing_pickup_days,
    MIN(pickup_datetime) AS first_pickup,
    MAX(pickup_datetime) AS last_pickup,

    COUNT(*) FILTER (WHERE request_datetime IS NULL) AS request_datetime_null_trips,
    COUNT(*) FILTER (WHERE pickup_datetime IS NULL) AS pickup_datetime_null_trips,
    COUNT(*) FILTER (WHERE dropoff_datetime IS NULL) AS dropoff_datetime_null_trips,
    COUNT(*) FILTER (
        WHERE pickup_datetime IS NOT NULL
          AND CAST(DATE_TRUNC('month', pickup_datetime) AS DATE) <> month
    ) AS pickup_month_mismatch_trips,
    COUNT(*) FILTER (WHERE request_to_pickup_minutes_raw < 0) AS negative_request_to_pickup_trips,
    COUNT(*) FILTER (WHERE request_to_pickup_minutes_raw > 60) AS request_to_pickup_gt_60min_trips,
    COUNT(*) FILTER (WHERE wait_eligible) AS wait_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE wait_eligible) / COUNT(*), 4) AS wait_coverage_pct,

    COUNT(*) FILTER (WHERE trip_time IS NULL OR trip_time <= 0) AS nonpositive_or_null_trip_time_trips,
    COUNT(*) FILTER (WHERE dropoff_datetime IS NULL OR dropoff_datetime <= pickup_datetime) AS invalid_dropoff_trips,
    COUNT(*) FILTER (WHERE trip_time_mismatch_gt_60sec) AS trip_time_mismatch_gt_60sec_trips,
    COUNT(*) FILTER (WHERE duration_eligible) AS duration_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE duration_eligible) / COUNT(*), 4) AS duration_coverage_pct,

    COUNT(*) FILTER (WHERE trip_miles < 0) AS negative_miles_trips,
    COUNT(*) FILTER (WHERE trip_miles = 0) AS zero_miles_trips,
    COUNT(*) FILTER (WHERE distance_eligible) AS distance_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE distance_eligible) / COUNT(*), 4) AS distance_coverage_pct,
    COUNT(*) FILTER (WHERE trip_miles > 50) AS miles_gt_50_trips,
    COUNT(*) FILTER (WHERE trip_miles > 100) AS miles_gt_100_trips,

    COUNT(*) FILTER (WHERE speed_mph_raw > 60) AS speed_gt_60mph_trips,
    COUNT(*) FILTER (WHERE speed_mph_raw > 80) AS speed_gt_80mph_trips,
    COUNT(*) FILTER (WHERE speed_mph_raw > 100) AS speed_gt_100mph_trips,
    COUNT(*) FILTER (WHERE speed_eligible) AS speed_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE speed_eligible) / COUNT(*), 4) AS speed_coverage_pct,

    COUNT(*) FILTER (WHERE base_passenger_fare < 0) AS negative_base_fare_trips,
    COUNT(*) FILTER (WHERE base_passenger_fare = 0) AS zero_base_fare_trips,
    COUNT(*) FILTER (WHERE fare_eligible) AS base_fare_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE fare_eligible) / COUNT(*), 4) AS base_fare_coverage_pct,
    COUNT(*) FILTER (WHERE driver_pay < 0) AS negative_driver_pay_trips,
    COUNT(*) FILTER (WHERE driver_pay = 0) AS zero_driver_pay_trips,
    COUNT(*) FILTER (WHERE driver_pay_eligible) AS driver_pay_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE driver_pay_eligible) / COUNT(*), 4) AS driver_pay_coverage_pct,
    COUNT(*) FILTER (WHERE driver_pay > base_passenger_fare) AS driver_pay_gt_base_fare_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE driver_pay > base_passenger_fare) / COUNT(*), 4)
        AS driver_pay_gt_base_fare_pct,

    COUNT(*) FILTER (WHERE pickup_zone_invalid) AS invalid_pickup_zone_trips,
    COUNT(*) FILTER (WHERE dropoff_zone_invalid) AS invalid_dropoff_zone_trips,
    COUNT(*) FILTER (WHERE NOT pickup_zone_invalid) AS pickup_zone_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE NOT pickup_zone_invalid) / COUNT(*), 4)
        AS pickup_zone_coverage_pct,

    COUNT(*) FILTER (WHERE on_scene_datetime IS NOT NULL) AS on_scene_populated_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE on_scene_datetime IS NOT NULL) / COUNT(*), 4)
        AS on_scene_population_pct,
    COUNT(*) FILTER (
        WHERE on_scene_datetime IS NOT NULL
          AND request_datetime IS NOT NULL
          AND on_scene_datetime < request_datetime
    ) AS on_scene_before_request_trips,
    COUNT(*) FILTER (
        WHERE on_scene_datetime IS NOT NULL
          AND pickup_datetime IS NOT NULL
          AND on_scene_datetime > pickup_datetime
    ) AS on_scene_after_pickup_trips
FROM uber_enriched
GROUP BY month
ORDER BY month
"""


MONTHLY_METRICS_SQL = """
SELECT
    month,
    COUNT(*) AS trips,
    COUNT(DISTINCT pickup_date) AS active_days,
    ROUND(COUNT(*)::DOUBLE / COUNT(DISTINCT pickup_date), 2) AS trips_per_active_day,
    COUNT(DISTINCT PULocationID) FILTER (WHERE NOT pickup_zone_invalid) AS active_pickup_zones,

    COUNT(*) FILTER (WHERE wait_eligible) AS wait_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE wait_eligible) / COUNT(*), 4) AS wait_coverage_pct,
    ROUND(AVG(wait_minutes), 3) AS avg_request_to_pickup_minutes,
    ROUND(APPROX_QUANTILE(wait_minutes, 0.50), 3) AS p50_request_to_pickup_minutes,
    ROUND(APPROX_QUANTILE(wait_minutes, 0.90), 3) AS p90_request_to_pickup_minutes,
    ROUND(APPROX_QUANTILE(wait_minutes, 0.95), 3) AS p95_request_to_pickup_minutes,
    ROUND(APPROX_QUANTILE(wait_minutes, 0.99), 3) AS p99_request_to_pickup_minutes,

    COUNT(*) FILTER (WHERE duration_eligible) AS duration_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE duration_eligible) / COUNT(*), 4) AS duration_coverage_pct,
    ROUND(AVG(trip_duration_minutes), 3) AS avg_trip_duration_minutes,
    ROUND(APPROX_QUANTILE(trip_duration_minutes, 0.50), 3) AS p50_trip_duration_minutes,
    ROUND(APPROX_QUANTILE(trip_duration_minutes, 0.95), 3) AS p95_trip_duration_minutes,

    COUNT(*) FILTER (WHERE distance_eligible) AS distance_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE distance_eligible) / COUNT(*), 4) AS distance_coverage_pct,
    ROUND(AVG(eligible_trip_miles), 3) AS avg_trip_miles,
    ROUND(APPROX_QUANTILE(eligible_trip_miles, 0.50), 3) AS p50_trip_miles,
    ROUND(APPROX_QUANTILE(eligible_trip_miles, 0.95), 3) AS p95_trip_miles,
    ROUND(
        SUM(CASE WHEN speed_eligible THEN trip_miles END)
        / NULLIF(SUM(CASE WHEN speed_eligible THEN trip_time / 3600.0 END), 0),
        3
    ) AS weighted_speed_mph,

    ROUND(SUM(base_passenger_fare), 2) AS total_base_fare_reported,
    COUNT(*) FILTER (WHERE fare_eligible) AS base_fare_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE fare_eligible) / COUNT(*), 4) AS base_fare_coverage_pct,
    ROUND(AVG(eligible_base_fare), 2) AS avg_base_fare_eligible,
    ROUND(APPROX_QUANTILE(eligible_base_fare, 0.50), 2) AS p50_base_fare_eligible,
    ROUND(APPROX_QUANTILE(eligible_base_fare, 0.95), 2) AS p95_base_fare_eligible,

    ROUND(SUM(driver_pay), 2) AS total_driver_pay_reported,
    COUNT(*) FILTER (WHERE driver_pay_eligible) AS driver_pay_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE driver_pay_eligible) / COUNT(*), 4) AS driver_pay_coverage_pct,
    ROUND(AVG(eligible_driver_pay), 2) AS avg_driver_pay_eligible,
    ROUND(APPROX_QUANTILE(eligible_driver_pay, 0.50), 2) AS p50_driver_pay_eligible,
    ROUND(APPROX_QUANTILE(eligible_driver_pay, 0.95), 2) AS p95_driver_pay_eligible,

    ROUND(
        SUM(CASE WHEN fare_per_mile_eligible THEN base_passenger_fare END)
        / NULLIF(SUM(CASE WHEN fare_per_mile_eligible THEN trip_miles END), 0),
        3
    ) AS weighted_base_fare_per_mile,
    ROUND(
        SUM(CASE WHEN driver_pay_per_mile_eligible THEN driver_pay END)
        / NULLIF(SUM(CASE WHEN driver_pay_per_mile_eligible THEN trip_miles END), 0),
        3
    ) AS weighted_driver_pay_per_mile,
    ROUND(
        SUM(CASE WHEN driver_pay_per_hour_eligible THEN driver_pay END)
        / NULLIF(SUM(CASE WHEN driver_pay_per_hour_eligible THEN trip_time / 3600.0 END), 0),
        3
    ) AS driver_pay_per_occupied_hour,

    ROUND(SUM(tolls), 2) AS total_tolls_reported,
    ROUND(SUM(bcf), 2) AS total_bcf_reported,
    ROUND(SUM(sales_tax), 2) AS total_sales_tax_reported,
    ROUND(SUM(congestion_surcharge), 2) AS total_congestion_surcharge_reported,
    ROUND(SUM(airport_fee), 2) AS total_airport_fee_reported,
    ROUND(SUM(cbd_congestion_fee), 2) AS total_cbd_congestion_fee_reported,
    ROUND(SUM(tips), 2) AS total_tips_reported,

    COUNT(*) FILTER (WHERE airport_fee > 0) AS airport_fee_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE airport_fee > 0) / COUNT(*), 3) AS airport_fee_trip_share_pct,
    COUNT(*) FILTER (WHERE cbd_congestion_fee > 0) AS cbd_fee_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE cbd_congestion_fee > 0) / COUNT(*), 3) AS cbd_fee_trip_share_pct,
    COUNT(*) FILTER (WHERE shared_request_flag = 'Y') AS shared_request_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE shared_request_flag = 'Y') / COUNT(*), 3)
        AS shared_request_share_pct,
    COUNT(*) FILTER (WHERE shared_match_flag = 'Y') AS shared_match_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE shared_match_flag = 'Y') / COUNT(*), 3)
        AS shared_match_share_pct,
    COUNT(*) FILTER (WHERE wav_request_flag = 'Y') AS wav_request_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE wav_request_flag = 'Y') / COUNT(*), 3)
        AS wav_request_share_pct
FROM uber_enriched
GROUP BY month
ORDER BY month
"""


DAILY_METRICS_SQL = """
SELECT
    pickup_date,
    month,
    CAST(DATE_PART('isodow', pickup_date) AS TINYINT) AS iso_weekday,
    STRFTIME(pickup_date, '%A') AS weekday_name,
    DATE_PART('isodow', pickup_date) IN (6, 7) AS is_weekend,
    COUNT(*) AS trips,
    COUNT(DISTINCT PULocationID) FILTER (WHERE NOT pickup_zone_invalid) AS active_pickup_zones,

    COUNT(*) FILTER (WHERE wait_eligible) AS wait_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE wait_eligible) / COUNT(*), 4) AS wait_coverage_pct,
    ROUND(AVG(wait_minutes), 3) AS avg_request_to_pickup_minutes,
    ROUND(APPROX_QUANTILE(wait_minutes, 0.50), 3) AS p50_request_to_pickup_minutes,
    ROUND(APPROX_QUANTILE(wait_minutes, 0.90), 3) AS p90_request_to_pickup_minutes,

    COUNT(*) FILTER (WHERE duration_eligible) AS duration_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE duration_eligible) / COUNT(*), 4) AS duration_coverage_pct,
    ROUND(AVG(trip_duration_minutes), 3) AS avg_trip_duration_minutes,
    ROUND(APPROX_QUANTILE(trip_duration_minutes, 0.50), 3) AS p50_trip_duration_minutes,

    COUNT(*) FILTER (WHERE distance_eligible) AS distance_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE distance_eligible) / COUNT(*), 4) AS distance_coverage_pct,
    ROUND(AVG(eligible_trip_miles), 3) AS avg_trip_miles,
    ROUND(APPROX_QUANTILE(eligible_trip_miles, 0.50), 3) AS p50_trip_miles,
    ROUND(
        SUM(CASE WHEN speed_eligible THEN trip_miles END)
        / NULLIF(SUM(CASE WHEN speed_eligible THEN trip_time / 3600.0 END), 0),
        3
    ) AS weighted_speed_mph,

    ROUND(SUM(base_passenger_fare), 2) AS total_base_fare_reported,
    COUNT(*) FILTER (WHERE fare_eligible) AS base_fare_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE fare_eligible) / COUNT(*), 4) AS base_fare_coverage_pct,
    ROUND(AVG(eligible_base_fare), 2) AS avg_base_fare_eligible,
    ROUND(SUM(driver_pay), 2) AS total_driver_pay_reported,
    COUNT(*) FILTER (WHERE driver_pay_eligible) AS driver_pay_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE driver_pay_eligible) / COUNT(*), 4) AS driver_pay_coverage_pct,
    ROUND(AVG(eligible_driver_pay), 2) AS avg_driver_pay_eligible,
    ROUND(
        SUM(CASE WHEN fare_per_mile_eligible THEN base_passenger_fare END)
        / NULLIF(SUM(CASE WHEN fare_per_mile_eligible THEN trip_miles END), 0),
        3
    ) AS weighted_base_fare_per_mile,
    ROUND(
        SUM(CASE WHEN driver_pay_per_mile_eligible THEN driver_pay END)
        / NULLIF(SUM(CASE WHEN driver_pay_per_mile_eligible THEN trip_miles END), 0),
        3
    ) AS weighted_driver_pay_per_mile,
    ROUND(
        SUM(CASE WHEN driver_pay_per_hour_eligible THEN driver_pay END)
        / NULLIF(SUM(CASE WHEN driver_pay_per_hour_eligible THEN trip_time / 3600.0 END), 0),
        3
    ) AS driver_pay_per_occupied_hour,

    ROUND(SUM(airport_fee), 2) AS total_airport_fee_reported,
    ROUND(SUM(cbd_congestion_fee), 2) AS total_cbd_congestion_fee_reported,
    COUNT(*) FILTER (WHERE airport_fee > 0) AS airport_fee_trips,
    COUNT(*) FILTER (WHERE cbd_congestion_fee > 0) AS cbd_fee_trips,
    COUNT(*) FILTER (WHERE shared_request_flag = 'Y') AS shared_request_trips,
    COUNT(*) FILTER (WHERE shared_match_flag = 'Y') AS shared_match_trips,
    COUNT(*) FILTER (WHERE wav_request_flag = 'Y') AS wav_request_trips
FROM uber_enriched
GROUP BY pickup_date, month
ORDER BY pickup_date
"""


ZONE_DAILY_METRICS_SQL = """
SELECT
    pickup_date,
    month,
    PULocationID AS pickup_location_id,
    COUNT(*) AS trips,
    COUNT(DISTINCT DOLocationID) FILTER (WHERE NOT dropoff_zone_invalid) AS distinct_dropoff_zones,

    COUNT(*) FILTER (WHERE wait_eligible) AS wait_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE wait_eligible) / COUNT(*), 4) AS wait_coverage_pct,
    ROUND(AVG(wait_minutes), 3) AS avg_request_to_pickup_minutes,
    COUNT(*) FILTER (WHERE duration_eligible) AS duration_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE duration_eligible) / COUNT(*), 4) AS duration_coverage_pct,
    ROUND(AVG(trip_duration_minutes), 3) AS avg_trip_duration_minutes,
    COUNT(*) FILTER (WHERE distance_eligible) AS distance_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE distance_eligible) / COUNT(*), 4) AS distance_coverage_pct,
    ROUND(AVG(eligible_trip_miles), 3) AS avg_trip_miles,
    ROUND(
        SUM(CASE WHEN speed_eligible THEN trip_miles END)
        / NULLIF(SUM(CASE WHEN speed_eligible THEN trip_time / 3600.0 END), 0),
        3
    ) AS weighted_speed_mph,

    ROUND(SUM(base_passenger_fare), 2) AS total_base_fare_reported,
    COUNT(*) FILTER (WHERE fare_eligible) AS base_fare_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE fare_eligible) / COUNT(*), 4) AS base_fare_coverage_pct,
    ROUND(AVG(eligible_base_fare), 2) AS avg_base_fare_eligible,
    ROUND(SUM(driver_pay), 2) AS total_driver_pay_reported,
    COUNT(*) FILTER (WHERE driver_pay_eligible) AS driver_pay_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE driver_pay_eligible) / COUNT(*), 4) AS driver_pay_coverage_pct,
    ROUND(AVG(eligible_driver_pay), 2) AS avg_driver_pay_eligible,
    ROUND(
        SUM(CASE WHEN fare_per_mile_eligible THEN base_passenger_fare END)
        / NULLIF(SUM(CASE WHEN fare_per_mile_eligible THEN trip_miles END), 0),
        3
    ) AS weighted_base_fare_per_mile,
    ROUND(
        SUM(CASE WHEN driver_pay_per_mile_eligible THEN driver_pay END)
        / NULLIF(SUM(CASE WHEN driver_pay_per_mile_eligible THEN trip_miles END), 0),
        3
    ) AS weighted_driver_pay_per_mile,
    ROUND(
        SUM(CASE WHEN driver_pay_per_hour_eligible THEN driver_pay END)
        / NULLIF(SUM(CASE WHEN driver_pay_per_hour_eligible THEN trip_time / 3600.0 END), 0),
        3
    ) AS driver_pay_per_occupied_hour,

    COUNT(*) FILTER (WHERE airport_fee > 0) AS airport_fee_trips,
    COUNT(*) FILTER (WHERE cbd_congestion_fee > 0) AS cbd_fee_trips,
    COUNT(*) FILTER (WHERE shared_request_flag = 'Y') AS shared_request_trips,
    COUNT(*) FILTER (WHERE shared_match_flag = 'Y') AS shared_match_trips,
    COUNT(*) FILTER (WHERE wav_request_flag = 'Y') AS wav_request_trips
FROM uber_enriched
WHERE NOT pickup_zone_invalid
GROUP BY pickup_date, month, PULocationID
ORDER BY pickup_date, pickup_location_id
"""


ZONE_HOUR_METRICS_SQL = """
SELECT
    month,
    CAST(DATE_PART('isodow', pickup_datetime) AS TINYINT) AS iso_weekday,
    STRFTIME(pickup_datetime, '%A') AS weekday_name,
    CASE
        WHEN DATE_PART('isodow', pickup_datetime) IN (6, 7) THEN 'weekend'
        ELSE 'weekday'
    END AS day_type,
    CAST(DATE_PART('hour', pickup_datetime) AS TINYINT) AS pickup_hour,
    PULocationID AS pickup_location_id,
    COUNT(*) AS trips,
    COUNT(DISTINCT pickup_date) AS contributing_days,
    ROUND(COUNT(*)::DOUBLE / COUNT(DISTINCT pickup_date), 3) AS avg_trips_per_contributing_day,
    COUNT(DISTINCT DOLocationID) FILTER (WHERE NOT dropoff_zone_invalid) AS distinct_dropoff_zones,

    COUNT(*) FILTER (WHERE wait_eligible) AS wait_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE wait_eligible) / COUNT(*), 4) AS wait_coverage_pct,
    ROUND(AVG(wait_minutes), 3) AS avg_request_to_pickup_minutes,
    COUNT(*) FILTER (WHERE duration_eligible) AS duration_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE duration_eligible) / COUNT(*), 4) AS duration_coverage_pct,
    ROUND(AVG(trip_duration_minutes), 3) AS avg_trip_duration_minutes,
    COUNT(*) FILTER (WHERE distance_eligible) AS distance_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE distance_eligible) / COUNT(*), 4) AS distance_coverage_pct,
    ROUND(AVG(eligible_trip_miles), 3) AS avg_trip_miles,
    ROUND(
        SUM(CASE WHEN speed_eligible THEN trip_miles END)
        / NULLIF(SUM(CASE WHEN speed_eligible THEN trip_time / 3600.0 END), 0),
        3
    ) AS weighted_speed_mph,

    ROUND(SUM(base_passenger_fare), 2) AS total_base_fare_reported,
    COUNT(*) FILTER (WHERE fare_eligible) AS base_fare_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE fare_eligible) / COUNT(*), 4) AS base_fare_coverage_pct,
    ROUND(AVG(eligible_base_fare), 2) AS avg_base_fare_eligible,
    ROUND(SUM(driver_pay), 2) AS total_driver_pay_reported,
    COUNT(*) FILTER (WHERE driver_pay_eligible) AS driver_pay_eligible_trips,
    ROUND(100.0 * COUNT(*) FILTER (WHERE driver_pay_eligible) / COUNT(*), 4) AS driver_pay_coverage_pct,
    ROUND(AVG(eligible_driver_pay), 2) AS avg_driver_pay_eligible,
    ROUND(
        SUM(CASE WHEN fare_per_mile_eligible THEN base_passenger_fare END)
        / NULLIF(SUM(CASE WHEN fare_per_mile_eligible THEN trip_miles END), 0),
        3
    ) AS weighted_base_fare_per_mile,
    ROUND(
        SUM(CASE WHEN driver_pay_per_mile_eligible THEN driver_pay END)
        / NULLIF(SUM(CASE WHEN driver_pay_per_mile_eligible THEN trip_miles END), 0),
        3
    ) AS weighted_driver_pay_per_mile,
    ROUND(
        SUM(CASE WHEN driver_pay_per_hour_eligible THEN driver_pay END)
        / NULLIF(SUM(CASE WHEN driver_pay_per_hour_eligible THEN trip_time / 3600.0 END), 0),
        3
    ) AS driver_pay_per_occupied_hour,

    COUNT(*) FILTER (WHERE airport_fee > 0) AS airport_fee_trips,
    COUNT(*) FILTER (WHERE cbd_congestion_fee > 0) AS cbd_fee_trips,
    COUNT(*) FILTER (WHERE shared_request_flag = 'Y') AS shared_request_trips,
    COUNT(*) FILTER (WHERE shared_match_flag = 'Y') AS shared_match_trips,
    COUNT(*) FILTER (WHERE wav_request_flag = 'Y') AS wav_request_trips
FROM uber_enriched
WHERE NOT pickup_zone_invalid
GROUP BY
    month,
    DATE_PART('isodow', pickup_datetime),
    STRFTIME(pickup_datetime, '%A'),
    day_type,
    DATE_PART('hour', pickup_datetime),
    PULocationID
ORDER BY month, iso_weekday, pickup_hour, pickup_location_id
"""


TABLE_QUERIES = [
    ("data_quality_by_month", DATA_QUALITY_SQL),
    ("monthly_metrics", MONTHLY_METRICS_SQL),
    ("daily_metrics", DAILY_METRICS_SQL),
    ("zone_daily_metrics", ZONE_DAILY_METRICS_SQL),
    ("zone_hour_metrics", ZONE_HOUR_METRICS_SQL),
]


def parse_month(value: str) -> date:
    try:
        parsed = datetime.strptime(value, "%Y-%m").date()
    except ValueError as exc:
        raise argparse.ArgumentTypeError("month must use YYYY-MM format") from exc
    return parsed.replace(day=1)


def add_month(value: date) -> date:
    if value.month == 12:
        return date(value.year + 1, 1, 1)
    return date(value.year, value.month + 1, 1)


def month_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end month must not be earlier than start month")
    months: list[date] = []
    current = start
    while current <= end:
        months.append(current)
        current = add_month(current)
    return months


def sql_literal(value: str | Path) -> str:
    text = str(value).replace("\\", "/").replace("'", "''")
    return f"'{text}'"


def human_bytes(size: int) -> str:
    amount = float(size)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if amount < 1024 or unit == "TB":
            return f"{amount:.2f} {unit}"
        amount /= 1024
    raise AssertionError("unreachable")


def write_csv_atomic(path: Path, fieldnames: list[str], rows: list[dict[str, object]]) -> None:
    temp_path = path.with_name(f"_{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", newline="", encoding="utf-8-sig") as handle:
            writer = csv.DictWriter(handle, fieldnames=fieldnames)
            writer.writeheader()
            writer.writerows(rows)
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    temp_path = path.with_name(f"_{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp_path.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        os.replace(temp_path, path)
    finally:
        temp_path.unlink(missing_ok=True)


def export_table_atomic(
    con: duckdb.DuckDBPyConnection,
    table_name: str,
    target_path: Path,
    output_format: str,
) -> None:
    suffix = ".parquet" if output_format == "parquet" else ".csv"
    temp_path = target_path.with_name(f"_{target_path.stem}.{uuid.uuid4().hex}{suffix}")
    try:
        if output_format == "parquet":
            options = "FORMAT PARQUET, COMPRESSION ZSTD, ROW_GROUP_SIZE 100000"
        elif output_format == "csv":
            options = "FORMAT CSV, HEADER TRUE"
        else:
            raise ValueError(f"unsupported output format: {output_format}")
        con.execute(
            f"COPY (SELECT * FROM {table_name}) TO {sql_literal(temp_path)} ({options})"
        )
        os.replace(temp_path, target_path)
    finally:
        temp_path.unlink(missing_ok=True)


def create_metric_definitions(output_dir: Path) -> None:
    rows = [
        {
            "table_name": table_name,
            "metric_name": metric_name,
            "definition": definition,
            "eligibility_rule": eligibility_rule,
            "interpretation_note": interpretation_note,
        }
        for table_name, metric_name, definition, eligibility_rule, interpretation_note
        in METRIC_DEFINITIONS
    ]
    write_csv_atomic(
        output_dir / "metric_definitions.csv",
        [
            "table_name",
            "metric_name",
            "definition",
            "eligibility_rule",
            "interpretation_note",
        ],
        rows,
    )


def build_source_view(
    con: duckdb.DuckDBPyConnection,
    source_files: list[Path],
    start_month: date,
    end_month: date,
) -> None:
    file_list_sql = "[" + ", ".join(sql_literal(path) for path in source_files) + "]"
    source_describe = con.execute(
        f"""
        DESCRIBE
        SELECT *
        FROM read_parquet(
            {file_list_sql},
            union_by_name = TRUE,
            hive_partitioning = FALSE
        )
        """
    ).fetchall()
    source_columns = {row[0] for row in source_describe}
    missing_columns = sorted(REQUIRED_COLUMNS - source_columns)
    if missing_columns:
        raise RuntimeError(f"required source columns are missing: {missing_columns}")

    con.execute(
        f"""
        CREATE OR REPLACE VIEW uber_enriched AS
        WITH source AS (
            SELECT
                filename AS source_filename,
                request_datetime,
                on_scene_datetime,
                pickup_datetime,
                dropoff_datetime,
                PULocationID,
                DOLocationID,
                trip_miles,
                trip_time,
                base_passenger_fare,
                tolls,
                bcf,
                sales_tax,
                congestion_surcharge,
                airport_fee,
                tips,
                driver_pay,
                shared_request_flag,
                shared_match_flag,
                wav_request_flag,
                wav_match_flag,
                cbd_congestion_fee
            FROM read_parquet(
                {file_list_sql},
                union_by_name = TRUE,
                hive_partitioning = FALSE,
                filename = TRUE
            )
            WHERE hvfhs_license_num = {sql_literal(UBER_LICENSE)}
        ),
        derived AS (
            SELECT
                *,
                CAST(
                    STRPTIME(
                        REGEXP_EXTRACT(
                            source_filename,
                            'fhvhv_tripdata_([0-9]{{4}}-[0-9]{{2}})[.]parquet$',
                            1
                        ),
                        '%Y-%m'
                    )
                    AS DATE
                ) AS month,
                CAST(pickup_datetime AS DATE) AS pickup_date,
                DATE_DIFF('second', request_datetime, pickup_datetime) / 60.0
                    AS request_to_pickup_minutes_raw,
                DATE_DIFF('second', pickup_datetime, dropoff_datetime)
                    AS timestamp_trip_seconds,
                CASE
                    WHEN trip_time > 0 AND trip_miles > 0
                    THEN trip_miles / (trip_time / 3600.0)
                END AS speed_mph_raw
            FROM source
        ),
        flags AS (
            SELECT
                *,
                request_datetime IS NOT NULL
                    AND pickup_datetime IS NOT NULL
                    AND request_to_pickup_minutes_raw BETWEEN 0 AND 60
                    AS wait_eligible,
                trip_time IS NOT NULL
                    AND trip_time > 0
                    AND pickup_datetime IS NOT NULL
                    AND dropoff_datetime IS NOT NULL
                    AND dropoff_datetime > pickup_datetime
                    AS duration_eligible,
                trip_miles IS NOT NULL AND trip_miles > 0 AS distance_eligible,
                base_passenger_fare IS NOT NULL AND base_passenger_fare >= 0 AS fare_eligible,
                driver_pay IS NOT NULL AND driver_pay >= 0 AS driver_pay_eligible,
                PULocationID IS NULL OR PULocationID NOT BETWEEN 1 AND 265
                    AS pickup_zone_invalid,
                DOLocationID IS NULL OR DOLocationID NOT BETWEEN 1 AND 265
                    AS dropoff_zone_invalid,
                trip_time IS NOT NULL
                    AND pickup_datetime IS NOT NULL
                    AND dropoff_datetime IS NOT NULL
                    AND ABS(trip_time - timestamp_trip_seconds) > 60
                    AS trip_time_mismatch_gt_60sec
            FROM derived
        )
        SELECT
            *,
            duration_eligible AND distance_eligible AS speed_eligible,
            fare_eligible AND distance_eligible AS fare_per_mile_eligible,
            driver_pay_eligible AND distance_eligible AS driver_pay_per_mile_eligible,
            driver_pay_eligible AND duration_eligible AS driver_pay_per_hour_eligible,
            CASE WHEN wait_eligible THEN request_to_pickup_minutes_raw END AS wait_minutes,
            CASE WHEN duration_eligible THEN trip_time / 60.0 END AS trip_duration_minutes,
            CASE WHEN distance_eligible THEN trip_miles END AS eligible_trip_miles,
            CASE WHEN fare_eligible THEN base_passenger_fare END AS eligible_base_fare,
            CASE WHEN driver_pay_eligible THEN driver_pay END AS eligible_driver_pay
        FROM flags
        """
    )


def build_table(
    con: duckdb.DuckDBPyConnection,
    output_dir: Path,
    table_name: str,
    query: str,
) -> tuple[int, float]:
    started = time.perf_counter()
    print(f"\n[BUILD] {table_name}", flush=True)
    con.execute(f"CREATE OR REPLACE TEMP TABLE {table_name} AS {query}")
    row_count = con.execute(f"SELECT COUNT(*) FROM {table_name}").fetchone()[0]
    export_table_atomic(con, table_name, output_dir / f"{table_name}.parquet", "parquet")
    if table_name == "data_quality_by_month":
        export_table_atomic(con, table_name, output_dir / f"{table_name}.csv", "csv")
    con.execute(f"DROP TABLE {table_name}")
    elapsed = time.perf_counter() - started
    print(f"[DONE ] {table_name}: {row_count:,} rows in {elapsed:,.1f}s", flush=True)
    return row_count, elapsed


def validate_outputs(
    con: duckdb.DuckDBPyConnection,
    output_dir: Path,
    expected_months: int,
) -> list[dict[str, object]]:
    paths = {
        name: output_dir / f"{name}.parquet"
        for name, _ in TABLE_QUERIES
    }

    def scalar(sql: str) -> object:
        return con.execute(sql).fetchone()[0]

    monthly = sql_literal(paths["monthly_metrics"])
    daily = sql_literal(paths["daily_metrics"])
    quality = sql_literal(paths["data_quality_by_month"])
    zone_daily = sql_literal(paths["zone_daily_metrics"])
    zone_hour = sql_literal(paths["zone_hour_metrics"])

    monthly_trips = int(scalar(f"SELECT SUM(trips) FROM read_parquet({monthly})"))
    daily_trips = int(scalar(f"SELECT SUM(trips) FROM read_parquet({daily})"))
    quality_trips = int(scalar(f"SELECT SUM(trips) FROM read_parquet({quality})"))
    valid_zone_trips = int(
        scalar(
            f"""
            SELECT SUM(pickup_zone_eligible_trips)
            FROM read_parquet({quality})
            """
        )
    )
    zone_daily_trips = int(scalar(f"SELECT SUM(trips) FROM read_parquet({zone_daily})"))
    zone_hour_trips = int(scalar(f"SELECT SUM(trips) FROM read_parquet({zone_hour})"))

    checks: list[dict[str, object]] = []

    def add_check(name: str, actual: object, expected: object, passed: bool) -> None:
        checks.append(
            {
                "check_name": name,
                "actual": actual,
                "expected": expected,
                "passed": passed,
            }
        )

    monthly_rows = int(scalar(f"SELECT COUNT(*) FROM read_parquet({monthly})"))
    quality_rows = int(scalar(f"SELECT COUNT(*) FROM read_parquet({quality})"))
    add_check("monthly row count", monthly_rows, expected_months, monthly_rows == expected_months)
    add_check("quality row count", quality_rows, expected_months, quality_rows == expected_months)
    add_check("monthly trips equal daily trips", monthly_trips, daily_trips, monthly_trips == daily_trips)
    add_check("monthly trips equal quality trips", monthly_trips, quality_trips, monthly_trips == quality_trips)
    add_check(
        "valid-zone trips equal zone_daily trips",
        valid_zone_trips,
        zone_daily_trips,
        valid_zone_trips == zone_daily_trips,
    )
    add_check(
        "valid-zone trips equal zone_hour trips",
        valid_zone_trips,
        zone_hour_trips,
        valid_zone_trips == zone_hour_trips,
    )

    duplicate_queries = {
        "monthly key uniqueness": f"""
            SELECT COUNT(*) - COUNT(DISTINCT month)
            FROM read_parquet({monthly})
        """,
        "daily key uniqueness": f"""
            SELECT COUNT(*) - COUNT(DISTINCT pickup_date)
            FROM read_parquet({daily})
        """,
        "zone_daily key uniqueness": f"""
            SELECT COUNT(*) - COUNT(DISTINCT (pickup_date, pickup_location_id))
            FROM read_parquet({zone_daily})
        """,
        "zone_hour key uniqueness": f"""
            SELECT COUNT(*) - COUNT(DISTINCT (month, iso_weekday, pickup_hour, pickup_location_id))
            FROM read_parquet({zone_hour})
        """,
    }
    for check_name, query in duplicate_queries.items():
        duplicate_count = int(scalar(query))
        add_check(check_name, duplicate_count, 0, duplicate_count == 0)

    missing_days = int(
        scalar(f"SELECT COALESCE(SUM(missing_pickup_days), 0) FROM read_parquet({quality})")
    )
    add_check("complete pickup-day coverage", missing_days, 0, missing_days == 0)

    write_csv_atomic(
        output_dir / "build_validation.csv",
        ["check_name", "actual", "expected", "passed"],
        checks,
    )

    failed = [row for row in checks if not row["passed"]]
    if failed:
        failures = "; ".join(str(row["check_name"]) for row in failed)
        raise RuntimeError(f"output validation failed: {failures}")
    return checks


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
        help="Repository root.",
    )
    parser.add_argument(
        "--raw-dir",
        type=Path,
        default=None,
        help="Directory containing monthly fhvhv_tripdata_YYYY-MM.parquet files; defaults to <project-dir>/data/raw.",
    )
    parser.add_argument("--start-month", type=parse_month, default=parse_month(DEFAULT_START_MONTH))
    parser.add_argument("--end-month", type=parse_month, default=parse_month(DEFAULT_END_MONTH))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=None,
        help="Output directory; defaults to <project-dir>/data/processed/analytics.",
    )
    parser.add_argument("--memory-limit", default=DEFAULT_MEMORY_LIMIT)
    parser.add_argument("--threads", type=int, default=DEFAULT_THREADS)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.resolve()
    raw_dir = (args.raw_dir or project_dir / "data" / "raw").resolve()
    output_dir = (
        args.output_dir or project_dir / "data" / "processed" / "analytics"
    ).resolve()
    months = month_range(args.start_month, args.end_month)
    expected_files = [
        raw_dir / f"fhvhv_tripdata_{month:%Y-%m}.parquet"
        for month in months
    ]
    missing_files = [path for path in expected_files if not path.is_file()]
    if missing_files:
        formatted = "\n".join(f"  - {path}" for path in missing_files)
        raise FileNotFoundError(f"missing expected source files:\n{formatted}")

    output_dir.mkdir(parents=True, exist_ok=True)
    source_bytes = sum(path.stat().st_size for path in expected_files)
    started_at = datetime.now(timezone.utc)
    started = time.perf_counter()

    print("=" * 88)
    print("UBER NYC ANALYTICS LAYER BUILD")
    print("=" * 88)
    print(f"Project        : {project_dir}")
    print(f"Source window  : {args.start_month:%Y-%m} to {args.end_month:%Y-%m}")
    print(f"Source files   : {len(expected_files)} ({human_bytes(source_bytes)})")
    print(f"Platform filter: {UBER_LICENSE}")
    print(f"Output         : {output_dir}")
    print(f"DuckDB         : {duckdb.__version__}")
    print(f"Memory / thread: {args.memory_limit} / {args.threads}")

    table_stats: dict[str, dict[str, object]] = {}
    validation: list[dict[str, object]] = []

    with tempfile.TemporaryDirectory(prefix="duckdb-build-", dir=output_dir) as temp_dir_name:
        con = duckdb.connect(database=":memory:")
        try:
            con.execute(f"SET threads = {max(1, args.threads)}")
            con.execute(f"SET memory_limit = {sql_literal(args.memory_limit)}")
            con.execute(f"SET temp_directory = {sql_literal(Path(temp_dir_name))}")
            con.execute("SET preserve_insertion_order = FALSE")
            build_source_view(con, expected_files, args.start_month, args.end_month)
            create_metric_definitions(output_dir)

            for table_name, query in TABLE_QUERIES:
                row_count, elapsed_seconds = build_table(con, output_dir, table_name, query)
                target = output_dir / f"{table_name}.parquet"
                table_stats[table_name] = {
                    "rows": row_count,
                    "elapsed_seconds": round(elapsed_seconds, 3),
                    "file": target.name,
                    "bytes": target.stat().st_size,
                }

            print("\n[CHECK] validating grains, keys, and trip reconciliation", flush=True)
            validation = validate_outputs(con, output_dir, len(months))
            print(f"[DONE ] {len(validation)} validation checks passed", flush=True)
        finally:
            con.close()

    completed_at = datetime.now(timezone.utc)
    elapsed_seconds = time.perf_counter() - started
    manifest = {
        "build_name": "Uber NYC analytics layer",
        "started_at_utc": started_at.isoformat(),
        "completed_at_utc": completed_at.isoformat(),
        "elapsed_seconds": round(elapsed_seconds, 3),
        "repository_paths": {
            "raw_input": "data/raw (or --raw-dir; source files are not committed)",
            "output": (
                output_dir.relative_to(project_dir).as_posix()
                if output_dir.is_relative_to(project_dir)
                else output_dir.name
            ),
        },
        "source_window": {
            "start_month": args.start_month.strftime("%Y-%m"),
            "end_month": args.end_month.strftime("%Y-%m"),
            "month_count": len(months),
        },
        "platform_filter": UBER_LICENSE,
        "source_files": [
            {
                "name": path.name,
                "bytes": path.stat().st_size,
                "modified_at_utc": datetime.fromtimestamp(
                    path.stat().st_mtime, tz=timezone.utc
                ).isoformat(),
            }
            for path in expected_files
        ],
        "engine": {
            "python": sys.version.split()[0],
            "python_implementation": platform.python_implementation(),
            "duckdb": duckdb.__version__,
            "memory_limit": args.memory_limit,
            "threads": max(1, args.threads),
        },
        "tables": table_stats,
        "validation_checks": validation,
        "metric_policy": {
            "row_deletion": "none; metric-specific eligibility only",
            "wait": "0 to 60 minutes inclusive",
            "duration": "trip_time > 0 and dropoff_datetime > pickup_datetime",
            "distance": "trip_miles > 0",
            "fare_distribution": "base_passenger_fare >= 0",
            "driver_pay_distribution": "driver_pay >= 0",
            "on_scene_datetime": "quality monitoring only, not a core KPI",
            "fare_minus_driver_pay": "not calculated or interpreted as platform economics",
        },
    }
    write_json_atomic(output_dir / "build_manifest.json", manifest)

    print("\n" + "=" * 88)
    print("BUILD COMPLETE")
    print("=" * 88)
    for name, stats in table_stats.items():
        print(
            f"{name:<30} {int(stats['rows']):>10,} rows  "
            f"{human_bytes(int(stats['bytes'])):>10}"
        )
    print(f"Elapsed: {elapsed_seconds:,.1f}s")
    print(f"Output : {output_dir}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
