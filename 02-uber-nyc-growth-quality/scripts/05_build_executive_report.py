"""Build the English executive-report artifact from Uber NYC analysis outputs.

This script authors the canonical Data Analytics artifact JSON. The packaged
report builder then validates the artifact and produces the final self-contained
HTML reader.
"""

from __future__ import annotations

import argparse
import json
import os
import uuid
from datetime import datetime, timezone
from pathlib import Path

import duckdb


TITLE = "Uber NYC Growth Quality Review"


def read_rows(con: duckdb.DuckDBPyConnection, path: Path, sql: str) -> list[dict[str, object]]:
    relation = con.execute(sql.replace("__PATH__", sql_literal(path)))
    columns = [item[0] for item in relation.description]
    return [dict(zip(columns, row)) for row in relation.fetchall()]


def sql_literal(value: str | Path) -> str:
    return "'" + str(value).replace("\\", "/").replace("'", "''") + "'"


def write_json_atomic(path: Path, payload: dict[str, object]) -> None:
    temp = path.with_name(f"_{path.name}.{uuid.uuid4().hex}.tmp")
    try:
        with temp.open("w", encoding="utf-8") as handle:
            json.dump(payload, handle, ensure_ascii=False, indent=2, default=str)
            handle.write("\n")
        os.replace(temp, path)
    finally:
        temp.unlink(missing_ok=True)


def pct(value: float) -> str:
    return f"{value:+.1f}%"


def build_artifact(analysis_dir: Path) -> dict[str, object]:
    summary_path = analysis_dir / "analysis_summary.json"
    with summary_path.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)

    con = duckdb.connect(database=":memory:")
    try:
        monthly_rows = read_rows(
            con,
            analysis_dir / "monthly_trend.parquet",
            """
            SELECT
                month::VARCHAR AS month,
                month_label,
                trips,
                trips_per_active_day,
                avg_request_to_pickup_minutes,
                p50_request_to_pickup_minutes,
                p90_request_to_pickup_minutes,
                wait_coverage_pct,
                avg_trip_miles,
                avg_trip_duration_minutes,
                avg_base_fare_eligible,
                avg_driver_pay_eligible,
                weighted_base_fare_per_mile,
                weighted_driver_pay_per_mile,
                driver_pay_per_occupied_hour,
                trips_mom_pct,
                request_to_pickup_mom_pct,
                trips_yoy_pct,
                request_to_pickup_yoy_pct
            FROM read_parquet(__PATH__)
            ORDER BY month
            """,
        )
        wait_rows = read_rows(
            con,
            analysis_dir / "monthly_wait_trend.parquet",
            """
            SELECT
                month::VARCHAR AS month,
                month_label,
                metric,
                value_minutes,
                trips,
                wait_coverage_pct
            FROM read_parquet(__PATH__)
            ORDER BY month, metric
            """,
        )
        borough_rows = read_rows(
            con,
            analysis_dir / "borough_yoy.parquet",
            """
            SELECT
                borough,
                trips_2025_05,
                trips_2026_05,
                trip_delta,
                trip_growth_pct / 100.0 AS trip_growth_rate,
                trip_share_2026_pct / 100.0 AS trip_share_2026_rate,
                contribution_to_city_trip_growth_pct / 100.0 AS contribution_to_growth_rate,
                avg_wait_2025_05,
                avg_wait_2026_05,
                avg_wait_change_pct / 100.0 AS avg_wait_change_rate,
                avg_fare_2025_05,
                avg_fare_2026_05,
                avg_driver_pay_2025_05,
                avg_driver_pay_2026_05
            FROM read_parquet(__PATH__)
            WHERE borough IN ('Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island')
            ORDER BY trip_delta DESC
            """,
        )
        decomposition_rows = read_rows(
            con,
            analysis_dir / "wait_change_decomposition.parquet",
            """
            SELECT
                borough,
                prior_wait_trip_share_pct / 100.0 AS prior_wait_trip_share_rate,
                current_wait_trip_share_pct / 100.0 AS current_wait_trip_share_rate,
                avg_wait_2025_05,
                avg_wait_2026_05,
                within_borough_wait_change_minutes,
                within_borough_contribution_minutes,
                geographic_mix_contribution_minutes,
                total_contribution_minutes
            FROM read_parquet(__PATH__)
            WHERE borough IN ('Manhattan', 'Brooklyn', 'Queens', 'Bronx', 'Staten Island')
            ORDER BY total_contribution_minutes DESC
            """,
        )
        zone_rows = read_rows(
            con,
            analysis_dir / "zone_yoy.parquet",
            """
            SELECT
                pickup_location_id,
                borough,
                zone,
                zone_label,
                trips_2025_05,
                trips_2026_05,
                trip_delta,
                trip_growth_pct / 100.0 AS trip_growth_rate,
                trip_share_2026_pct / 100.0 AS trip_share_2026_rate,
                avg_wait_2025_05,
                avg_wait_2026_05,
                avg_wait_change_minutes,
                avg_wait_change_pct / 100.0 AS avg_wait_change_rate,
                wait_gap_to_city_minutes,
                estimated_excess_request_to_pickup_minutes,
                marketplace_quadrant
            FROM read_parquet(__PATH__)
            WHERE marketplace_quadrant = 'Supply-constrained priority'
            ORDER BY estimated_excess_request_to_pickup_minutes DESC
            LIMIT 12
            """,
        )
        window_rows = read_rows(
            con,
            analysis_dir / "priority_windows.parquet",
            """
            SELECT
                weekday_name,
                pickup_hour_label,
                borough,
                zone,
                zone_label,
                avg_trips_per_contributing_day,
                avg_request_to_pickup_minutes,
                wait_gap_to_city_minutes,
                estimated_excess_request_to_pickup_minutes_per_day,
                avg_base_fare_eligible,
                avg_driver_pay_eligible
            FROM read_parquet(__PATH__)
            ORDER BY estimated_excess_request_to_pickup_minutes_per_day DESC
            LIMIT 15
            """,
        )
        hourly_rows = read_rows(
            con,
            analysis_dir / "hourly_yoy.parquet",
            """
            SELECT
                pickup_hour,
                LPAD(pickup_hour::VARCHAR, 2, '0') || ':00' AS pickup_hour_label,
                trips_2025_05,
                trips_2026_05,
                avg_daily_trips_2025_05,
                avg_daily_trips_2026_05,
                trip_delta,
                trip_growth_pct / 100.0 AS trip_growth_rate,
                contribution_to_city_trip_growth_pct / 100.0 AS contribution_to_growth_rate,
                avg_wait_2025_05,
                avg_wait_2026_05,
                avg_wait_change_pct / 100.0 AS avg_wait_change_rate
            FROM read_parquet(__PATH__)
            ORDER BY pickup_hour
            """,
        )
        quality_rows = read_rows(
            con,
            analysis_dir / "data_quality_review.parquet",
            """
            SELECT
                month::VARCHAR AS month,
                review_note,
                trips,
                wait_coverage_pct / 100.0 AS wait_coverage_rate,
                duration_coverage_pct / 100.0 AS duration_coverage_rate,
                base_fare_coverage_pct / 100.0 AS base_fare_coverage_rate,
                trip_time_mismatch_gt_60sec_trips
            FROM read_parquet(__PATH__)
            WHERE review_note <> 'No material monthly anomaly'
            ORDER BY month
            """,
        )
    finally:
        con.close()

    metrics = summary["headline_metrics"]
    trips = metrics["Trips"]
    wait = metrics["Average request-to-pickup"]
    p90_wait = metrics["P90 request-to-pickup"]
    miles = metrics["Average trip distance"]
    fare = metrics["Average eligible base fare"]
    pay = metrics["Average eligible driver pay"]
    fare_mile = metrics["Weighted base fare per mile"]
    pay_mile = metrics["Weighted driver pay per mile"]
    decomposition = summary["wait_change_decomposition"]

    borough_lookup = {row["borough"]: row for row in borough_rows}
    manhattan = borough_lookup["Manhattan"]
    brooklyn = borough_lookup["Brooklyn"]
    queens = borough_lookup["Queens"]
    bronx = borough_lookup["Bronx"]
    staten_island = borough_lookup["Staten Island"]
    core_growth = manhattan["trip_delta"] + brooklyn["trip_delta"]
    core_growth_share = core_growth / trips["absolute_change"]

    headline_dataset = [
        {
            "period": "May 2026",
            "trips_current": trips["may_2026"],
            "trips_prior": trips["may_2025"],
            "trip_growth_rate": trips["change_pct"] / 100.0,
            "avg_wait_current": wait["may_2026"],
            "avg_wait_prior": wait["may_2025"],
            "avg_wait_growth_rate": wait["change_pct"] / 100.0,
            "p90_wait_current": p90_wait["may_2026"],
            "p90_wait_prior": p90_wait["may_2025"],
            "p90_wait_growth_rate": p90_wait["change_pct"] / 100.0,
            "avg_fare_current": fare["may_2026"],
            "avg_fare_prior": fare["may_2025"],
            "avg_fare_growth_rate": fare["change_pct"] / 100.0,
            "avg_pay_current": pay["may_2026"],
            "avg_pay_prior": pay["may_2025"],
            "avg_pay_growth_rate": pay["change_pct"] / 100.0,
            "avg_miles_current": miles["may_2026"],
            "avg_miles_prior": miles["may_2025"],
            "avg_miles_growth_rate": miles["change_pct"] / 100.0,
        }
    ]

    generated_at = datetime.now(timezone.utc).isoformat()

    source_specs = [
        {
            "id": "deep_analysis_summary",
            "label": "Deep-analysis summary",
            "path": "data/processed/analysis/analysis_summary.json",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_json_auto('data/processed/analysis/analysis_summary.json')",
                "description": "Loads the validated headline comparison and ranked findings produced by the deep-analysis script.",
                "tables_used": ["analysis.analysis_summary"],
                "filters": ["May 2026 compared with May 2025"],
                "metric_definitions": {
                    "growth_quality": "Trip growth assessed alongside request-to-pickup, passenger fare, driver pay, distance, and duration.",
                    "supply_constrained_priority": "Top-quartile zone demand with average request-to-pickup above the city benchmark; a prioritization proxy, not causal proof.",
                },
                "executed_at": generated_at,
            },
        },
        {
            "id": "monthly_metrics_analysis",
            "label": "Monthly Uber marketplace metrics",
            "path": "data/processed/analysis/monthly_trend.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analytics/monthly_metrics.parquet') ORDER BY month",
                "description": "Loads monthly Uber trip, service, passenger-fare, and driver-pay metrics.",
                "tables_used": ["analytics.monthly_metrics"],
                "filters": ["HV0003 Uber trips", "2025-05 through 2026-05"],
                "metric_definitions": {
                    "request_to_pickup": "pickup_datetime minus request_datetime for eligible trips between 0 and 60 minutes.",
                    "base_fare": "Passenger base fare, not platform revenue.",
                    "driver_pay": "Reported driver compensation, analyzed separately from passenger fare.",
                },
                "executed_at": generated_at,
            },
        },
        {
            "id": "borough_analysis",
            "label": "Borough growth and wait decomposition",
            "path": "data/processed/analysis/borough_yoy.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analysis/borough_yoy.parquet')",
                "description": "Compares May 2026 with May 2025 by pickup borough and decomposes the citywide wait change into within-borough and mix components.",
                "tables_used": ["analytics.zone_daily_metrics", "data.reference.taxi_zone_lookup"],
                "filters": ["May 2025 and May 2026", "valid pickup taxi zones"],
                "metric_definitions": {
                    "growth_contribution": "Borough trip delta divided by the total city trip delta.",
                    "within_borough_wait_effect": "Prior-period borough weight multiplied by the borough wait change.",
                    "geographic_mix_effect": "Change in borough trip weight multiplied by current-period borough wait.",
                },
                "executed_at": generated_at,
            },
        },
        {
            "id": "zone_priority_analysis",
            "label": "Taxi-zone marketplace priority analysis",
            "path": "data/processed/analysis/zone_yoy.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analysis/zone_yoy.parquet') ORDER BY estimated_excess_request_to_pickup_minutes DESC",
                "description": "Ranks pickup zones by demand, wait performance, growth, and excess request-to-pickup minutes.",
                "tables_used": ["analytics.zone_daily_metrics", "data.reference.taxi_zone_lookup"],
                "filters": ["May 2025 and May 2026", "valid pickup taxi zones"],
                "metric_definitions": {
                    "estimated_excess_request_to_pickup_minutes": "Eligible trips multiplied by positive zone wait gap versus the city average.",
                    "priority_quadrant": "Top-quartile demand and above-city average request-to-pickup.",
                },
                "executed_at": generated_at,
            },
        },
        {
            "id": "priority_window_analysis",
            "label": "Pickup zone and recurring hour priorities",
            "path": "data/processed/analysis/priority_windows.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analysis/priority_windows.parquet') ORDER BY estimated_excess_request_to_pickup_minutes_per_day DESC",
                "description": "Ranks May 2026 weekday, pickup-hour, and taxi-zone windows with above-city request-to-pickup and material completed-trip demand.",
                "tables_used": ["analytics.zone_hour_metrics", "data.reference.taxi_zone_lookup"],
                "filters": ["May 2026", "at least 500 trips in the recurring window", "wait above city average"],
                "metric_definitions": {
                    "excess_minutes_per_day": "Eligible trips per contributing weekday multiplied by positive wait gap versus city average.",
                },
                "executed_at": generated_at,
            },
        },
        {
            "id": "quality_review",
            "label": "Monthly data-quality review",
            "path": "data/processed/analysis/data_quality_review.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analytics/data_quality_by_month.parquet') ORDER BY month",
                "description": "Reviews monthly eligibility coverage and time/fare anomalies before using results for recommendations.",
                "tables_used": ["analytics.data_quality_by_month"],
                "filters": ["HV0003 Uber trips", "2025-05 through 2026-05"],
                "executed_at": generated_at,
            },
        },
    ]

    manifest_sources = [
        {"id": item["id"], "label": item["label"], "path": item["path"]}
        for item in source_specs
    ]
    top_level_sources = [
        {"id": item["id"], "query": item["query"]}
        for item in source_specs
    ]

    executive_summary = f"""## Executive Summary

- **May 2026 delivered modest trip growth, but it was not clean growth.** Completed trips rose **{pct(trips['change_pct'])}** to **15.35M**, while average request-to-pickup increased **{pct(wait['change_pct'])}** to **{wait['may_2026']:.2f} minutes** and P90 increased **{pct(p90_wait['change_pct'])}** to **{p90_wait['may_2026']:.2f} minutes**.
- **The wait deterioration was broad operational movement, not a geographic mix illusion.** The borough decomposition attributes **{decomposition['within_borough_contribution_minutes']:.3f} minutes** to within-borough worsening, while geographic mix offset roughly **{abs(decomposition['geographic_mix_contribution_minutes']):.3f} minutes**.
- **Growth was concentrated in Manhattan and Brooklyn, but service pressure was concentrated elsewhere.** The two boroughs generated **{core_growth:,.0f} incremental trips**, or **{core_growth_share:.1%}** of net city growth. Brooklyn wait increased **{brooklyn['avg_wait_change_rate']:.1%}**, Queens **{queens['avg_wait_change_rate']:.1%}**, and the Bronx **{bronx['avg_wait_change_rate']:.1%}**.
- **Use targeted supply and airport operating playbooks, not broad demand stimulation.** Airports show the largest excess request-to-pickup burden despite lower trip volumes, while several growing Brooklyn and Harlem zones combine material demand with double-digit wait deterioration.
"""

    growth_section = f"""## Trip growth came with a larger service-quality penalty

Trips increased **{pct(trips['change_pct'])}**, but the service distribution worsened much faster: average request-to-pickup increased **{pct(wait['change_pct'])}** and P90 increased **{pct(p90_wait['change_pct'])}**. The gap between the average and P90 movement suggests the long-wait tail deteriorated more than the typical trip.

Passenger base fare per trip and driver pay per trip moved almost in parallel—**{pct(fare['change_pct'])}** and **{pct(pay['change_pct'])}**, respectively—while average distance fell **{pct(miles['change_pct'])}**. The shorter trip mix mechanically pushed base fare per mile up **{pct(fare_mile['change_pct'])}** and driver pay per mile up **{pct(pay_mile['change_pct'])}**. These are separate passenger and driver economics; they are not a platform margin calculation.
"""

    wait_section = f"""## Service deterioration was broad, while geographic mix was slightly favorable

The citywide average increased **{wait['absolute_change']:.3f} minutes**. The decomposition assigns approximately **{decomposition['within_borough_contribution_minutes']:.3f} minutes** to higher request-to-pickup inside boroughs. Changing borough mix contributed **{decomposition['geographic_mix_contribution_minutes']:.3f} minutes**, slightly offsetting the deterioration rather than causing it.

Manhattan combined **{manhattan['trip_growth_rate']:.1%}** trip growth with only **{manhattan['avg_wait_change_rate']:.1%}** wait deterioration. Brooklyn grew **{brooklyn['trip_growth_rate']:.1%}** but wait rose **{brooklyn['avg_wait_change_rate']:.1%}**. Queens wait rose **{queens['avg_wait_change_rate']:.1%}** on **{queens['trip_growth_rate']:.1%}** trip growth, while Bronx trips declined **{abs(bronx['trip_growth_rate']):.1%}** and wait still rose **{bronx['avg_wait_change_rate']:.1%}**. That pattern argues against one citywide marketplace explanation.
"""

    zone_section = """## Airports and growing neighborhoods require different operating playbooks

LaGuardia and JFK rank first on estimated excess request-to-pickup minutes, but both recorded fewer completed trips than the prior May. That combination looks more like a structural airport pickup and staging problem than demand-led growth pressure.

The neighborhood list tells a different story. Central Harlem North, Crown Heights North, Canarsie, Stuyvesant Heights, Bushwick South, East New York, and Brownsville pair sizable completed-trip demand with rising request-to-pickup. These are better candidates for targeted supply reallocation or controlled incentive tests than for broad citywide intervention.
"""

    window_section = """## Late-night airport windows and early-morning citywide hours are the first operating priorities

The most concentrated recurring windows are dominated by LaGuardia and JFK during late evening and overnight periods. Separately, the citywide hourly comparison shows the sharpest wait deterioration around 3–6 a.m., when completed-trip growth also accelerated. Operations should track these windows with both average and P90 request-to-pickup, because the long-wait tail deteriorated fastest overall.
"""

    recommendation_section = """## Recommended next steps

1. **Separate airport operations from neighborhood marketplace management.** Review airport staging, queue release, flight-arrival alignment, and late-night driver availability independently from urban supply allocation.
2. **Pilot targeted supply interventions in the highest-burden neighborhood zones.** Start with the recurring zone-hour windows in the priority table and use a phased or randomized design where possible.
3. **Use service guardrails before adding demand.** Do not treat trip growth alone as success; require average and P90 request-to-pickup, excess request-to-pickup minutes, and driver-pay intensity to remain within agreed limits.
4. **Add internal marketplace data before claiming causality.** Acceptance, cancellation, unserved requests, driver online time, surge, reservations, and incentive exposure are required to distinguish supply shortage from dispatch, product, or reporting effects.
"""

    questions_section = """## Further Questions

- How much of the request-to-pickup increase comes from reserved or scheduled trips rather than on-demand dispatch?
- Did driver online hours, acceptance, cancellation, or repositioning behavior change in the affected boroughs and hours?
- Are airport patterns explained by flight schedules, queue rules, staging-lot utilization, or pickup-zone reporting behavior?
- Which priority neighborhood windows remain constrained after controlling for weather, holidays, and local events?
"""

    caveat_section = """## Caveats and assumptions

- The TLC records represent completed trips. They do not include unserved demand, cancellations, driver online time, promotions, surge multipliers, or user/driver identifiers.
- “Supply-constrained priority” and “excess request-to-pickup minutes” are prioritization proxies, not causal proof of insufficient driver supply.
- Timestamps are treated as reported New York local time. Request-to-pickup is restricted to 0–60 minutes; `on_scene_datetime` is not used as a core KPI.
- Passenger base fare and driver pay are analyzed separately. Their difference is not labeled platform revenue, profit, margin, or take rate.
- Monthly quality checks identified isolated duration and fare anomalies outside the focal May-to-May comparison. May eligibility remained high enough for the comparison, but public TLC data is provider-submitted and not guaranteed complete or error-free.
"""

    cards = [
        {
            "id": "trips_card",
            "description": "Completed Uber trips in May 2026 with the May 2025 comparison.",
            "dataset": "headline",
            "sourceId": "monthly_metrics_analysis",
            "metrics": [
                {"label": "May 2026 trips", "field": "trips_current", "format": "number"},
                {"label": "May 2025", "field": "trips_prior", "format": "number"},
                {"label": "YoY", "field": "trip_growth_rate", "format": "percent", "signed": True},
            ],
        },
        {
            "id": "avg_wait_card",
            "description": "Average request-to-pickup among metric-eligible trips.",
            "dataset": "headline",
            "sourceId": "monthly_metrics_analysis",
            "metrics": [
                {"label": "Average request-to-pickup", "field": "avg_wait_current", "format": "number", "unit": "min"},
                {"label": "May 2025", "field": "avg_wait_prior", "format": "number", "unit": "min"},
                {"label": "YoY", "field": "avg_wait_growth_rate", "format": "percent", "signed": True},
            ],
        },
        {
            "id": "p90_wait_card",
            "description": "The 90th percentile of request-to-pickup among metric-eligible trips.",
            "dataset": "headline",
            "sourceId": "monthly_metrics_analysis",
            "metrics": [
                {"label": "P90 request-to-pickup", "field": "p90_wait_current", "format": "number", "unit": "min"},
                {"label": "May 2025", "field": "p90_wait_prior", "format": "number", "unit": "min"},
                {"label": "YoY", "field": "p90_wait_growth_rate", "format": "percent", "signed": True},
            ],
        },
        {
            "id": "fare_card",
            "description": "Average eligible passenger base fare per completed trip; not platform revenue.",
            "dataset": "headline",
            "sourceId": "monthly_metrics_analysis",
            "metrics": [
                {"label": "Passenger base fare", "field": "avg_fare_current", "format": "currency"},
                {"label": "May 2025", "field": "avg_fare_prior", "format": "currency"},
                {"label": "YoY", "field": "avg_fare_growth_rate", "format": "percent", "signed": True},
            ],
        },
        {
            "id": "pay_card",
            "description": "Average eligible reported driver pay per completed trip.",
            "dataset": "headline",
            "sourceId": "monthly_metrics_analysis",
            "metrics": [
                {"label": "Driver pay per trip", "field": "avg_pay_current", "format": "currency"},
                {"label": "May 2025", "field": "avg_pay_prior", "format": "currency"},
                {"label": "YoY", "field": "avg_pay_growth_rate", "format": "percent", "signed": True},
            ],
        },
    ]

    charts = [
        {
            "id": "monthly_trips_chart",
            "title": "Monthly completed trips",
            "subtitle": "May 2025–May 2026; Uber HV0003 completed trips",
            "type": "line",
            "dataset": "monthly_trend",
            "sourceId": "monthly_metrics_analysis",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "month", "type": "temporal", "label": "Month"},
                "y": {"field": "trips", "type": "quantitative", "label": "Trips"},
                "tooltip": [
                    {"field": "trips_per_active_day", "type": "quantitative", "label": "Trips per active day"},
                    {"field": "avg_request_to_pickup_minutes", "type": "quantitative", "label": "Avg request-to-pickup"},
                ],
            },
        },
        {
            "id": "monthly_wait_chart",
            "title": "Monthly request-to-pickup distribution",
            "subtitle": "Average, median, and P90 among trips with request-to-pickup between 0 and 60 minutes",
            "type": "line",
            "dataset": "monthly_wait_trend",
            "sourceId": "monthly_metrics_analysis",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "month", "type": "temporal", "label": "Month"},
                "y": {"field": "value_minutes", "type": "quantitative", "label": "Minutes"},
                "color": {"field": "metric", "type": "nominal", "label": "Statistic"},
                "tooltip": [
                    {"field": "metric", "type": "nominal", "label": "Statistic"},
                    {"field": "value_minutes", "type": "quantitative", "label": "Minutes"},
                    {"field": "wait_coverage_pct", "type": "quantitative", "label": "Eligibility coverage (%)"},
                ],
            },
        },
        {
            "id": "borough_growth_chart",
            "title": "Completed-trip growth by pickup borough",
            "subtitle": "May 2026 versus May 2025; five NYC boroughs",
            "type": "bar",
            "dataset": "borough_yoy",
            "sourceId": "borough_analysis",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "borough", "type": "nominal", "label": "Pickup borough"},
                "y": {"field": "trip_growth_rate", "type": "quantitative", "label": "Trip growth"},
                "tooltip": [
                    {"field": "trip_delta", "type": "quantitative", "label": "Trip delta"},
                    {"field": "avg_wait_change_rate", "type": "quantitative", "label": "Wait change", "format": "percent"},
                    {"field": "contribution_to_growth_rate", "type": "quantitative", "label": "Contribution to city growth", "format": "percent"},
                ],
            },
        },
        {
            "id": "priority_zone_chart",
            "title": "Highest excess request-to-pickup burden by pickup zone",
            "subtitle": "May 2026; top-quartile zone demand and wait above the city average",
            "type": "bar",
            "dataset": "priority_zones",
            "sourceId": "zone_priority_analysis",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "zone_label", "type": "nominal", "label": "Pickup zone"},
                "y": {"field": "estimated_excess_request_to_pickup_minutes", "type": "quantitative", "label": "Estimated excess minutes"},
                "tooltip": [
                    {"field": "trips_2026_05", "type": "quantitative", "label": "May 2026 trips"},
                    {"field": "trip_growth_rate", "type": "quantitative", "label": "Trip growth", "format": "percent"},
                    {"field": "avg_wait_2026_05", "type": "quantitative", "label": "Avg request-to-pickup"},
                    {"field": "avg_wait_change_rate", "type": "quantitative", "label": "Wait change", "format": "percent"},
                ],
            },
        },
        {
            "id": "hourly_wait_chart",
            "title": "Request-to-pickup change by pickup hour",
            "subtitle": "May 2026 versus May 2025; citywide completed trips",
            "type": "bar",
            "dataset": "hourly_yoy",
            "sourceId": "priority_window_analysis",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "pickup_hour_label", "type": "ordinal", "label": "Pickup hour"},
                "y": {"field": "avg_wait_change_rate", "type": "quantitative", "label": "Wait change"},
                "tooltip": [
                    {"field": "trip_growth_rate", "type": "quantitative", "label": "Trip growth", "format": "percent"},
                    {"field": "avg_wait_2025_05", "type": "quantitative", "label": "May 2025 avg wait"},
                    {"field": "avg_wait_2026_05", "type": "quantitative", "label": "May 2026 avg wait"},
                ],
            },
        },
    ]

    tables = [
        {
            "id": "priority_windows_table",
            "title": "Highest-priority recurring pickup windows",
            "subtitle": "Top 15 May 2026 weekday-hour-zone combinations by estimated excess request-to-pickup minutes per contributing day",
            "dataset": "priority_windows",
            "sourceId": "priority_window_analysis",
            "defaultSort": {"field": "estimated_excess_request_to_pickup_minutes_per_day", "direction": "desc"},
            "columns": [
                {"field": "weekday_name", "label": "Weekday", "type": "text"},
                {"field": "pickup_hour_label", "label": "Hour", "type": "text"},
                {"field": "zone_label", "label": "Pickup zone", "type": "text"},
                {"field": "avg_trips_per_contributing_day", "label": "Trips/day", "format": "number"},
                {"field": "avg_request_to_pickup_minutes", "label": "Avg request-to-pickup", "format": "number"},
                {"field": "wait_gap_to_city_minutes", "label": "Gap vs city", "format": "number"},
                {"field": "estimated_excess_request_to_pickup_minutes_per_day", "label": "Excess minutes/day", "format": "number"},
            ],
        },
        {
            "id": "quality_table",
            "title": "Monthly quality exceptions outside the focal comparison",
            "subtitle": "Months with duration, fare, or trip-time mismatch signals requiring caution",
            "dataset": "quality_exceptions",
            "sourceId": "quality_review",
            "defaultSort": {"field": "month", "direction": "asc"},
            "columns": [
                {"field": "month", "label": "Month", "type": "text"},
                {"field": "review_note", "label": "Review note", "type": "text"},
                {"field": "wait_coverage_rate", "label": "Wait coverage", "format": "percent"},
                {"field": "duration_coverage_rate", "label": "Duration coverage", "format": "percent"},
                {"field": "base_fare_coverage_rate", "label": "Fare coverage", "format": "percent"},
                {"field": "trip_time_mismatch_gt_60sec_trips", "label": "Trip-time mismatches", "format": "number"},
            ],
        },
    ]

    blocks = [
        {"id": "title", "type": "markdown", "body": f"# {TITLE}"},
        {"id": "executive_summary", "type": "markdown", "body": executive_summary, "sourceId": "deep_analysis_summary"},
        {"id": "headline_metrics", "type": "metric-strip", "cardIds": [item["id"] for item in cards]},
        {"id": "growth_section", "type": "markdown", "body": growth_section, "sourceId": "deep_analysis_summary"},
        {"id": "monthly_trips_block", "type": "chart", "chartId": "monthly_trips_chart"},
        {"id": "monthly_wait_block", "type": "chart", "chartId": "monthly_wait_chart"},
        {"id": "wait_section", "type": "markdown", "body": wait_section, "sourceId": "deep_analysis_summary"},
        {"id": "borough_growth_block", "type": "chart", "chartId": "borough_growth_chart"},
        {"id": "zone_section", "type": "markdown", "body": zone_section, "sourceId": "deep_analysis_summary"},
        {"id": "priority_zone_block", "type": "chart", "chartId": "priority_zone_chart"},
        {"id": "window_section", "type": "markdown", "body": window_section, "sourceId": "deep_analysis_summary"},
        {"id": "hourly_wait_block", "type": "chart", "chartId": "hourly_wait_chart"},
        {"id": "priority_windows_block", "type": "table", "tableId": "priority_windows_table"},
        {"id": "recommendations", "type": "markdown", "body": recommendation_section, "sourceId": "deep_analysis_summary"},
        {"id": "further_questions", "type": "markdown", "body": questions_section},
        {"id": "caveats", "type": "markdown", "body": caveat_section, "sourceId": "quality_review"},
        {"id": "quality_block", "type": "table", "tableId": "quality_table"},
    ]

    return {
        "surface": "report",
        "manifest": {
            "version": 1,
            "surface": "report",
            "title": TITLE,
            "description": "A decision-ready review of Uber NYC growth quality, service efficiency, and operating priorities.",
            "generatedAt": generated_at,
            "cards": cards,
            "charts": charts,
            "tables": tables,
            "sources": manifest_sources,
            "blocks": blocks,
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": {
                "headline": headline_dataset,
                "monthly_trend": monthly_rows,
                "monthly_wait_trend": wait_rows,
                "borough_yoy": borough_rows,
                "wait_decomposition": decomposition_rows,
                "priority_zones": zone_rows,
                "priority_windows": window_rows,
                "hourly_yoy": hourly_rows,
                "quality_exceptions": quality_rows,
            },
            "accessIssues": [],
        },
        "sources": top_level_sources,
    }


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir",
        type=Path,
        default=Path(__file__).resolve().parents[1],
    )
    parser.add_argument("--analysis-dir", type=Path, default=None)
    parser.add_argument("--output", type=Path, default=None)
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.resolve()
    analysis_dir = (
        args.analysis_dir or project_dir / "data" / "processed" / "analysis"
    ).resolve()
    output = (
        args.output or project_dir / "reports" / "executive_report_artifact_en.json"
    ).resolve()
    required = [
        analysis_dir / "analysis_summary.json",
        analysis_dir / "monthly_trend.parquet",
        analysis_dir / "monthly_wait_trend.parquet",
        analysis_dir / "borough_yoy.parquet",
        analysis_dir / "wait_change_decomposition.parquet",
        analysis_dir / "zone_yoy.parquet",
        analysis_dir / "priority_windows.parquet",
        analysis_dir / "hourly_yoy.parquet",
        analysis_dir / "data_quality_review.parquet",
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing report inputs:\n" + "\n".join(map(str, missing)))

    output.parent.mkdir(parents=True, exist_ok=True)
    artifact = build_artifact(analysis_dir)
    write_json_atomic(output, artifact)
    print(f"Canonical report artifact written to: {output}")
    print(f"Blocks: {len(artifact['manifest']['blocks'])}")
    print(f"Charts: {len(artifact['manifest']['charts'])}")
    print(f"Tables: {len(artifact['manifest']['tables'])}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
