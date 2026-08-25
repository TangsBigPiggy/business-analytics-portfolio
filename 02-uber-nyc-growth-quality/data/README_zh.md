# 数据包说明

[**English**](README.md) | [**中文**](README_zh.md)

公开仓库仅保留检查与复现已发布分析所需的文件：

- `reference/taxi_zone_lookup.csv` — NYC TLC 出租车分区名称。
- `processed/analytics/` — 由 13 个月原始文件构建的紧凑 DuckDB 分析数据集。
- `processed/analysis/` — 报告与 Dashboard 使用的已验证同比、分解、区域、小时段与优先级输出。

公共数据支持完成行程与服务代理指标分析，但不观测未服务请求、取消、司机在线时长、派单接受率、动态加价、预约或促销。“供给受限优先级代理”仅用于运营排序，不构成因果证明；乘客基础车费与司机报酬是两个独立指标，二者之差不代表利润、利润率或抽成率。

## 原始数据

13 个源文件合计约 6.13 GB，因此不纳入 Git。使用以下命令下载 2025 年 5 月至 2026 年 5 月的 NYC TLC High Volume For-Hire Vehicle Parquet 文件：

```bash
python scripts/00_download_tlc_data.py
```

文件写入已被 `.gitignore` 排除的 `data/raw/`。直接文件路径规则为：

```text
https://d37ci6vzurychx.cloudfront.net/trip-data/fhvhv_tripdata_YYYY-MM.parquet
```

官方文档：

- [NYC TLC Trip Record Data](https://www.nyc.gov/site/tlc/about/tlc-trip-record-data.page)
- [High Volume FHV data dictionary](https://www.nyc.gov/assets/tlc/downloads/pdf/data_dictionary_trip_records_hvfhs.pdf)
- [Taxi Zone Lookup Table](https://d37ci6vzurychx.cloudfront.net/misc/taxi_zone_lookup.csv)
