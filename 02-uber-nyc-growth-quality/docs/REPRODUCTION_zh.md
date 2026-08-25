# 复现指南

[**English**](REPRODUCTION.md) | [**中文**](REPRODUCTION_zh.md)

建议使用 Python 3.11 或更高版本。

```bash
python -m venv .venv
python -m pip install -r requirements.txt
```

基于仓库中的聚合数据快速重建：

```bash
python scripts/04_deep_analysis.py
python scripts/05_build_executive_report.py
python scripts/07_build_bilingual_delivery.py
python scripts/06_build_final_dashboard.py
python scripts/run_final_audit.py
```

从原始 TLC 记录完整重建：

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

`data/raw/` 已被 Git 忽略。双语交付脚本会在渲染前验证两份报告 artifact 的数字证据与章节顺序完全一致。
