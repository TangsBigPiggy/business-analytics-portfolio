"""Download the 13 monthly NYC TLC HVFHV Parquet files used in this project."""

from __future__ import annotations

import argparse
import os
import urllib.request
import uuid
from datetime import date, datetime
from pathlib import Path


URL_TEMPLATE = (
    "https://d37ci6vzurychx.cloudfront.net/trip-data/"
    "fhvhv_tripdata_{month}.parquet"
)


def parse_month(value: str) -> date:
    return datetime.strptime(value, "%Y-%m").date().replace(day=1)


def month_range(start: date, end: date) -> list[date]:
    if end < start:
        raise ValueError("end month must be on or after start month")
    months: list[date] = []
    cursor = start
    while cursor <= end:
        months.append(cursor)
        cursor = date(cursor.year + (cursor.month == 12), cursor.month % 12 + 1, 1)
    return months


def parse_args() -> argparse.Namespace:
    project_dir = Path(__file__).resolve().parents[1]
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--start-month", type=parse_month, default=parse_month("2025-05"))
    parser.add_argument("--end-month", type=parse_month, default=parse_month("2026-05"))
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=project_dir / "data" / "raw",
        help="Destination for the monthly Parquet files.",
    )
    parser.add_argument(
        "--force",
        action="store_true",
        help="Replace files that already exist instead of skipping them.",
    )
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    output_dir = args.output_dir.resolve()
    output_dir.mkdir(parents=True, exist_ok=True)
    months = month_range(args.start_month, args.end_month)

    print(f"Downloading {len(months)} monthly HVFHV files to {output_dir}")
    for index, month in enumerate(months, start=1):
        month_label = month.strftime("%Y-%m")
        filename = f"fhvhv_tripdata_{month_label}.parquet"
        target = output_dir / filename
        if target.is_file() and not args.force:
            print(f"[{index:02d}/{len(months):02d}] SKIP {filename}")
            continue

        url = URL_TEMPLATE.format(month=month_label)
        temp = target.with_name(f"_{target.name}.{uuid.uuid4().hex}.part")
        print(f"[{index:02d}/{len(months):02d}] GET  {filename}", flush=True)
        try:
            urllib.request.urlretrieve(url, temp)
            os.replace(temp, target)
        finally:
            temp.unlink(missing_ok=True)

    print("Download complete. Raw files remain ignored by Git.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

