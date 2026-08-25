"""Build the unified three-page Uber NYC Final Dashboard from validated marts.

The script reads only the compact, validated outputs produced by
``04_deep_analysis.py``. It writes canonical source artifacts, packages all three
management views into one self-contained HTML file, and records numerical QA.

Run from the repository root:

    python scripts/06_build_final_dashboard.py
"""

from __future__ import annotations

import argparse
import csv
import json
import os
import subprocess
import sys
import uuid
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import duckdb


PAGES = (
    ("page_1_marketplace_overview", "Page 1 — Marketplace Overview"),
    ("page_2_marketplace_efficiency", "Page 2 — Marketplace Efficiency"),
    ("page_3_operating_priorities", "Page 3 — Growth Quality & Operating Priorities"),
)


def sql_literal(value: str | Path) -> str:
    return "'" + str(value).replace("\\", "/").replace("'", "''") + "'"


def read_rows(
    con: duckdb.DuckDBPyConnection, path: Path, sql: str
) -> list[dict[str, Any]]:
    relation = con.execute(sql.replace("__PATH__", sql_literal(path)))
    columns = [item[0] for item in relation.description]
    return [dict(zip(columns, row)) for row in relation.fetchall()]


def write_json_atomic(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
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


def nav(page_number: int) -> str:
    labels = []
    for index, (slug, title) in enumerate(PAGES, start=1):
        label = title.replace(f"Page {index} — ", "")
        if index == page_number:
            labels.append(f"**{index}. {label}**")
        else:
            labels.append(f"[{index}. {label}]({slug}.html)")
    return f"**Executive dashboard · Page {page_number} of 3**  \n" + " · ".join(labels)


def make_card(
    *, card_id: str, description: str, dataset: str, source_id: str, metrics: list[dict[str, Any]]
) -> dict[str, Any]:
    return {
        "id": card_id,
        "description": description,
        "dataset": dataset,
        "sourceId": source_id,
        "metrics": metrics,
    }


def source_specs(generated_at: str) -> dict[str, dict[str, Any]]:
    return {
        "deep_analysis_summary": {
            "label": "Validated deep-analysis summary",
            "path": "data/processed/analysis/analysis_summary.json",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_json_auto('data/processed/analysis/analysis_summary.json')",
                "description": "Loads the validated May 2026 versus May 2025 headline metrics and interpretation boundaries.",
                "tables_used": ["analysis.analysis_summary"],
                "filters": ["May 2026 compared with May 2025"],
                "metric_definitions": {
                    "growth_quality": "Completed-trip growth assessed alongside request-to-pickup, passenger base fare, driver pay, distance, and duration.",
                    "interpretation_boundary": "Completed-trip data does not measure unserved demand, cancellations, driver online time, surge, promotions, or causal supply shortages.",
                },
                "executed_at": generated_at,
            },
        },
        "monthly_metrics_analysis": {
            "label": "Monthly Uber marketplace metrics",
            "path": "data/processed/analysis/monthly_trend.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analysis/monthly_trend.parquet') ORDER BY month",
                "description": "Loads 13 monthly observations for completed trips, request-to-pickup, passenger base fare, and driver pay.",
                "tables_used": ["analytics.monthly_metrics"],
                "filters": ["HV0003 Uber trips", "2025-05 through 2026-05"],
                "metric_definitions": {
                    "trips": "Count of HV0003 completed-trip rows; preserved independently of metric eligibility.",
                    "request_to_pickup": "Pickup timestamp minus request timestamp for eligible observations between 0 and 60 minutes.",
                    "base_fare": "Average eligible passenger base fare per trip; not platform revenue.",
                    "driver_pay": "Average eligible reported driver compensation per trip; not online-hour earnings.",
                    "wait_coverage": "Request-to-pickup-eligible trips divided by all HV0003 completed trips.",
                },
                "executed_at": generated_at,
            },
        },
        "borough_analysis": {
            "label": "Borough growth and wait decomposition",
            "path": "data/processed/analysis/borough_yoy.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analysis/borough_yoy.parquet')",
                "description": "Compares May 2026 with May 2025 by pickup borough and decomposes citywide request-to-pickup movement.",
                "tables_used": ["analytics.zone_daily_metrics", "data.reference.taxi_zone_lookup"],
                "filters": ["May 2025 and May 2026", "five NYC boroughs"],
                "metric_definitions": {
                    "growth_contribution": "Borough trip delta divided by the total city trip delta.",
                    "within_borough_effect": "Prior-period borough trip weight multiplied by the borough wait change.",
                    "geographic_mix_effect": "Change in borough trip weight multiplied by current-period borough wait.",
                },
                "executed_at": generated_at,
            },
        },
        "zone_priority_analysis": {
            "label": "Taxi-zone marketplace priority analysis",
            "path": "data/processed/analysis/zone_yoy.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analysis/zone_yoy.parquet') ORDER BY estimated_excess_request_to_pickup_minutes DESC",
                "description": "Compares pickup zones on completed-trip demand, request-to-pickup, growth, and excess request-to-pickup burden.",
                "tables_used": ["analytics.zone_daily_metrics", "data.reference.taxi_zone_lookup"],
                "filters": ["May 2025 and May 2026", "valid pickup taxi zones"],
                "metric_definitions": {
                    "estimated_excess_request_to_pickup_minutes": "Eligible completed trips multiplied by the positive zone wait gap versus the city average.",
                    "supply_constrained_priority": "Top-quartile completed-trip demand with average request-to-pickup above the city benchmark; an operating proxy, not causal proof.",
                    "scatter_population": "Five-borough taxi zones with at least 500 completed trips in each comparison month and a valid May 2026 wait metric.",
                },
                "executed_at": generated_at,
            },
        },
        "hourly_analysis": {
            "label": "Citywide hourly year-over-year profile",
            "path": "data/processed/analysis/hourly_yoy.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analysis/hourly_yoy.parquet') ORDER BY pickup_hour",
                "description": "Compares May 2026 with May 2025 by pickup hour across completed trips.",
                "tables_used": ["analytics.zone_hour_metrics"],
                "filters": ["May 2025 and May 2026", "24 pickup hours"],
                "metric_definitions": {
                    "hourly_wait_change": "Year-over-year change in average eligible request-to-pickup for each pickup hour.",
                },
                "executed_at": generated_at,
            },
        },
        "priority_window_analysis": {
            "label": "Recurring pickup-window priority analysis",
            "path": "data/processed/analysis/priority_windows.parquet",
            "query": {
                "engine": "duckdb",
                "language": "sql",
                "sql": "SELECT * FROM read_parquet('data/processed/analysis/priority_windows.parquet') ORDER BY estimated_excess_request_to_pickup_minutes_per_day DESC",
                "description": "Ranks May 2026 weekday-hour-zone windows with above-city request-to-pickup and material completed-trip demand.",
                "tables_used": ["analytics.zone_hour_metrics", "data.reference.taxi_zone_lookup"],
                "filters": ["May 2026", "at least 500 trips in the recurring window", "wait above city average"],
                "metric_definitions": {
                    "excess_minutes_per_day": "Eligible trips per contributing weekday multiplied by the positive wait gap versus the city average.",
                },
                "executed_at": generated_at,
            },
        },
    }


def artifact(
    *,
    title: str,
    description: str,
    generated_at: str,
    cards: list[dict[str, Any]],
    charts: list[dict[str, Any]],
    tables: list[dict[str, Any]],
    blocks: list[dict[str, Any]],
    datasets: dict[str, list[dict[str, Any]]],
    sources: dict[str, dict[str, Any]],
    source_ids: list[str],
) -> dict[str, Any]:
    return {
        "surface": "dashboard",
        "manifest": {
            "version": 1,
            "surface": "dashboard",
            "title": title,
            "description": description,
            "generatedAt": generated_at,
            "cards": cards,
            "charts": charts,
            "tables": tables,
            "sources": [
                {"id": source_id, "label": sources[source_id]["label"], "path": sources[source_id]["path"]}
                for source_id in source_ids
            ],
            "blocks": blocks,
        },
        "snapshot": {
            "version": 1,
            "generatedAt": generated_at,
            "status": "ready",
            "datasets": datasets,
            "accessIssues": [],
        },
        "sources": [
            {"id": source_id, "query": sources[source_id]["query"]}
            for source_id in source_ids
        ],
    }


def build_pages(project_dir: Path) -> tuple[dict[str, dict[str, Any]], list[dict[str, Any]], list[dict[str, Any]]]:
    analysis_dir = project_dir / "data" / "processed" / "analysis"
    summary_path = analysis_dir / "analysis_summary.json"
    with summary_path.open("r", encoding="utf-8") as handle:
        summary = json.load(handle)

    generated_at = datetime.now(timezone.utc).isoformat()
    sources = source_specs(generated_at)
    con = duckdb.connect(database=":memory:")
    try:
        monthly = read_rows(
            con,
            analysis_dir / "monthly_trend.parquet",
            """
            SELECT month::VARCHAR AS month, month_label, trips, trips_per_active_day,
                   avg_request_to_pickup_minutes, p50_request_to_pickup_minutes,
                   p90_request_to_pickup_minutes, wait_coverage_pct / 100.0 AS wait_coverage_rate,
                   avg_base_fare_eligible, avg_driver_pay_eligible,
                   trips_yoy_pct / 100.0 AS trips_yoy_rate,
                   request_to_pickup_yoy_pct / 100.0 AS request_to_pickup_yoy_rate
            FROM read_parquet(__PATH__) ORDER BY month
            """,
        )
        wait_trend = read_rows(
            con,
            analysis_dir / "monthly_wait_trend.parquet",
            """
            SELECT month::VARCHAR AS month, month_label, metric, value_minutes, trips,
                   wait_coverage_pct / 100.0 AS wait_coverage_rate
            FROM read_parquet(__PATH__) ORDER BY month, metric
            """,
        )
        borough = read_rows(
            con,
            analysis_dir / "borough_yoy.parquet",
            """
            SELECT borough, trips_2025_05, trips_2026_05, trip_delta,
                   trip_growth_pct / 100.0 AS trip_growth_rate,
                   contribution_to_city_trip_growth_pct / 100.0 AS contribution_to_growth_rate,
                   avg_wait_2025_05, avg_wait_2026_05,
                   avg_wait_change_pct / 100.0 AS avg_wait_change_rate
            FROM read_parquet(__PATH__)
            WHERE borough IN ('Manhattan','Brooklyn','Queens','Bronx','Staten Island')
            ORDER BY trip_delta DESC
            """,
        )
        decomposition = read_rows(
            con,
            analysis_dir / "wait_change_decomposition.parquet",
            """
            SELECT borough, within_borough_contribution_minutes,
                   geographic_mix_contribution_minutes, total_contribution_minutes
            FROM read_parquet(__PATH__)
            WHERE borough IN ('Manhattan','Brooklyn','Queens','Bronx','Staten Island')
            ORDER BY total_contribution_minutes DESC
            """,
        )
        zone_scatter = read_rows(
            con,
            analysis_dir / "zone_yoy.parquet",
            """
            SELECT pickup_location_id, borough, zone, zone_label,
                   trips_2025_05, trips_2026_05, trip_delta,
                   trip_growth_pct / 100.0 AS trip_growth_rate,
                   avg_wait_2025_05, avg_wait_2026_05,
                   avg_wait_change_pct / 100.0 AS avg_wait_change_rate,
                   estimated_excess_request_to_pickup_minutes,
                   marketplace_quadrant
            FROM read_parquet(__PATH__)
            WHERE borough IN ('Manhattan','Brooklyn','Queens','Bronx','Staten Island')
              AND trips_2025_05 >= 500 AND trips_2026_05 >= 500
              AND avg_wait_2026_05 IS NOT NULL
            ORDER BY trips_2026_05 DESC
            """,
        )
        priority_zones = read_rows(
            con,
            analysis_dir / "zone_yoy.parquet",
            """
            SELECT pickup_location_id, borough, zone, zone_label,
                   trips_2026_05, trip_delta,
                   trip_growth_pct / 100.0 AS trip_growth_rate,
                   avg_wait_2026_05,
                   avg_wait_change_pct / 100.0 AS avg_wait_change_rate,
                   wait_gap_to_city_minutes,
                   estimated_excess_request_to_pickup_minutes,
                   marketplace_quadrant
            FROM read_parquet(__PATH__)
            WHERE marketplace_quadrant = 'Supply-constrained priority'
            ORDER BY estimated_excess_request_to_pickup_minutes DESC
            """,
        )
        hourly = read_rows(
            con,
            analysis_dir / "hourly_yoy.parquet",
            """
            SELECT pickup_hour, LPAD(pickup_hour::VARCHAR, 2, '0') || ':00' AS pickup_hour_label,
                   trips_2025_05, trips_2026_05, trip_delta,
                   trip_growth_pct / 100.0 AS trip_growth_rate,
                   contribution_to_city_trip_growth_pct / 100.0 AS contribution_to_growth_rate,
                   avg_wait_2025_05, avg_wait_2026_05,
                   avg_wait_change_pct / 100.0 AS avg_wait_change_rate
            FROM read_parquet(__PATH__) ORDER BY pickup_hour
            """,
        )
        priority_windows = read_rows(
            con,
            analysis_dir / "priority_windows.parquet",
            """
            SELECT weekday_name, pickup_hour, pickup_hour_label, borough, zone, zone_label,
                   avg_trips_per_contributing_day, avg_request_to_pickup_minutes,
                   wait_gap_to_city_minutes,
                   estimated_excess_request_to_pickup_minutes_per_day
            FROM read_parquet(__PATH__)
            ORDER BY estimated_excess_request_to_pickup_minutes_per_day DESC
            """,
        )
    finally:
        con.close()

    economics_trend: list[dict[str, Any]] = []
    for row in monthly:
        economics_trend.extend(
            [
                {
                    "month": row["month"],
                    "month_label": row["month_label"],
                    "metric": "Passenger base fare",
                    "value_usd_per_trip": row["avg_base_fare_eligible"],
                    "trips": row["trips"],
                },
                {
                    "month": row["month"],
                    "month_label": row["month_label"],
                    "metric": "Driver pay",
                    "value_usd_per_trip": row["avg_driver_pay_eligible"],
                    "trips": row["trips"],
                },
            ]
        )

    metrics = summary["headline_metrics"]
    trips = metrics["Trips"]
    avg_wait = metrics["Average request-to-pickup"]
    p90_wait = metrics["P90 request-to-pickup"]
    fare = metrics["Average eligible base fare"]
    pay = metrics["Average eligible driver pay"]
    coverage = metrics["Wait eligibility coverage"]
    wait_decomp = summary["wait_change_decomposition"]

    page_1_headline = [
        {
            "period": "May 2026",
            "trips_current": trips["may_2026"],
            "trips_prior": trips["may_2025"],
            "trip_growth_rate": trips["change_pct"] / 100.0,
            "avg_wait_current": avg_wait["may_2026"],
            "avg_wait_prior": avg_wait["may_2025"],
            "avg_wait_growth_rate": avg_wait["change_pct"] / 100.0,
            "p90_wait_current": p90_wait["may_2026"],
            "p90_wait_prior": p90_wait["may_2025"],
            "p90_wait_growth_rate": p90_wait["change_pct"] / 100.0,
            "fare_current": fare["may_2026"],
            "fare_prior": fare["may_2025"],
            "fare_growth_rate": fare["change_pct"] / 100.0,
            "pay_current": pay["may_2026"],
            "pay_prior": pay["may_2025"],
            "pay_growth_rate": pay["change_pct"] / 100.0,
            "wait_coverage_current": coverage["may_2026"] / 100.0,
            "wait_coverage_prior": coverage["may_2025"] / 100.0,
        }
    ]

    page_1_cards = [
        make_card(
            card_id="trips_card",
            description="Completed Uber HV0003 trips in May 2026; metric-specific eligibility does not alter trip volume.",
            dataset="headline",
            source_id="monthly_metrics_analysis",
            metrics=[
                {"label": "May 2026 trips", "field": "trips_current", "format": "number"},
                {"label": "May 2025", "field": "trips_prior", "format": "number"},
                {"label": "YoY", "field": "trip_growth_rate", "format": "percent", "signed": True},
            ],
        ),
        make_card(
            card_id="avg_wait_card",
            description="Average Request-to-Pickup Time among eligible completed trips.",
            dataset="headline",
            source_id="monthly_metrics_analysis",
            metrics=[
                {"label": "Avg request-to-pickup", "field": "avg_wait_current", "format": "number", "unit": "min"},
                {"label": "May 2025", "field": "avg_wait_prior", "format": "number", "unit": "min"},
                {"label": "YoY", "field": "avg_wait_growth_rate", "format": "percent", "signed": True},
            ],
        ),
        make_card(
            card_id="p90_wait_card",
            description="90th percentile Request-to-Pickup Time among eligible completed trips.",
            dataset="headline",
            source_id="monthly_metrics_analysis",
            metrics=[
                {"label": "P90 request-to-pickup", "field": "p90_wait_current", "format": "number", "unit": "min"},
                {"label": "May 2025", "field": "p90_wait_prior", "format": "number", "unit": "min"},
                {"label": "YoY", "field": "p90_wait_growth_rate", "format": "percent", "signed": True},
            ],
        ),
        make_card(
            card_id="fare_card",
            description="Average eligible passenger base fare per trip; not platform revenue.",
            dataset="headline",
            source_id="monthly_metrics_analysis",
            metrics=[
                {"label": "Passenger base fare", "field": "fare_current", "format": "currency"},
                {"label": "May 2025", "field": "fare_prior", "format": "currency"},
                {"label": "YoY", "field": "fare_growth_rate", "format": "percent", "signed": True},
            ],
        ),
        make_card(
            card_id="pay_card",
            description="Average eligible reported driver compensation per completed trip.",
            dataset="headline",
            source_id="monthly_metrics_analysis",
            metrics=[
                {"label": "Driver pay per trip", "field": "pay_current", "format": "currency"},
                {"label": "May 2025", "field": "pay_prior", "format": "currency"},
                {"label": "YoY", "field": "pay_growth_rate", "format": "percent", "signed": True},
            ],
        ),
        make_card(
            card_id="coverage_card",
            description="Share of completed trips eligible for Request-to-Pickup Time.",
            dataset="headline",
            source_id="monthly_metrics_analysis",
            metrics=[
                {"label": "Wait eligibility", "field": "wait_coverage_current", "format": "percent"},
                {"label": "May 2025", "field": "wait_coverage_prior", "format": "percent"},
            ],
        ),
    ]

    page_1_charts = [
        {
            "id": "monthly_trips_chart",
            "title": "Monthly completed trips",
            "subtitle": "May 2025–May 2026 · Uber HV0003 completed trips",
            "type": "line",
            "intent": "trend",
            "question": "How did completed-trip volume move across the 13-month window?",
            "rationale": "A line chart shows the monthly volume shape across 13 observed periods.",
            "dataset": "monthly_trend",
            "sourceId": "monthly_metrics_analysis",
            "layout": "half",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "month", "type": "temporal", "label": "Month"},
                "y": {"field": "trips", "type": "quantitative", "label": "Completed trips"},
                "tooltip": [
                    {"field": "trips_per_active_day", "type": "quantitative", "label": "Trips per active day"},
                    {"field": "avg_request_to_pickup_minutes", "type": "quantitative", "label": "Avg request-to-pickup"},
                ],
            },
        },
        {
            "id": "monthly_wait_chart",
            "title": "Monthly Request-to-Pickup Time",
            "subtitle": "Average, median, and P90 · eligible completed trips · minutes",
            "type": "line",
            "intent": "trend",
            "question": "How did the center and long-wait tail of Request-to-Pickup move?",
            "rationale": "Three lines compare the average, median, and P90 across the same monthly grain.",
            "combinationRationale": "All series use minutes, the same eligibility rule, and the same 13 monthly observations.",
            "dataset": "monthly_wait_trend",
            "sourceId": "monthly_metrics_analysis",
            "layout": "half",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "month", "type": "temporal", "label": "Month"},
                "y": {"field": "value_minutes", "type": "quantitative", "label": "Minutes"},
                "color": {"field": "metric", "type": "nominal", "label": "Statistic"},
                "tooltip": [
                    {"field": "metric", "type": "nominal", "label": "Statistic"},
                    {"field": "value_minutes", "type": "quantitative", "label": "Minutes"},
                    {"field": "wait_coverage_rate", "type": "quantitative", "label": "Eligibility", "format": "percent"},
                ],
            },
        },
        {
            "id": "monthly_economics_chart",
            "title": "Passenger base fare and driver pay per completed trip",
            "subtitle": "May 2025–May 2026 · eligible observations · USD per trip",
            "type": "line",
            "intent": "trend",
            "question": "How did passenger base fare and reported driver pay per trip move over time?",
            "rationale": "Two same-unit lines compare the separate passenger and driver measures without implying a margin relationship.",
            "combinationRationale": "Both series are monthly averages in USD per eligible completed trip; they remain analytically separate.",
            "dataset": "economics_trend",
            "sourceId": "monthly_metrics_analysis",
            "layout": "full",
            "valueFormat": "currency",
            "encodings": {
                "x": {"field": "month", "type": "temporal", "label": "Month"},
                "y": {"field": "value_usd_per_trip", "type": "quantitative", "label": "USD per trip"},
                "color": {"field": "metric", "type": "nominal", "label": "Measure"},
                "tooltip": [
                    {"field": "metric", "type": "nominal", "label": "Measure"},
                    {"field": "value_usd_per_trip", "type": "quantitative", "label": "USD per trip", "format": "currency"},
                    {"field": "trips", "type": "quantitative", "label": "Completed trips"},
                ],
            },
        },
    ]

    page_1_summary = f"""## Growth quality at a glance

May 2026 completed trips rose **{pct(trips['change_pct'])}** year over year to **{trips['may_2026'] / 1_000_000:.2f}M**. Average Request-to-Pickup Time increased **{pct(avg_wait['change_pct'])}** to **{avg_wait['may_2026']:.2f} minutes**, while P90 increased **{pct(p90_wait['change_pct'])}** to **{p90_wait['may_2026']:.2f} minutes**. The long-wait tail therefore deteriorated faster than trip volume grew.

Passenger base fare and driver pay are shown as separate per-trip measures. The dashboard does not use their difference as platform revenue, profit, margin, or take rate. Completed-trip data shows observed service pressure; it does not establish unserved demand or a causal supply shortage.
"""

    page_1 = artifact(
        title="Uber NYC Final Dashboard — Marketplace Overview",
        description="Executive view of completed-trip scale, growth, service quality, passenger base fare, and driver pay.",
        generated_at=generated_at,
        cards=page_1_cards,
        charts=page_1_charts,
        tables=[],
        blocks=[
            {"id": "navigation", "type": "markdown", "body": nav(1)},
            {"id": "growth_quality_summary", "type": "markdown", "body": page_1_summary, "sourceId": "deep_analysis_summary"},
            {"id": "headline_metrics", "type": "metric-strip", "cardIds": [card["id"] for card in page_1_cards]},
            {"id": "monthly_trips_block", "type": "chart", "chartId": "monthly_trips_chart", "layout": "half"},
            {"id": "monthly_wait_block", "type": "chart", "chartId": "monthly_wait_chart", "layout": "half"},
            {"id": "monthly_economics_block", "type": "chart", "chartId": "monthly_economics_chart", "layout": "full"},
        ],
        datasets={
            "headline": page_1_headline,
            "monthly_trend": monthly,
            "monthly_wait_trend": wait_trend,
            "economics_trend": economics_trend,
        },
        sources=sources,
        source_ids=["deep_analysis_summary", "monthly_metrics_analysis"],
    )

    priority_trip_total = sum(float(row["trips_2026_05"]) for row in priority_zones)
    airport_priority = [row for row in priority_zones if "Airport" in str(row["zone"])]
    airport_excess_total = sum(float(row["estimated_excess_request_to_pickup_minutes"]) for row in airport_priority)
    page_2_headline = [
        {
            "priority_zone_count": len(priority_zones),
            "priority_zone_trips": priority_trip_total,
            "priority_zone_trip_share": priority_trip_total / trips["may_2026"],
            "airport_priority_zone_count": len(airport_priority),
            "airport_excess_minutes": airport_excess_total,
        }
    ]

    page_2_cards = [
        make_card(
            card_id="priority_zone_count_card",
            description="Taxi zones classified as the operating-priority proxy: top-quartile completed-trip demand and above-city Request-to-Pickup Time.",
            dataset="efficiency_headline",
            source_id="zone_priority_analysis",
            metrics=[{"label": "Priority proxy zones", "field": "priority_zone_count", "format": "number"}],
        ),
        make_card(
            card_id="priority_trip_card",
            description="May 2026 completed trips beginning in priority-proxy zones.",
            dataset="efficiency_headline",
            source_id="zone_priority_analysis",
            metrics=[
                {"label": "Trips in priority zones", "field": "priority_zone_trips", "format": "number"},
                {"label": "Share of city trips", "field": "priority_zone_trip_share", "format": "percent"},
            ],
        ),
        make_card(
            card_id="airport_burden_card",
            description="Estimated excess Request-to-Pickup minutes in LaGuardia and JFK versus the city average; a completed-trip burden proxy.",
            dataset="efficiency_headline",
            source_id="zone_priority_analysis",
            metrics=[
                {"label": "Airport excess minutes", "field": "airport_excess_minutes", "format": "number"},
                {"label": "Airport zones", "field": "airport_priority_zone_count", "format": "number"},
            ],
        ),
    ]

    priority_top_12 = priority_zones[:12]
    priority_top_15 = priority_zones[:15]
    page_2_charts = [
        {
            "id": "zone_operating_matrix",
            "title": "Taxi-zone operating matrix",
            "subtitle": "Bubble size = May 2026 completed trips · X = YoY growth · Y = average Request-to-Pickup Time · five-borough zones with ≥500 trips in each May",
            "type": "scatter",
            "intent": "relationship",
            "question": "Which taxi zones combine material completed-trip demand, elevated Request-to-Pickup Time, and growth?",
            "rationale": "A bubble scatter shows growth, wait, and demand at one consistent taxi-zone grain.",
            "combinationRationale": "Growth, wait, and trip volume use the same May 2026 versus May 2025 taxi-zone population and filters.",
            "dataset": "zone_scatter",
            "sourceId": "zone_priority_analysis",
            "layout": "full",
            "valueFormat": "number",
            "referenceLines": [
                {"axis": "x", "value": 0, "label": "0% growth", "color": "neutral", "lineStyle": "dashed"},
                {"axis": "y", "value": avg_wait["may_2026"], "label": "City average", "color": "neutral", "lineStyle": "dashed"},
            ],
            "encodings": {
                "x": {"field": "trip_growth_rate", "type": "quantitative", "label": "YoY completed-trip growth", "format": "percent"},
                "y": {"field": "avg_wait_2026_05", "type": "quantitative", "label": "Avg Request-to-Pickup (min)"},
                "size": {"field": "trips_2026_05", "type": "quantitative", "label": "May 2026 trips"},
                "color": {"field": "marketplace_quadrant", "type": "nominal", "label": "Operating segment"},
                "tooltip": [
                    {"field": "zone_label", "type": "nominal", "label": "Pickup zone"},
                    {"field": "trips_2026_05", "type": "quantitative", "label": "May 2026 trips"},
                    {"field": "trip_growth_rate", "type": "quantitative", "label": "YoY trip growth", "format": "percent"},
                    {"field": "avg_wait_2026_05", "type": "quantitative", "label": "Avg request-to-pickup"},
                    {"field": "avg_wait_change_rate", "type": "quantitative", "label": "YoY wait change", "format": "percent"},
                    {"field": "estimated_excess_request_to_pickup_minutes", "type": "quantitative", "label": "Estimated excess minutes"},
                ],
            },
        },
        {
            "id": "priority_zone_burden",
            "title": "Highest estimated excess Request-to-Pickup burden",
            "subtitle": "May 2026 · top 12 priority-proxy pickup zones · excess minutes versus city average",
            "type": "bar",
            "intent": "ranking",
            "question": "Which priority-proxy zones carry the largest completed-trip wait burden?",
            "rationale": "A sorted full-width bar chart supports direct ranking across the 12 largest taxi-zone burdens.",
            "dataset": "priority_top_12",
            "sourceId": "zone_priority_analysis",
            "layout": "full",
            "valueFormat": "number",
            "encodings": {
                "x": {"field": "zone", "type": "nominal", "label": "Pickup zone"},
                "y": {"field": "estimated_excess_request_to_pickup_minutes", "type": "quantitative", "label": "Estimated excess minutes"},
                "tooltip": [
                    {"field": "trips_2026_05", "type": "quantitative", "label": "May 2026 trips"},
                    {"field": "trip_growth_rate", "type": "quantitative", "label": "YoY trip growth", "format": "percent"},
                    {"field": "avg_wait_2026_05", "type": "quantitative", "label": "Avg request-to-pickup"},
                    {"field": "avg_wait_change_rate", "type": "quantitative", "label": "YoY wait change", "format": "percent"},
                ],
            },
        },
    ]

    page_2_table = {
        "id": "priority_zone_table",
        "title": "Priority-proxy zone detail",
        "subtitle": "Top 15 zones by estimated excess Request-to-Pickup minutes; May 2026",
        "dataset": "priority_top_15",
        "sourceId": "zone_priority_analysis",
        "layout": "full",
        "defaultSort": {"field": "estimated_excess_request_to_pickup_minutes", "direction": "desc"},
        "columns": [
            {"field": "zone_label", "label": "Pickup zone", "type": "text"},
            {"field": "trips_2026_05", "label": "May trips", "format": "number"},
            {"field": "trip_growth_rate", "label": "Trip growth", "format": "percent", "movement": True},
            {"field": "avg_wait_2026_05", "label": "Avg wait", "format": "number"},
            {"field": "avg_wait_change_rate", "label": "Wait change", "format": "percent", "movement": True},
            {"field": "wait_gap_to_city_minutes", "label": "Gap vs city", "format": "number", "movement": True},
            {"field": "estimated_excess_request_to_pickup_minutes", "label": "Excess minutes", "format": "number"},
        ],
    }

    page_2_summary = f"""## Regional diagnosis

The operating-priority proxy identifies **{len(priority_zones)} taxi zones** with **{priority_trip_total / 1_000_000:.2f}M completed trips**, or **{priority_trip_total / trips['may_2026']:.1%}** of May 2026 city volume. LaGuardia and JFK rank first and second by estimated excess Request-to-Pickup burden, together accounting for roughly **{airport_excess_total / 1_000_000:.2f}M excess minutes** versus the city average.

The matrix is the regional equivalent of a map for this management view: demand is encoded by bubble size, growth on the horizontal axis, service pressure on the vertical axis, and the operating segment by color. “Supply-constrained priority” is a prioritization label based on observed completed trips and wait performance—not proof of an underlying supply shortage.
"""

    page_2 = artifact(
        title="Uber NYC Final Dashboard — Marketplace Efficiency",
        description="Taxi-zone operating matrix and ranked regional priorities across demand, Request-to-Pickup Time, and growth.",
        generated_at=generated_at,
        cards=page_2_cards,
        charts=page_2_charts,
        tables=[page_2_table],
        blocks=[
            {"id": "navigation", "type": "markdown", "body": nav(2)},
            {"id": "regional_summary", "type": "markdown", "body": page_2_summary, "sourceId": "zone_priority_analysis"},
            {"id": "efficiency_metrics", "type": "metric-strip", "cardIds": [card["id"] for card in page_2_cards]},
            {"id": "zone_matrix_block", "type": "chart", "chartId": "zone_operating_matrix", "layout": "full"},
            {"id": "zone_burden_block", "type": "chart", "chartId": "priority_zone_burden", "layout": "full"},
            {"id": "priority_zone_table_block", "type": "table", "tableId": "priority_zone_table", "layout": "full"},
        ],
        datasets={
            "efficiency_headline": page_2_headline,
            "zone_scatter": zone_scatter,
            "priority_top_12": priority_top_12,
            "priority_top_15": priority_top_15,
        },
        sources=sources,
        source_ids=["zone_priority_analysis"],
    )

    borough_by_name = {row["borough"]: row for row in borough}
    core_growth = float(borough_by_name["Manhattan"]["trip_delta"]) + float(borough_by_name["Brooklyn"]["trip_delta"])
    top_hour = max(hourly, key=lambda row: float(row["avg_wait_change_rate"]))
    top_window = priority_windows[0]
    neighborhood_priority = [row for row in priority_zones if "Airport" not in str(row["zone"])][:10]
    airport_windows = [row for row in priority_windows if "Airport" in str(row["zone"])][:12]
    page_3_headline = [
        {
            "manhattan_brooklyn_increment": core_growth,
            "manhattan_brooklyn_share": core_growth / trips["absolute_change"],
            "within_borough_wait_minutes": wait_decomp["within_borough_contribution_minutes"],
            "geographic_mix_wait_minutes": wait_decomp["geographic_mix_contribution_minutes"],
            "peak_hour": str(top_hour["pickup_hour_label"]),
            "peak_hour_wait_change_rate": top_hour["avg_wait_change_rate"],
            "top_window_excess_minutes_per_day": top_window["estimated_excess_request_to_pickup_minutes_per_day"],
        }
    ]

    page_3_cards = [
        make_card(
            card_id="core_growth_card",
            description="Combined completed-trip increase from Manhattan and Brooklyn; the share exceeds 100% because other boroughs offset part of the gain.",
            dataset="priority_headline",
            source_id="borough_analysis",
            metrics=[
                {"label": "Manhattan + Brooklyn", "field": "manhattan_brooklyn_increment", "format": "number"},
                {"label": "Share of net city growth", "field": "manhattan_brooklyn_share", "format": "percent"},
            ],
        ),
        make_card(
            card_id="within_borough_card",
            description="Citywide Request-to-Pickup increase attributable to within-borough movement in the validated decomposition.",
            dataset="priority_headline",
            source_id="borough_analysis",
            metrics=[
                {"label": "Within-borough wait effect", "field": "within_borough_wait_minutes", "format": "number", "unit": "min"},
                {"label": "Geographic mix effect", "field": "geographic_mix_wait_minutes", "format": "number", "unit": "min", "signed": True},
            ],
        ),
        make_card(
            card_id="peak_hour_card",
            description="Pickup hour with the largest May year-over-year average Request-to-Pickup increase.",
            dataset="priority_headline",
            source_id="hourly_analysis",
            metrics=[
                {"label": "Peak hourly wait change", "field": "peak_hour_wait_change_rate", "format": "percent", "signed": True},
                {"label": "Pickup hour", "field": "peak_hour", "format": "text"},
            ],
        ),
        make_card(
            card_id="top_window_card",
            description="Top recurring weekday-hour-zone window by estimated excess Request-to-Pickup minutes per contributing day.",
            dataset="priority_headline",
            source_id="priority_window_analysis",
            metrics=[
                {"label": "Top-window excess min/day", "field": "top_window_excess_minutes_per_day", "format": "number"},
            ],
        ),
    ]

    page_3_charts = [
        {
            "id": "borough_growth_contribution",
            "title": "Contribution to city completed-trip growth by borough",
            "subtitle": "May 2026 versus May 2025 · signed share of net city trip change",
            "type": "bar",
            "intent": "comparison",
            "question": "Which boroughs contributed to or offset city completed-trip growth?",
            "rationale": "A signed bar chart makes positive and negative growth contributions directly comparable.",
            "dataset": "borough_yoy",
            "sourceId": "borough_analysis",
            "layout": "half",
            "valueFormat": "percent",
            "referenceLines": [{"axis": "y", "value": 0, "label": "No contribution", "color": "neutral", "lineStyle": "solid"}],
            "encodings": {
                "x": {"field": "borough", "type": "nominal", "label": "Pickup borough"},
                "y": {"field": "contribution_to_growth_rate", "type": "quantitative", "label": "Contribution to city growth"},
                "tooltip": [
                    {"field": "trip_delta", "type": "quantitative", "label": "Trip delta"},
                    {"field": "trip_growth_rate", "type": "quantitative", "label": "Borough trip growth", "format": "percent"},
                ],
            },
        },
        {
            "id": "borough_wait_change",
            "title": "Average Request-to-Pickup change by borough",
            "subtitle": "May 2026 versus May 2025 · eligible completed trips",
            "type": "bar",
            "intent": "comparison",
            "question": "Where did average Request-to-Pickup deteriorate most?",
            "rationale": "A common-scale bar chart compares the five borough year-over-year changes.",
            "dataset": "borough_yoy",
            "sourceId": "borough_analysis",
            "layout": "half",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "borough", "type": "nominal", "label": "Pickup borough"},
                "y": {"field": "avg_wait_change_rate", "type": "quantitative", "label": "YoY wait change"},
                "tooltip": [
                    {"field": "avg_wait_2025_05", "type": "quantitative", "label": "May 2025 avg wait"},
                    {"field": "avg_wait_2026_05", "type": "quantitative", "label": "May 2026 avg wait"},
                    {"field": "trip_growth_rate", "type": "quantitative", "label": "Trip growth", "format": "percent"},
                ],
            },
        },
        {
            "id": "hourly_wait_change",
            "title": "Average Request-to-Pickup change by pickup hour",
            "subtitle": "May 2026 versus May 2025 · 24 citywide pickup hours",
            "type": "bar",
            "intent": "comparison",
            "question": "Which hours carry the greatest year-over-year service deterioration?",
            "rationale": "An ordered hourly bar chart exposes peak-pressure windows while preserving the daily sequence.",
            "dataset": "hourly_yoy",
            "sourceId": "hourly_analysis",
            "layout": "full",
            "valueFormat": "percent",
            "encodings": {
                "x": {"field": "pickup_hour_label", "type": "ordinal", "label": "Pickup hour"},
                "y": {"field": "avg_wait_change_rate", "type": "quantitative", "label": "YoY wait change"},
                "tooltip": [
                    {"field": "trip_growth_rate", "type": "quantitative", "label": "Trip growth", "format": "percent"},
                    {"field": "contribution_to_growth_rate", "type": "quantitative", "label": "Contribution to city growth", "format": "percent"},
                    {"field": "avg_wait_2026_05", "type": "quantitative", "label": "May 2026 avg wait"},
                ],
            },
        },
    ]

    airport_table = {
        "id": "airport_windows_table",
        "title": "Highest-priority airport operating windows",
        "subtitle": "Top 12 recurring May 2026 airport weekday-hour windows by estimated excess minutes per contributing day",
        "dataset": "airport_windows",
        "sourceId": "priority_window_analysis",
        "layout": "full",
        "defaultSort": {"field": "estimated_excess_request_to_pickup_minutes_per_day", "direction": "desc"},
        "columns": [
            {"field": "weekday_name", "label": "Weekday", "type": "text"},
            {"field": "pickup_hour_label", "label": "Hour", "type": "text"},
            {"field": "zone_label", "label": "Pickup zone", "type": "text"},
            {"field": "avg_trips_per_contributing_day", "label": "Trips/day", "format": "number"},
            {"field": "avg_request_to_pickup_minutes", "label": "Avg wait", "format": "number"},
            {"field": "wait_gap_to_city_minutes", "label": "Gap vs city", "format": "number", "movement": True},
            {"field": "estimated_excess_request_to_pickup_minutes_per_day", "label": "Excess min/day", "format": "number"},
        ],
    }
    neighborhood_table = {
        "id": "neighborhood_priority_table",
        "title": "Highest-priority non-airport neighborhoods",
        "subtitle": "Top 10 priority-proxy pickup zones excluding JFK and LaGuardia; May 2026",
        "dataset": "neighborhood_priority",
        "sourceId": "zone_priority_analysis",
        "layout": "full",
        "defaultSort": {"field": "estimated_excess_request_to_pickup_minutes", "direction": "desc"},
        "columns": [
            {"field": "zone_label", "label": "Pickup zone", "type": "text"},
            {"field": "trips_2026_05", "label": "May trips", "format": "number"},
            {"field": "trip_growth_rate", "label": "Trip growth", "format": "percent", "movement": True},
            {"field": "avg_wait_2026_05", "label": "Avg wait", "format": "number"},
            {"field": "avg_wait_change_rate", "label": "Wait change", "format": "percent", "movement": True},
            {"field": "estimated_excess_request_to_pickup_minutes", "label": "Excess minutes", "format": "number"},
        ],
    }

    page_3_summary = f"""## Operating priorities

Manhattan and Brooklyn added **{core_growth:,.0f} completed trips**, equivalent to **{core_growth / trips['absolute_change']:.1%}** of net city growth because declines elsewhere offset part of their increase. The wait decomposition assigns **{wait_decomp['within_borough_contribution_minutes']:.3f} minutes** of the citywide change to within-borough movement, while geographic mix contributed **{wait_decomp['geographic_mix_contribution_minutes']:.3f} minutes** and slightly offset the deterioration.

The hourly view identifies **{top_hour['pickup_hour_label']}** as the largest year-over-year wait increase at **{top_hour['avg_wait_change_rate']:.1%}**. The recurring-window ranking is dominated by JFK and LaGuardia late-evening and overnight periods, while the neighborhood list concentrates on Harlem, Brownsville, Crown Heights, Canarsie, Stuyvesant Heights, Bushwick, Mott Haven, and East New York.
"""

    actions = """## Recommended actions

1. **Protect airport service quality.** Review late-evening and overnight operating playbooks at JFK and LaGuardia, beginning with the highest-burden weekday-hour windows in the table.
2. **Target neighborhood diagnostics before broad demand stimulation.** Prioritize localized dispatch, driver-positioning, and pickup-process tests in the ranked Harlem, Brooklyn, and Bronx zones; measure completed trips and Request-to-Pickup together.
3. **Treat 00:00–07:00 as a focused service-recovery window.** Diagnose the 03:00–06:00 wait increase and evaluate targeted interventions with citywide and zone-level guardrails.
4. **Add the missing causal evidence before making supply claims.** Join cancellations, driver online time, dispatch acceptance, surge, promotions, and pickup-process data before attributing the observed patterns to supply shortage or estimating financial impact.
"""

    page_3 = artifact(
        title="Uber NYC Final Dashboard — Growth Quality & Operating Priorities",
        description="Borough, hour, airport, and neighborhood priorities with evidence-bounded recommended actions.",
        generated_at=generated_at,
        cards=page_3_cards,
        charts=page_3_charts,
        tables=[airport_table, neighborhood_table],
        blocks=[
            {"id": "navigation", "type": "markdown", "body": nav(3)},
            {"id": "priority_summary", "type": "markdown", "body": page_3_summary},
            {"id": "priority_metrics", "type": "metric-strip", "cardIds": [card["id"] for card in page_3_cards]},
            {"id": "borough_growth_block", "type": "chart", "chartId": "borough_growth_contribution", "layout": "half"},
            {"id": "borough_wait_block", "type": "chart", "chartId": "borough_wait_change", "layout": "half"},
            {"id": "hourly_wait_block", "type": "chart", "chartId": "hourly_wait_change", "layout": "full"},
            {"id": "airport_windows_block", "type": "table", "tableId": "airport_windows_table", "layout": "full"},
            {"id": "neighborhood_priority_block", "type": "table", "tableId": "neighborhood_priority_table", "layout": "full"},
            {"id": "recommended_actions", "type": "markdown", "body": actions},
        ],
        datasets={
            "priority_headline": page_3_headline,
            "borough_yoy": borough,
            "wait_decomposition": decomposition,
            "hourly_yoy": hourly,
            "airport_windows": airport_windows,
            "neighborhood_priority": neighborhood_priority,
        },
        sources=sources,
        source_ids=["borough_analysis", "hourly_analysis", "priority_window_analysis", "zone_priority_analysis"],
    )

    validation_rows: list[dict[str, Any]] = []

    def check(name: str, actual: Any, expected: Any, passed: bool) -> None:
        validation_rows.append(
            {"check_name": name, "actual": actual, "expected": expected, "passed": bool(passed)}
        )

    analysis_validation_path = analysis_dir / "analysis_validation.csv"
    with analysis_validation_path.open("r", encoding="utf-8-sig", newline="") as handle:
        upstream_checks = list(csv.DictReader(handle))
    check(
        "upstream deep-analysis validation",
        sum(row["passed"].lower() == "true" for row in upstream_checks),
        len(upstream_checks),
        all(row["passed"].lower() == "true" for row in upstream_checks),
    )
    check("monthly row count", len(monthly), 13, len(monthly) == 13)
    check("monthly wait row count", len(wait_trend), 39, len(wait_trend) == 39)
    check("latest trips reconcile", monthly[-1]["trips"], trips["may_2026"], float(monthly[-1]["trips"]) == float(trips["may_2026"]))
    check("latest average wait reconcile", monthly[-1]["avg_request_to_pickup_minutes"], avg_wait["may_2026"], abs(float(monthly[-1]["avg_request_to_pickup_minutes"]) - float(avg_wait["may_2026"])) < 1e-9)
    check("latest P90 wait reconcile", monthly[-1]["p90_request_to_pickup_minutes"], p90_wait["may_2026"], abs(float(monthly[-1]["p90_request_to_pickup_minutes"]) - float(p90_wait["may_2026"])) < 1e-9)
    five_borough_trips = sum(float(row["trips_2026_05"]) for row in borough)
    check(
        "five-borough current-trip coverage",
        five_borough_trips / float(trips["may_2026"]),
        ">= 99.99%",
        five_borough_trips / float(trips["may_2026"]) >= 0.9999,
    )
    check(
        "non-five-borough current-trip residual",
        float(trips["may_2026"]) - five_borough_trips,
        815,
        abs(float(trips["may_2026"]) - five_borough_trips - 815) < 1e-6,
    )
    check("priority zone count", len(priority_zones), 23, len(priority_zones) == 23)
    check("priority zone trip total", priority_trip_total, 2_990_216, abs(priority_trip_total - 2_990_216) < 1e-6)
    check("hourly row count", len(hourly), 24, len(hourly) == 24)
    check("hour current trips reconcile", sum(float(row["trips_2026_05"]) for row in hourly), trips["may_2026"], abs(sum(float(row["trips_2026_05"]) for row in hourly) - float(trips["may_2026"])) < 1e-6)
    check("wait decomposition reconcile", wait_decomp["total_change_minutes"], avg_wait["absolute_change"], abs(float(wait_decomp["total_change_minutes"]) - float(avg_wait["absolute_change"])) <= 0.001)
    check("page count", 3, 3, True)

    chart_map = [
        {"page": 1, "chart_id": "monthly_trips_chart", "question": "Monthly completed-trip movement", "family": "Trend", "takeaway": "Volume fluctuated seasonally and finished May 2026 2.1% above May 2025.", "palette_policy": "single-root preferred"},
        {"page": 1, "chart_id": "monthly_wait_chart", "question": "Wait center and tail movement", "family": "Trend", "takeaway": "The P90 wait tail deteriorated faster than the average.", "palette_policy": "relaxed multi-category"},
        {"page": 1, "chart_id": "monthly_economics_chart", "question": "Passenger fare and driver pay movement", "family": "Trend", "takeaway": "The separate per-trip measures moved in parallel over the comparison year.", "palette_policy": "hard two-root cap"},
        {"page": 2, "chart_id": "zone_operating_matrix", "question": "Demand × wait × growth by taxi zone", "family": "Relationship", "takeaway": "Priority-proxy zones combine material completed-trip demand and above-city wait; airports carry the largest burden.", "palette_policy": "relaxed multi-category"},
        {"page": 2, "chart_id": "priority_zone_burden", "question": "Ranked excess wait burden", "family": "Comparison & Ranking", "takeaway": "LaGuardia and JFK rank first and second by estimated excess minutes.", "palette_policy": "single-root preferred"},
        {"page": 3, "chart_id": "borough_growth_contribution", "question": "Borough growth contribution", "family": "Comparison", "takeaway": "Manhattan and Brooklyn generated more than the net city increase because declines elsewhere offset growth.", "palette_policy": "hard two-root cap"},
        {"page": 3, "chart_id": "borough_wait_change", "question": "Borough wait deterioration", "family": "Comparison", "takeaway": "Wait increased in every borough, led by the Bronx, Queens, and Brooklyn.", "palette_policy": "single-root preferred"},
        {"page": 3, "chart_id": "hourly_wait_change", "question": "Hourly wait deterioration", "family": "Comparison", "takeaway": "The largest increases cluster in the overnight and early-morning hours.", "palette_policy": "single-root preferred"},
    ]

    pages = {
        "page_1_marketplace_overview": page_1,
        "page_2_marketplace_efficiency": page_2,
        "page_3_operating_priorities": page_3,
    }
    return pages, validation_rows, chart_map


def write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0].keys()))
        writer.writeheader()
        writer.writerows(rows)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--project-dir", type=Path, default=Path(__file__).resolve().parents[1]
    )
    parser.add_argument("--output-dir", type=Path, default=None)
    parser.add_argument("--skip-html", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    project_dir = args.project_dir.resolve()
    output_dir = (args.output_dir or project_dir / "dashboard").resolve()
    analysis_dir = project_dir / "data" / "processed" / "analysis"
    required = [
        analysis_dir / "analysis_summary.json",
        analysis_dir / "analysis_validation.csv",
        analysis_dir / "monthly_trend.parquet",
        analysis_dir / "monthly_wait_trend.parquet",
        analysis_dir / "borough_yoy.parquet",
        analysis_dir / "wait_change_decomposition.parquet",
        analysis_dir / "zone_yoy.parquet",
        analysis_dir / "hourly_yoy.parquet",
        analysis_dir / "priority_windows.parquet",
    ]
    missing = [path for path in required if not path.is_file()]
    if missing:
        raise FileNotFoundError("Missing validated dashboard inputs:\n" + "\n".join(map(str, missing)))

    pages, validation_rows, chart_map = build_pages(project_dir)
    failed_checks = [row for row in validation_rows if not row["passed"]]
    if failed_checks:
        raise RuntimeError("Dashboard numerical QA failed:\n" + json.dumps(failed_checks, indent=2, default=str))

    artifacts_dir = output_dir / "artifacts"
    for slug, _ in PAGES:
        write_json_atomic(artifacts_dir / f"{slug}.artifact.json", pages[slug])

    write_csv(output_dir / "qa" / "dashboard_validation.csv", validation_rows)
    write_csv(output_dir / "qa" / "chart_map.csv", chart_map)

    renderer_receipt: dict[str, Any] | None = None
    if not args.skip_html:
        renderer_candidates = [
            Path(__file__).resolve().with_name("render_unified_dashboard.py"),
            output_dir / "render_unified_dashboard.py",
        ]
        renderer = next((path for path in renderer_candidates if path.is_file()), None)
        if renderer is None:
            raise FileNotFoundError(
                "render_unified_dashboard.py was not found next to the build script or in the output directory."
            )
        result = subprocess.run(
            [sys.executable, str(renderer), "--output-root", str(output_dir)],
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            check=False,
        )
        renderer_receipt = {
            "renderer": "scripts/render_unified_dashboard.py",
            "returncode": result.returncode,
            "status": "ok" if result.returncode == 0 else "failed",
            "html": "dashboard/uber_nyc_final_dashboard.html",
        }
        write_json_atomic(output_dir / "qa" / "build_receipts.json", renderer_receipt)
        if result.returncode != 0:
            raise RuntimeError(
                "Unified dashboard rendering failed:\n" + result.stdout + "\n" + result.stderr
            )
    else:
        write_json_atomic(
            output_dir / "dashboard_manifest.json",
            {
                "title": "Uber NYC Final Dashboard",
                "generated_at_utc": datetime.now(timezone.utc).isoformat(),
                "primary_dashboard": None,
                "source_artifacts": [f"artifacts/{slug}.artifact.json" for slug, _ in PAGES],
                "qa": {"numerical": "qa/dashboard_validation.csv", "chart_map": "qa/chart_map.csv"},
                "interpretation_boundary": summary_boundary(project_dir),
            },
        )

    print(f"Dashboard package written to: {output_dir}")
    print(f"Pages: {len(pages)}")
    print(f"Numerical QA checks passed: {len(validation_rows)}")
    if renderer_receipt:
        print("Unified three-page HTML packaged successfully.")
    return 0


def summary_boundary(project_dir: Path) -> str:
    with (project_dir / "data" / "processed" / "analysis" / "analysis_summary.json").open(
        "r", encoding="utf-8"
    ) as handle:
        return json.load(handle)["interpretation_boundary"]


if __name__ == "__main__":
    raise SystemExit(main())
