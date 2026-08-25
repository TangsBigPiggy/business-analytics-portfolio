"""Inspect one NYC TLC HVFHV Parquet file before running the full pipeline."""

from __future__ import annotations

import argparse
from pathlib import Path

import duckdb


UBER_LICENSE = "HV0003"
DEFAULT_FILE = "fhvhv_tripdata_2025-05.parquet"


def sql_literal(path: Path) -> str:
    return "'" + path.as_posix().replace("'", "''") + "'"


def parse_args() -> argparse.Namespace:
    project_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--input",
        type=Path,
        default=project_dir / "data" / "raw" / DEFAULT_FILE,
        help="Path to one TLC HVFHV Parquet file.",
    )
    return parser.parse_args()


def main() -> int:
    source = parse_args().input.resolve()
    if not source.is_file():
        raise FileNotFoundError(
            f"Input file not found: {source}\n"
            "Download the TLC file into data/raw or pass --input explicitly."
        )

    con = duckdb.connect(database=":memory:")
    try:
        source_sql = sql_literal(source)
        print("\n========== SCHEMA ==========")
        print(
            con.execute(f"DESCRIBE SELECT * FROM read_parquet({source_sql})")
            .df()
            .to_string(index=False)
        )

        print("\n========== ROW COUNT ==========")
        print(
            con.execute(
                f"SELECT COUNT(*) AS total_rows FROM read_parquet({source_sql})"
            )
            .df()
            .to_string(index=False)
        )

        print("\n========== SAMPLE ==========")
        print(
            con.execute(f"SELECT * FROM read_parquet({source_sql}) LIMIT 10")
            .df()
            .to_string(index=False)
        )

        print("\n========== PLATFORM DISTRIBUTION ==========")
        print(
            con.execute(
                f"""
                SELECT
                    hvfhs_license_num,
                    COUNT(*) AS trips,
                    ROUND(COUNT(*) * 100.0 / SUM(COUNT(*)) OVER (), 2) AS share_pct
                FROM read_parquet({source_sql})
                GROUP BY hvfhs_license_num
                ORDER BY trips DESC
                """
            )
            .df()
            .to_string(index=False)
        )

        print("\n========== DATE RANGE ==========")
        print(
            con.execute(
                f"""
                SELECT
                    MIN(pickup_datetime) AS first_pickup,
                    MAX(pickup_datetime) AS last_pickup,
                    MIN(dropoff_datetime) AS first_dropoff,
                    MAX(dropoff_datetime) AS last_dropoff
                FROM read_parquet({source_sql})
                """
            )
            .df()
            .to_string(index=False)
        )

        print("\n========== UBER BASIC PROFILE ==========")
        print(
            con.execute(
                f"""
                SELECT
                    COUNT(*) AS trips,
                    ROUND(AVG(trip_miles), 2) AS avg_trip_miles,
                    ROUND(MEDIAN(trip_miles), 2) AS median_trip_miles,
                    ROUND(AVG(trip_time) / 60.0, 2) AS avg_trip_minutes,
                    ROUND(AVG(base_passenger_fare), 2) AS avg_base_fare,
                    ROUND(AVG(driver_pay), 2) AS avg_driver_pay
                FROM read_parquet({source_sql})
                WHERE hvfhs_license_num = '{UBER_LICENSE}'
                """
            )
            .df()
            .to_string(index=False)
        )
    finally:
        con.close()

    print("\n========== INSPECTION COMPLETE ==========")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
