# Data package

[**English**](README.md) | [**中文**](README_zh.md)

The public repository keeps only the files needed to inspect and reproduce the published analysis:

- `reference/taxi_zone_lookup.csv` — NYC TLC taxi-zone labels.
- `processed/analytics/` — compact DuckDB marts built from the 13 monthly source files.
- `processed/analysis/` — validated comparison, decomposition, zone, hour, and priority outputs used by the report and dashboard.

The public data supports completed-trip and service-proxy analysis. It does not observe unserved requests, cancellations, driver online time, dispatch acceptance, surge, reservations, or promotions. “Supply-constrained priority” is an operating-priority proxy, not causal proof; passenger base fare and driver pay remain separate measures and their difference is not profit, margin, or take rate.

## Raw data

The 13 source files total approximately 6.13 GB and are intentionally excluded from Git. Download the NYC TLC High Volume For-Hire Vehicle Parquet files for May 2025 through May 2026 with:

```bash
python scripts/00_download_tlc_data.py
```

Files are written to `data/raw/`, which is ignored by `.gitignore`. The direct file pattern is:

```text
https://d37ci6vzurychx.cloudfront.net/trip-data/fhvhv_tripdata_YYYY-MM.parquet
```

Official documentation:

- [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
- [High Volume FHV data dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_hvfhs.pdf)
- [Taxi Zone Lookup Table](https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv)
