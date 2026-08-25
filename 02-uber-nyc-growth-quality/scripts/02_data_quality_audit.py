import argparse
from pathlib import Path

import duckdb
import pandas as pd


# ============================================================
# PATH
# ============================================================

DEFAULT_PROJECT_DIR = Path(__file__).resolve().parents[1]

parser = argparse.ArgumentParser(description="Run a detailed quality audit on one monthly HVFHV file.")
parser.add_argument(
    "--input",
    type=Path,
    default=DEFAULT_PROJECT_DIR / "data" / "raw" / "fhvhv_tripdata_2025-05.parquet",
    help="Path to one TLC HVFHV Parquet file.",
)
parser.add_argument(
    "--output-dir",
    type=Path,
    default=DEFAULT_PROJECT_DIR / "data" / "quality_audit",
    help="Directory for CSV audit outputs.",
)
args = parser.parse_args()

FILE = args.input.resolve()
OUTPUT_DIR = args.output_dir.resolve()
if not FILE.is_file():
    raise FileNotFoundError(
        f"Input file not found: {FILE}\n"
        "Download the TLC file into data/raw or pass --input explicitly."
    )
OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

FILE_SQL = str(FILE).replace("\\", "/")


# ============================================================
# DUCKDB
# ============================================================

con = duckdb.connect()

con.execute(f"""
CREATE OR REPLACE VIEW uber AS
SELECT *
FROM read_parquet('{FILE_SQL}')
WHERE hvfhs_license_num = 'HV0003'
""")


# ============================================================
# 1. BASIC COUNT
# ============================================================

print("\n" + "=" * 90)
print("1. BASIC COUNT")
print("=" * 90)

basic = con.execute("""
SELECT
    COUNT(*) AS trips,
    COUNT(DISTINCT DATE(pickup_datetime)) AS pickup_days,
    MIN(pickup_datetime) AS min_pickup,
    MAX(pickup_datetime) AS max_pickup
FROM uber
""").df()

print(basic.to_string(index=False))


# ============================================================
# 2. NULL PROFILE
# ============================================================

print("\n" + "=" * 90)
print("2. NULL PROFILE")
print("=" * 90)

columns = [
    row[0]
    for row in con.execute("""
        DESCRIBE SELECT * FROM uber
    """).fetchall()
]

null_sql_parts = []

for col in columns:
    null_sql_parts.append(
        f"""
        SUM(CASE WHEN "{col}" IS NULL THEN 1 ELSE 0 END)
        AS "{col}"
        """
    )

null_query = f"""
SELECT
    {",".join(null_sql_parts)}
FROM uber
"""

null_counts = con.execute(null_query).df()

total_rows = basic.loc[0, "trips"]

null_profile = pd.DataFrame({
    "column": null_counts.columns,
    "null_count": null_counts.iloc[0].values
})

null_profile["null_pct"] = (
    null_profile["null_count"]
    / total_rows
    * 100
).round(4)

null_profile = null_profile.sort_values(
    "null_pct",
    ascending=False
)

print(null_profile.to_string(index=False))

null_profile.to_csv(
    OUTPUT_DIR / "01_null_profile.csv",
    index=False
)


# ============================================================
# 3. DATETIME INTEGRITY
# ============================================================

print("\n" + "=" * 90)
print("3. DATETIME INTEGRITY")
print("=" * 90)

datetime_checks = con.execute("""
SELECT

    COUNT(*) AS total_trips,

    COUNT(*) FILTER (
        WHERE request_datetime IS NULL
    ) AS request_null,

    COUNT(*) FILTER (
        WHERE pickup_datetime IS NULL
    ) AS pickup_null,

    COUNT(*) FILTER (
        WHERE dropoff_datetime IS NULL
    ) AS dropoff_null,

    COUNT(*) FILTER (
        WHERE request_datetime > pickup_datetime
    ) AS request_after_pickup,

    COUNT(*) FILTER (
        WHERE dropoff_datetime <= pickup_datetime
    ) AS invalid_dropoff,

    COUNT(*) FILTER (
        WHERE on_scene_datetime IS NOT NULL
          AND on_scene_datetime < request_datetime
    ) AS scene_before_request,

    COUNT(*) FILTER (
        WHERE on_scene_datetime IS NOT NULL
          AND on_scene_datetime > pickup_datetime
    ) AS scene_after_pickup,

    COUNT(*) FILTER (
        WHERE ABS(
            trip_time -
            DATE_DIFF(
                'second',
                pickup_datetime,
                dropoff_datetime
            )
        ) > 60
    ) AS trip_time_mismatch_gt_60sec

FROM uber
""").df()

print(datetime_checks.to_string(index=False))

datetime_checks.to_csv(
    OUTPUT_DIR / "02_datetime_integrity.csv",
    index=False
)


# ============================================================
# 4. NUMERIC / LOGICAL CHECKS
# ============================================================

print("\n" + "=" * 90)
print("4. NUMERIC / LOGICAL CHECKS")
print("=" * 90)

numeric_checks = con.execute("""
SELECT

    COUNT(*) AS total_trips,

    COUNT(*) FILTER (
        WHERE trip_miles < 0
    ) AS negative_miles,

    COUNT(*) FILTER (
        WHERE trip_miles = 0
    ) AS zero_miles,

    COUNT(*) FILTER (
        WHERE trip_time < 0
    ) AS negative_trip_time,

    COUNT(*) FILTER (
        WHERE trip_time = 0
    ) AS zero_trip_time,

    COUNT(*) FILTER (
        WHERE base_passenger_fare < 0
    ) AS negative_base_fare,

    COUNT(*) FILTER (
        WHERE base_passenger_fare = 0
    ) AS zero_base_fare,

    COUNT(*) FILTER (
        WHERE driver_pay < 0
    ) AS negative_driver_pay,

    COUNT(*) FILTER (
        WHERE driver_pay = 0
    ) AS zero_driver_pay,

    COUNT(*) FILTER (
        WHERE driver_pay > base_passenger_fare
    ) AS driver_pay_gt_base_fare,

    COUNT(*) FILTER (
        WHERE PULocationID IS NULL
    ) AS pickup_zone_null,

    COUNT(*) FILTER (
        WHERE DOLocationID IS NULL
    ) AS dropoff_zone_null,

    COUNT(*) FILTER (
        WHERE PULocationID <= 0
           OR PULocationID > 265
    ) AS pickup_zone_outside_expected_range,

    COUNT(*) FILTER (
        WHERE DOLocationID <= 0
           OR DOLocationID > 265
    ) AS dropoff_zone_outside_expected_range

FROM uber
""").df()

print(numeric_checks.to_string(index=False))

numeric_checks.to_csv(
    OUTPUT_DIR / "03_numeric_integrity.csv",
    index=False
)


# ============================================================
# 5. DERIVED OPERATIONAL METRICS
# ============================================================

print("\n" + "=" * 90)
print("5. OPERATIONAL METRIC CHECKS")
print("=" * 90)

operational_checks = con.execute("""
WITH derived AS (

    SELECT

        DATE_DIFF(
            'second',
            request_datetime,
            pickup_datetime
        ) / 60.0 AS wait_minutes,

        CASE
            WHEN on_scene_datetime IS NOT NULL
            THEN DATE_DIFF(
                'second',
                request_datetime,
                on_scene_datetime
            ) / 60.0
        END AS driver_arrival_minutes,

        CASE
            WHEN on_scene_datetime IS NOT NULL
            THEN DATE_DIFF(
                'second',
                on_scene_datetime,
                pickup_datetime
            ) / 60.0
        END AS curb_wait_minutes,

        trip_time / 60.0 AS trip_minutes,

        CASE
            WHEN trip_time > 0
            THEN trip_miles /
                 (trip_time / 3600.0)
        END AS avg_speed_mph,

        trip_miles,

        base_passenger_fare,

        driver_pay,

        base_passenger_fare
        - driver_pay AS fare_driver_pay_spread

    FROM uber

)

SELECT

    COUNT(*) AS trips,

    COUNT(*) FILTER (
        WHERE wait_minutes < 0
    ) AS negative_wait,

    COUNT(*) FILTER (
        WHERE wait_minutes > 30
    ) AS wait_gt_30min,

    COUNT(*) FILTER (
        WHERE wait_minutes > 60
    ) AS wait_gt_60min,

    COUNT(*) FILTER (
        WHERE wait_minutes > 120
    ) AS wait_gt_120min,

    COUNT(*) FILTER (
        WHERE avg_speed_mph > 60
    ) AS speed_gt_60mph,

    COUNT(*) FILTER (
        WHERE avg_speed_mph > 80
    ) AS speed_gt_80mph,

    COUNT(*) FILTER (
        WHERE avg_speed_mph > 100
    ) AS speed_gt_100mph,

    COUNT(*) FILTER (
        WHERE trip_miles > 50
    ) AS miles_gt_50,

    COUNT(*) FILTER (
        WHERE trip_miles > 100
    ) AS miles_gt_100

FROM derived
""").df()

print(operational_checks.to_string(index=False))

operational_checks.to_csv(
    OUTPUT_DIR / "04_operational_checks.csv",
    index=False
)


# ============================================================
# 6. DISTRIBUTION / PERCENTILES
# ============================================================

print("\n" + "=" * 90)
print("6. DISTRIBUTION / PERCENTILES")
print("=" * 90)

percentiles = con.execute("""
WITH derived AS (

    SELECT

        DATE_DIFF(
            'second',
            request_datetime,
            pickup_datetime
        ) / 60.0 AS wait_minutes,

        CASE
            WHEN on_scene_datetime IS NOT NULL
            THEN DATE_DIFF(
                'second',
                request_datetime,
                on_scene_datetime
            ) / 60.0
        END AS driver_arrival_minutes,

        CASE
            WHEN on_scene_datetime IS NOT NULL
            THEN DATE_DIFF(
                'second',
                on_scene_datetime,
                pickup_datetime
            ) / 60.0
        END AS curb_wait_minutes,

        trip_miles,

        trip_time / 60.0 AS trip_minutes,

        CASE
            WHEN trip_time > 0
            THEN trip_miles /
                 (trip_time / 3600.0)
        END AS avg_speed_mph,

        base_passenger_fare,

        driver_pay,

        base_passenger_fare
        - driver_pay AS fare_driver_pay_spread

    FROM uber

)

SELECT

    ROUND(
        APPROX_QUANTILE(wait_minutes, 0.50),
        2
    ) AS wait_p50,

    ROUND(
        APPROX_QUANTILE(wait_minutes, 0.90),
        2
    ) AS wait_p90,

    ROUND(
        APPROX_QUANTILE(wait_minutes, 0.95),
        2
    ) AS wait_p95,

    ROUND(
        APPROX_QUANTILE(wait_minutes, 0.99),
        2
    ) AS wait_p99,

    ROUND(
        APPROX_QUANTILE(trip_miles, 0.50),
        2
    ) AS miles_p50,

    ROUND(
        APPROX_QUANTILE(trip_miles, 0.90),
        2
    ) AS miles_p90,

    ROUND(
        APPROX_QUANTILE(trip_miles, 0.95),
        2
    ) AS miles_p95,

    ROUND(
        APPROX_QUANTILE(trip_miles, 0.99),
        2
    ) AS miles_p99,

    ROUND(
        APPROX_QUANTILE(trip_minutes, 0.50),
        2
    ) AS trip_minutes_p50,

    ROUND(
        APPROX_QUANTILE(trip_minutes, 0.95),
        2
    ) AS trip_minutes_p95,

    ROUND(
        APPROX_QUANTILE(avg_speed_mph, 0.50),
        2
    ) AS speed_p50,

    ROUND(
        APPROX_QUANTILE(avg_speed_mph, 0.95),
        2
    ) AS speed_p95,

    ROUND(
        APPROX_QUANTILE(avg_speed_mph, 0.99),
        2
    ) AS speed_p99,

    ROUND(
        APPROX_QUANTILE(base_passenger_fare, 0.50),
        2
    ) AS fare_p50,

    ROUND(
        APPROX_QUANTILE(base_passenger_fare, 0.95),
        2
    ) AS fare_p95,

    ROUND(
        APPROX_QUANTILE(base_passenger_fare, 0.99),
        2
    ) AS fare_p99,

    ROUND(
        APPROX_QUANTILE(driver_pay, 0.50),
        2
    ) AS driver_pay_p50,

    ROUND(
        APPROX_QUANTILE(driver_pay, 0.95),
        2
    ) AS driver_pay_p95,

    ROUND(
        APPROX_QUANTILE(driver_pay, 0.99),
        2
    ) AS driver_pay_p99

FROM derived
""").df()

print(percentiles.to_string(index=False))

percentiles.to_csv(
    OUTPUT_DIR / "05_percentiles.csv",
    index=False
)


# ============================================================
# 7. FLAG DISTRIBUTION
# ============================================================

print("\n" + "=" * 90)
print("7. FLAG DISTRIBUTION")
print("=" * 90)

flags = con.execute("""
SELECT
    shared_request_flag,
    shared_match_flag,
    access_a_ride_flag,
    wav_request_flag,
    wav_match_flag,
    COUNT(*) AS trips
FROM uber
GROUP BY
    shared_request_flag,
    shared_match_flag,
    access_a_ride_flag,
    wav_request_flag,
    wav_match_flag
ORDER BY trips DESC
""").df()

print(flags.head(30).to_string(index=False))

flags.to_csv(
    OUTPUT_DIR / "06_flag_distribution.csv",
    index=False
)


print("\n" + "=" * 90)
print("AUDIT COMPLETE")
print("=" * 90)

print(f"\nResults saved to:\n{OUTPUT_DIR}")
