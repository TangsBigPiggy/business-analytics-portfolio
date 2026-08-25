# Reproduction Guide

[**English**](REPRODUCTION.md) | [**中文**](REPRODUCTION_zh.md)

Python 3.11 or newer is recommended.

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

Fast rebuild from checked-in aggregate marts:

```bash
python scripts/04_deep_analysis.py
python scripts/05_build_executive_report.py
python scripts/07_build_bilingual_delivery.py
python scripts/06_build_final_dashboard.py
python scripts/run_final_audit.py
```

Full rebuild from raw TLC records:

```bash
python scripts/00_download_tlc_data.py
python scripts/01_inspect_parquet.py
python scripts/02_data_quality_audit.py
python scripts/03_build_analytics_layer.py
python scripts/04_deep_analysis.py
python scripts/05_build_executive_report.py
python scripts/07_build_bilingual_delivery.py
python scripts/06_build_final_dashboard.py
python scripts/run_final_audit.py
```

`data/raw/` is ignored by Git. The bilingual delivery script asserts identical numeric evidence and section order between the two report artifacts before rendering.
