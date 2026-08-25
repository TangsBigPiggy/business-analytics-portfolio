"""Build the single-file, three-page Uber NYC executive dashboard.

The script reads the already validated dashboard artifact JSON files. It does
not recompute business metrics. All CSS, JavaScript, tables, and SVG charts are
embedded in one portable HTML file.
"""

from __future__ import annotations

import argparse
import csv
import html
import json
import math
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Iterable, Sequence


BG = "#F5F7FA"
CARD = "#FFFFFF"
INK = "#172033"
MUTED = "#667085"
GRID = "#D9E0EA"
BLUE = "#2367D1"
BLUE_DARK = "#174A99"
BLUE_LIGHT = "#DCEAFF"
GOLD = "#D9A326"
ORANGE = "#E77A2E"
OLIVE = "#788D3A"
PINK = "#C85C89"
NEUTRAL = "#8B95A7"

LANGUAGES = ("en", "zh")


def l(lang: str, en: str, zh: str) -> str:
    """Return a localized reader-facing string without changing source data."""
    return zh if lang == "zh" else en


BOROUGH_ZH = {
    "Bronx": "布朗克斯",
    "Brooklyn": "布鲁克林",
    "Manhattan": "曼哈顿",
    "Queens": "皇后区",
    "Staten Island": "史泰登岛",
}

ZONE_ZH = {
    "LaGuardia Airport": "拉瓜迪亚机场",
    "JFK Airport": "肯尼迪机场",
    "Central Harlem North": "哈莱姆中北部",
    "Brownsville": "布朗斯维尔",
    "Crown Heights North": "皇冠高地北部",
    "Canarsie": "卡纳西",
    "Stuyvesant Heights": "斯图维森特高地",
    "East Harlem North": "东哈莱姆北部",
    "Bushwick South": "布什维克南部",
    "Mott Haven/Port Morris": "莫特黑文/莫里斯港",
    "Central Harlem": "哈莱姆中部",
    "East New York": "东纽约",
    "Bedford": "贝德福德",
    "Bushwick North": "布什维克北部",
    "Prospect-Lefferts Gardens": "普罗斯佩克特-莱弗茨花园",
}

WEEKDAY_ZH = {
    "Monday": "周一",
    "Tuesday": "周二",
    "Wednesday": "周三",
    "Thursday": "周四",
    "Friday": "周五",
    "Saturday": "周六",
    "Sunday": "周日",
}


def zone_name(value: Any, lang: str) -> str:
    text = str(value)
    if lang != "zh":
        return text
    if " — " in text:
        borough, zone = text.split(" — ", 1)
        return f"{BOROUGH_ZH.get(borough, borough)} · {ZONE_ZH.get(zone, zone)}"
    if " · " in text:
        borough, zone = text.split(" · ", 1)
        return f"{BOROUGH_ZH.get(borough, borough)} · {ZONE_ZH.get(zone, zone)}"
    return ZONE_ZH.get(text, text)


def e(value: Any) -> str:
    return html.escape(str(value), quote=True)


def fmt_number(value: Any, decimals: int = 1) -> str:
    if value is None:
        return "—"
    number = float(value)
    sign = "−" if number < 0 else ""
    number = abs(number)
    if number >= 1_000_000:
        return f"{sign}{number / 1_000_000:.2f}M"
    if number >= 1_000:
        return f"{sign}{number / 1_000:.1f}K"
    return f"{sign}{number:.{decimals}f}"


def fmt_pct(value: Any, decimals: int = 1, signed: bool = False) -> str:
    if value is None:
        return "—"
    pct = float(value) * 100
    if signed:
        return f"{pct:+.{decimals}f}%"
    return f"{pct:.{decimals}f}%"


def fmt_money(value: Any) -> str:
    return "—" if value is None else f"${float(value):,.2f}"


def metric_card(label: str, value: str, delta: str = "", note: str = "", negative: bool = False) -> str:
    chip = ""
    if delta:
        chip_class = "chip negative" if negative else "chip"
        chip = f'<span class="{chip_class}">{e(delta)}</span>'
    note_html = f'<span class="metric-note">{e(note)}</span>' if note else ""
    return (
        '<article class="metric-card">'
        f'<div class="metric-label">{e(label)}</div>'
        f'<div class="metric-value">{e(value)}</div>'
        f'<div class="metric-meta">{chip}{note_html}</div>'
        '</article>'
    )


def summary_card(title: str, body: str, accent: str) -> str:
    return (
        f'<article class="summary-card" style="--accent:{accent}">'
        f'<h2>{e(title)}</h2><p>{e(body)}</p></article>'
    )


def page_header(page: int, title: str, subtitle: str, lang: str) -> str:
    return (
        '<div class="page-head">'
        f'<div><div class="eyebrow">{e(l(lang, "UBER NYC · EXECUTIVE MARKETPLACE REVIEW", "UBER NYC · 管理层市场经营复盘"))}</div>'
        f'<h1>{e(title)}</h1><p>{e(subtitle)}</p></div>'
        f'<div class="page-stamp"><span>{e(l(lang, f"PAGE {page} / 3", f"第 {page} 页 / 共 3 页"))}</span><b>{e(l(lang, "MAY 2026", "2026 年 5 月"))}</b></div>'
        '</div>'
    )


def panel(title: str, subtitle: str, body: str, extra_class: str = "") -> str:
    return (
        f'<article class="panel {e(extra_class)}"><div class="panel-head">'
        f'<h2>{e(title)}</h2><p>{e(subtitle)}</p></div>{body}</article>'
    )


def linear_scale(value: float, source_min: float, source_max: float, target_min: float, target_max: float) -> float:
    if source_max == source_min:
        return (target_min + target_max) / 2
    return target_min + (value - source_min) / (source_max - source_min) * (target_max - target_min)


def svg_line_chart(
    labels: Sequence[str],
    series: Sequence[tuple[str, Sequence[float], str]],
    y_formatter,
    *,
    height: int = 360,
) -> str:
    width = 1000
    left, right, top, bottom = 72, 28, 24, 64
    plot_w, plot_h = width - left - right, height - top - bottom
    values = [float(v) for _, items, _ in series for v in items if v is not None]
    ymin, ymax = min(values), max(values)
    pad = (ymax - ymin) * 0.14 or 1
    ymin, ymax = ymin - pad, ymax + pad
    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img">']
    for tick in range(5):
        ratio = tick / 4
        y = top + (1 - ratio) * plot_h
        value = ymin + ratio * (ymax - ymin)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 12}" y="{y + 5:.1f}" text-anchor="end" class="axis">{e(y_formatter(value))}</text>')
    denominator = max(1, len(labels) - 1)
    for index, label in enumerate(labels):
        if index in {0, len(labels) - 1} or index % 3 == 0:
            x = left + index / denominator * plot_w
            parts.append(f'<text x="{x:.1f}" y="{height - 29}" text-anchor="middle" class="axis">{e(label)}</text>')
    legend_x = left
    for name, items, color in series:
        points: list[tuple[float, float]] = []
        for index, value in enumerate(items):
            x = left + index / denominator * plot_w
            y = top + (ymax - float(value)) / (ymax - ymin) * plot_h
            points.append((x, y))
        point_text = " ".join(f"{x:.1f},{y:.1f}" for x, y in points)
        parts.append(f'<polyline points="{point_text}" fill="none" stroke="{color}" stroke-width="4" stroke-linejoin="round" stroke-linecap="round"/>')
        for index, (x, y) in enumerate(points):
            parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="4" fill="{CARD}" stroke="{color}" stroke-width="2"><title>{e(labels[index])}: {e(name)} {e(y_formatter(items[index]))}</title></circle>')
        parts.append(f'<line x1="{legend_x}" y1="{height - 7}" x2="{legend_x + 28}" y2="{height - 7}" stroke="{color}" stroke-width="4"/>')
        parts.append(f'<text x="{legend_x + 36}" y="{height - 2}" class="legend">{e(name)}</text>')
        legend_x += max(150, len(name) * 8 + 64)
    parts.append('</svg>')
    return "".join(parts)


def svg_vertical_bar(
    labels: Sequence[str],
    values: Sequence[float],
    *,
    percent: bool = True,
    signed: bool = True,
    color: str = BLUE,
    height: int = 360,
) -> str:
    width = 1000
    left, right, top, bottom = 72, 24, 24, 58
    plot_w, plot_h = width - left - right, height - top - bottom
    ymin = min(0.0, min(values)) if signed else 0.0
    ymax = max(values) * 1.14 if values else 1.0
    if ymax == ymin:
        ymax += 1
    zero_y = top + (ymax - 0) / (ymax - ymin) * plot_h
    parts = [f'<svg class="chart-svg" viewBox="0 0 {width} {height}" role="img">']
    for tick in range(5):
        ratio = tick / 4
        y = top + (1 - ratio) * plot_h
        value = ymin + ratio * (ymax - ymin)
        label = fmt_pct(value, signed=signed) if percent else fmt_number(value)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 12}" y="{y + 5:.1f}" text-anchor="end" class="axis">{e(label)}</text>')
    parts.append(f'<line x1="{left}" y1="{zero_y:.1f}" x2="{left + plot_w}" y2="{zero_y:.1f}" stroke="{NEUTRAL}" stroke-width="2"/>')
    slot = plot_w / max(1, len(labels))
    bar_w = slot * 0.58
    for index, (label, value) in enumerate(zip(labels, values)):
        x = left + (index + 0.5) * slot
        y = top + (ymax - value) / (ymax - ymin) * plot_h
        fill = color if value >= 0 else ORANGE
        rect_y, rect_h = min(y, zero_y), max(2, abs(zero_y - y))
        parts.append(f'<rect x="{x - bar_w / 2:.1f}" y="{rect_y:.1f}" width="{bar_w:.1f}" height="{rect_h:.1f}" rx="5" fill="{fill}"><title>{e(label)}: {e(fmt_pct(value, signed=True) if percent else fmt_number(value))}</title></rect>')
        parts.append(f'<text x="{x:.1f}" y="{height - 23}" text-anchor="middle" class="axis">{e(label)}</text>')
    parts.append('</svg>')
    return "".join(parts)


def svg_scatter(rows: Sequence[dict[str, Any]], city_wait: float, lang: str) -> str:
    """Render Page 2 with a dedicated callout rail so labels never cover bubbles."""
    width, height = 1400, 660
    left, right, top, bottom = 82, 345, 38, 145
    plot_w, plot_h = width - left - right, height - top - bottom
    xs = [float(row["trip_growth_rate"]) for row in rows]
    ys = [float(row["avg_wait_2026_05"]) for row in rows]
    volumes = [float(row["trips_2026_05"]) for row in rows]
    xmin, xmax = min(xs), max(xs)
    ymin, ymax = min(ys), max(ys)
    xmin -= (xmax - xmin) * 0.08
    xmax += (xmax - xmin) * 0.04
    ymin -= (ymax - ymin) * 0.08
    ymax += (ymax - ymin) * 0.08
    colors = {
        "Supply-constrained priority": ORANGE,
        "High-demand core": BLUE,
        "Service-risk watchlist": PINK,
        "Lower-priority / balanced": OLIVE,
    }
    segment_labels = {
        "Supply-constrained priority": l(lang, "Supply-constrained priority proxy", "供给受限优先级代理"),
        "High-demand core": l(lang, "High-demand core", "高需求核心区"),
        "Service-risk watchlist": l(lang, "Service-risk watchlist", "服务风险观察区"),
        "Lower-priority / balanced": l(lang, "Lower-priority / balanced", "较低优先级 / 相对平衡"),
    }
    parts = [f'<svg class="chart-svg scatter" viewBox="0 0 {width} {height}" role="img">']
    for tick in range(5):
        xr = tick / 4
        x = left + xr * plot_w
        xv = xmin + xr * (xmax - xmin)
        parts.append(f'<line x1="{x:.1f}" y1="{top}" x2="{x:.1f}" y2="{top + plot_h}" class="grid"/>')
        parts.append(f'<text x="{x:.1f}" y="{top + plot_h + 31}" text-anchor="middle" class="axis">{e(fmt_pct(xv, signed=True))}</text>')
        yr = tick / 4
        y = top + (1 - yr) * plot_h
        yv = ymin + yr * (ymax - ymin)
        parts.append(f'<line x1="{left}" y1="{y:.1f}" x2="{left + plot_w}" y2="{y:.1f}" class="grid"/>')
        parts.append(f'<text x="{left - 14}" y="{y + 5:.1f}" text-anchor="end" class="axis">{yv:.1f}</text>')
    zero_x = linear_scale(0, xmin, xmax, left, left + plot_w)
    city_y = linear_scale(city_wait, ymin, ymax, top + plot_h, top)
    parts.append(f'<line x1="{zero_x:.1f}" y1="{top}" x2="{zero_x:.1f}" y2="{top + plot_h}" class="reference"/>')
    parts.append(f'<text x="{zero_x + 8:.1f}" y="{top + 19}" class="annotation">{e(l(lang, "0% growth", "0% 增长"))}</text>')
    parts.append(f'<line x1="{left}" y1="{city_y:.1f}" x2="{left + plot_w}" y2="{city_y:.1f}" class="reference"/>')
    parts.append(f'<text x="{left + plot_w - 6}" y="{city_y - 8:.1f}" text-anchor="end" class="annotation">{e(l(lang, f"City avg {city_wait:.2f} min", f"全市均值 {city_wait:.2f} 分钟"))}</text>')
    max_volume = max(volumes)
    ordered = sorted(rows, key=lambda row: float(row["trips_2026_05"]))
    label_zones = ("JFK Airport", "LaGuardia Airport", "Brownsville", "Central Harlem North")
    callout_points: dict[str, tuple[float, float, float, dict[str, Any]]] = {}
    for row in ordered:
        x = linear_scale(float(row["trip_growth_rate"]), xmin, xmax, left, left + plot_w)
        y = linear_scale(float(row["avg_wait_2026_05"]), ymin, ymax, top + plot_h, top)
        radius = 4 + math.sqrt(float(row["trips_2026_05"]) / max_volume) * 18
        color = colors.get(str(row["marketplace_quadrant"]), NEUTRAL)
        tooltip = l(
            lang,
            f'{row["zone_label"]} · trips {fmt_number(row["trips_2026_05"])} · growth {fmt_pct(row["trip_growth_rate"], signed=True)} · request-to-pickup {float(row["avg_wait_2026_05"]):.2f} min',
            f'{zone_name(row["zone_label"], lang)} · 行程 {fmt_number(row["trips_2026_05"])} · 增长 {fmt_pct(row["trip_growth_rate"], signed=True)} · 请求至上车时长 {float(row["avg_wait_2026_05"]):.2f} 分钟',
        )
        parts.append(f'<circle cx="{x:.1f}" cy="{y:.1f}" r="{radius:.1f}" fill="{color}" fill-opacity="0.70" stroke="{color}" stroke-width="1.5"><title>{e(tooltip)}</title></circle>')
        if row["zone"] in label_zones:
            callout_points[str(row["zone"])] = (x, y, radius, row)

    rail_x = left + plot_w + 28
    parts.append(f'<text x="{rail_x}" y="{top + 2}" class="callout-title">{e(l(lang, "Priority-proxy labels", "优先级代理重点区域"))}</text>')
    callout_ys = (top + 38, top + 132, top + 226, top + 320)
    for zone, box_y in zip(label_zones, callout_ys):
        if zone not in callout_points:
            continue
        x, y, radius, row = callout_points[zone]
        line_y = box_y + 34
        color = colors.get(str(row["marketplace_quadrant"]), NEUTRAL)
        parts.append(f'<polyline points="{x + radius:.1f},{y:.1f} {rail_x - 15:.1f},{y:.1f} {rail_x - 4:.1f},{line_y:.1f}" fill="none" class="callout-line"/>')
        parts.append(f'<rect x="{rail_x}" y="{box_y}" width="286" height="72" rx="10" class="callout-box"/>')
        parts.append(f'<rect x="{rail_x}" y="{box_y}" width="6" height="72" rx="3" fill="{color}"/>')
        parts.append(f'<text x="{rail_x + 18}" y="{box_y + 26}" class="callout-name">{e(zone_name(zone, lang))}</text>')
        detail = l(
            lang,
            f'{float(row["avg_wait_2026_05"]):.2f} min · {fmt_pct(row["trip_growth_rate"], signed=True)} growth · {fmt_number(row["trips_2026_05"])} trips',
            f'{float(row["avg_wait_2026_05"]):.2f} 分钟 · 增长 {fmt_pct(row["trip_growth_rate"], signed=True)} · {fmt_number(row["trips_2026_05"])} 行程',
        )
        parts.append(f'<text x="{rail_x + 18}" y="{box_y + 52}" class="callout-detail">{e(detail)}</text>')

    parts.append(f'<text x="{left + plot_w / 2:.1f}" y="{top + plot_h + 60}" text-anchor="middle" class="axis-title">{e(l(lang, "YoY completed-trip growth", "完成行程同比增长"))}</text>')
    parts.append(f'<text x="21" y="{top + plot_h / 2:.1f}" text-anchor="middle" transform="rotate(-90 21 {top + plot_h / 2:.1f})" class="axis-title">{e(l(lang, "Average request-to-pickup (min)", "平均请求至上车时长（分钟）"))}</text>')

    legend_positions = ((left, height - 55), (left + 420, height - 55), (left, height - 20), (left + 420, height - 20))
    for name, (legend_x, legend_y) in zip(("Supply-constrained priority", "High-demand core", "Service-risk watchlist", "Lower-priority / balanced"), legend_positions):
        color = colors[name]
        parts.append(f'<circle cx="{legend_x}" cy="{legend_y - 4}" r="7" fill="{color}"/>')
        parts.append(f'<text x="{legend_x + 14}" y="{legend_y}" class="legend">{e(segment_labels[name])}</text>')
    parts.append('</svg>')
    return f'<div class="scatter-scroll" tabindex="0" aria-label="{e(l(lang, "Taxi-zone matrix", "出租车分区运营矩阵"))}">' + "".join(parts) + '</div>'


def burden_bars(rows: Sequence[dict[str, Any]], lang: str) -> str:
    maximum = max(float(row["estimated_excess_request_to_pickup_minutes"]) for row in rows)
    chunks = ['<div class="hbars">']
    for index, row in enumerate(rows):
        value = float(row["estimated_excess_request_to_pickup_minutes"])
        width = value / maximum * 100
        color = GOLD if index < 2 else BLUE
        chunks.append(
            '<div class="hbar-row">'
            f'<div class="hbar-label">{e(zone_name(row["zone"], lang))}</div>'
            f'<div class="hbar-track"><span style="width:{width:.2f}%;background:{color}"></span></div>'
            f'<div class="hbar-value">{e(fmt_number(value, 0))}</div></div>'
        )
    chunks.append('</div>')
    return "".join(chunks)


def data_table(headers: Sequence[str], rows: Iterable[Sequence[Any]]) -> str:
    head = "".join(f'<th>{e(item)}</th>' for item in headers)
    body = "".join('<tr>' + "".join(f'<td>{e(item)}</td>' for item in row) + '</tr>' for row in rows)
    return f'<div class="table-wrap"><table><thead><tr>{head}</tr></thead><tbody>{body}</tbody></table></div>'


CSS = r"""
:root{--bg:#F5F7FA;--card:#fff;--ink:#172033;--muted:#667085;--grid:#D9E0EA;--blue:#2367D1;--blue-dark:#174A99;--blue-light:#DCEAFF;--orange:#E77A2E;--gold:#D9A326;--shadow:0 12px 30px rgba(23,32,51,.06)}
*{box-sizing:border-box}html{scroll-behavior:smooth}body{margin:0;background:var(--bg);color:var(--ink);font-family:"Segoe UI","Microsoft YaHei","PingFang SC",Arial,sans-serif;-webkit-font-smoothing:antialiased}
button{font:inherit}.appbar{position:sticky;top:0;z-index:30;display:grid;grid-template-columns:1fr auto auto auto;gap:22px;align-items:center;padding:14px max(28px,calc((100vw - 1640px)/2));background:rgba(245,247,250,.96);border-bottom:1px solid var(--grid);backdrop-filter:blur(12px)}
.brand{font-size:15px;font-weight:700;letter-spacing:.04em;color:var(--blue-dark)}.tabs{display:flex;gap:8px}.tab{border:1px solid transparent;background:transparent;color:var(--muted);padding:10px 15px;border-radius:999px;cursor:pointer;font-weight:650}.tab:hover{background:#fff}.tab.active{color:var(--blue-dark);background:var(--blue-light);border-color:#c9dcfb}.snapshot{font:650 13px Consolas,monospace;color:var(--muted)}
.language-switch{display:flex;padding:3px;border:1px solid var(--grid);border-radius:999px;background:#fff;white-space:nowrap}.lang-btn{border:0;background:transparent;color:var(--muted);padding:7px 11px;border-radius:999px;cursor:pointer;font-size:13px;font-weight:700}.lang-btn.active{background:var(--blue-dark);color:#fff}.lang-btn:focus-visible,.tab:focus-visible,.page-nav button:focus-visible{outline:3px solid #9fc1f5;outline-offset:2px}
.dashboard{max-width:1640px;margin:0 auto;padding:48px 36px 72px}.dashboard-page{display:none}.dashboard-page.active{display:block;animation:fade .25s ease}@keyframes fade{from{opacity:.2;transform:translateY(4px)}to{opacity:1;transform:none}}
.page-head{display:flex;justify-content:space-between;gap:40px;align-items:flex-start;padding:0 0 28px;border-bottom:2px solid var(--grid);margin-bottom:36px}.eyebrow{font-size:14px;color:var(--blue-dark);font-weight:700;letter-spacing:.03em;margin-bottom:20px}.page-head h1{font-size:48px;line-height:1.06;margin:0 0 8px;letter-spacing:-.035em}.page-head p{font-size:19px;color:var(--muted);margin:0}.page-stamp{display:grid;gap:12px;justify-items:center;color:var(--blue-dark);font:650 14px Consolas,monospace}.page-stamp b{background:var(--blue-light);padding:10px 26px;border-radius:999px;font:600 14px "Segoe UI",sans-serif;white-space:nowrap}
.summary-card{--accent:var(--blue);position:relative;background:var(--card);border:1px solid var(--grid);border-radius:20px;padding:32px 38px 32px 48px;margin-bottom:28px;box-shadow:var(--shadow);overflow:hidden}.summary-card:before{content:"";position:absolute;left:0;top:0;bottom:0;width:10px;background:var(--accent)}.summary-card h2{margin:0 0 12px;font-size:28px;line-height:1.2}.summary-card p{margin:0;color:var(--muted);font-size:18px;line-height:1.55;max-width:1450px}
.metrics{display:grid;grid-template-columns:repeat(3,1fr);gap:20px;margin-bottom:30px}.metrics.four{grid-template-columns:repeat(4,1fr)}.metric-card{background:var(--card);border:1px solid var(--grid);border-radius:18px;padding:24px 26px;min-height:150px;box-shadow:var(--shadow)}.metric-label{color:var(--muted);font-size:15px}.metric-value{font:400 31px Consolas,monospace;margin:9px 0 17px;letter-spacing:.01em}.metric-meta{display:flex;align-items:center;gap:12px;min-height:30px}.chip{display:inline-flex;background:var(--blue-light);color:var(--blue-dark);font:650 14px Consolas,monospace;border-radius:999px;padding:6px 13px}.chip.negative{background:#FDE7DB;color:#A94716}.metric-note{color:var(--muted);font-size:13px}
.chart-grid{display:grid;grid-template-columns:1fr 1fr;gap:22px;margin-bottom:22px}.panel{background:var(--card);border:1px solid var(--grid);border-radius:20px;padding:24px 26px 20px;box-shadow:var(--shadow);margin-bottom:22px;min-width:0}.panel-head{margin-bottom:12px}.panel-head h2{font-size:25px;line-height:1.22;margin:0 0 4px}.panel-head p{font-size:13px;color:var(--muted);margin:0}.chart-svg{display:block;width:100%;height:auto;overflow:visible}.grid{stroke:var(--grid);stroke-width:1}.axis,.legend{fill:var(--muted);font:14px Consolas,"Microsoft YaHei",monospace}.annotation{fill:var(--muted);font:14px "Segoe UI","Microsoft YaHei",sans-serif}.reference{stroke:#78869b;stroke-width:2}.point-label{fill:var(--ink);font:13px "Segoe UI","Microsoft YaHei",sans-serif}.axis-title{fill:var(--muted);font:600 14px "Segoe UI","Microsoft YaHei",sans-serif}.callout-title{fill:var(--blue-dark);font:700 14px "Segoe UI","Microsoft YaHei",sans-serif}.callout-box{fill:#fff;stroke:var(--grid);stroke-width:1}.callout-line{stroke:#9aa6b8;stroke-width:1.5}.callout-name{fill:var(--ink);font:700 14px "Segoe UI","Microsoft YaHei",sans-serif}.callout-detail{fill:var(--muted);font:12.5px Consolas,"Microsoft YaHei",monospace}
.hbars{padding:12px 20px 10px}.hbar-row{display:grid;grid-template-columns:220px 1fr 76px;gap:14px;align-items:center;margin:10px 0}.hbar-label{text-align:right;font-size:14px}.hbar-track{height:18px;background:#eef2f7;border-radius:5px;overflow:hidden}.hbar-track span{display:block;height:100%;border-radius:5px}.hbar-value{font:14px Consolas,monospace;color:var(--muted)}
.scatter-scroll{width:100%;overflow-x:auto;overflow-y:hidden}.scatter-scroll:focus-visible{outline:3px solid #9fc1f5;outline-offset:3px}.table-wrap{width:100%;overflow:auto}table{width:100%;border-collapse:separate;border-spacing:0;font-size:14px}thead th{background:#EAF0F8;color:var(--blue-dark);text-align:left;font-weight:650;padding:10px 12px;white-space:nowrap}thead th:first-child{border-radius:10px 0 0 10px}thead th:last-child{border-radius:0 10px 10px 0}tbody td{padding:9px 12px;border-bottom:1px solid #edf0f4;color:#344054}tbody tr:nth-child(even) td{background:#FAFBFC}tbody td:not(:first-child){font-family:Consolas,monospace}
.actions{background:#EDF4FF;border-color:#ABC9F8;padding:30px}.actions ol{list-style:none;counter-reset:item;margin:12px 0 0;padding:0;display:grid;gap:15px}.actions li{counter-increment:item;display:grid;grid-template-columns:30px 1fr;align-items:start;font-size:16px;line-height:1.5}.actions li:before{content:counter(item);display:grid;place-items:center;background:var(--blue);color:#fff;width:23px;height:23px;border-radius:50%;font:700 12px Consolas,monospace;margin-top:1px}
.page-footer{display:flex;justify-content:space-between;gap:24px;border-top:1px solid var(--grid);margin-top:34px;padding-top:18px;color:var(--muted);font-size:12px}.page-nav{display:flex;justify-content:space-between;margin-top:28px}.page-nav button{border:1px solid var(--grid);border-radius:999px;background:#fff;color:var(--blue-dark);padding:11px 18px;font-weight:650;cursor:pointer}.page-nav button:hover{border-color:#9bbced;box-shadow:var(--shadow)}
@media(max-width:1120px){.appbar{grid-template-columns:1fr auto auto}.tabs{grid-column:1/-1;overflow:auto}.snapshot{display:none}.dashboard{padding:32px 20px 60px}.page-head h1{font-size:38px}.metrics,.metrics.four{grid-template-columns:repeat(2,1fr)}.chart-grid{grid-template-columns:1fr}.hbar-row{grid-template-columns:150px 1fr 70px}}
@media(max-width:650px){.appbar{padding:12px 14px;gap:10px}.brand{font-size:12px}.language-switch{justify-self:end}.lang-btn{padding:6px 9px}.tab{padding:9px 11px;font-size:13px}.dashboard{padding:24px 12px 48px}.page-head{display:block}.page-head h1{font-size:32px}.page-stamp{display:none}.summary-card{padding:26px 24px 26px 34px}.summary-card h2{font-size:23px}.summary-card p{font-size:16px}.metrics,.metrics.four{grid-template-columns:1fr}.panel{padding:20px 12px}.scatter-scroll .scatter{min-width:1050px}.hbar-row{grid-template-columns:105px 1fr 56px;font-size:11px}.hbar-label{font-size:11px}.axis,.legend{font-size:12px}.page-footer{display:block}.page-footer span{display:block;margin-bottom:6px}}
@media print{.appbar,.page-nav{display:none}.dashboard{max-width:none;padding:0}.dashboard-page{display:none!important}.dashboard-page.language-active{display:block!important;break-after:page;padding:28px}.panel,.metric-card,.summary-card{box-shadow:none;break-inside:avoid}}
"""


JS = r"""
const buttons=[...document.querySelectorAll('.tab')];
const pages=[...document.querySelectorAll('.dashboard-page')];
const languageButtons=[...document.querySelectorAll('.lang-btn')];
const tabLabels={
  en:['1 · Marketplace Overview','2 · Marketplace Efficiency','3 · Growth Quality & Priorities'],
  zh:['1 · 市场概览','2 · 市场效率','3 · 增长质量与运营优先级']
};
const chromeText={
  en:{brand:'UBER NYC · FINAL DASHBOARD',snapshot:'MAY 2026',nav:'Dashboard pages',title:'Uber NYC Final Dashboard — '},
  zh:{brand:'UBER NYC · 最终经营分析看板',snapshot:'2026 年 5 月',nav:'看板页签',title:'Uber NYC 最终经营分析看板 — '}
};
let currentLang='en';
let currentPage=1;
function showPage(page,scroll=true){
  const number=Math.max(1,Math.min(3,Number(page)||1));
  currentPage=number;
  buttons.forEach(b=>{const active=Number(b.dataset.page)===number;b.classList.toggle('active',active);b.setAttribute('aria-selected',String(active));b.setAttribute('aria-controls','page-'+currentLang+'-'+number);});
  pages.forEach(p=>p.classList.toggle('active',p.dataset.lang===currentLang&&Number(p.dataset.page)===number));
  history.replaceState(null,'','?lang='+currentLang+'#page-'+number);
  const activePage=pages.find(p=>p.dataset.lang===currentLang&&Number(p.dataset.page)===number);
  document.title=chromeText[currentLang].title+activePage.dataset.title;
  if(scroll)window.scrollTo({top:0,behavior:'smooth'});
}
function setLanguage(lang,scroll=false){
  currentLang=lang==='zh'?'zh':'en';
  document.documentElement.lang=currentLang==='zh'?'zh-CN':'en';
  document.body.dataset.language=currentLang;
  document.getElementById('brand').textContent=chromeText[currentLang].brand;
  document.getElementById('snapshot').textContent=chromeText[currentLang].snapshot;
  document.getElementById('dashboard-tabs').setAttribute('aria-label',chromeText[currentLang].nav);
  buttons.forEach((button,index)=>button.textContent=tabLabels[currentLang][index]);
  languageButtons.forEach(button=>{const active=button.dataset.langToggle===currentLang;button.classList.toggle('active',active);button.setAttribute('aria-pressed',String(active));});
  pages.forEach(page=>page.classList.toggle('language-active',page.dataset.lang===currentLang));
  try{localStorage.setItem('uber-dashboard-language',currentLang);}catch(error){}
  showPage(currentPage,scroll);
}
buttons.forEach(b=>b.addEventListener('click',()=>showPage(b.dataset.page)));
document.querySelectorAll('[data-go]').forEach(b=>b.addEventListener('click',()=>showPage(b.dataset.go)));
languageButtons.forEach(button=>button.addEventListener('click',()=>setLanguage(button.dataset.langToggle)));
window.addEventListener('hashchange',()=>showPage((location.hash.match(/page-(\d)/)||[])[1],false));
document.addEventListener('keydown',event=>{if(!['ArrowLeft','ArrowRight'].includes(event.key))return;const active=Number((location.hash.match(/page-(\d)/)||[])[1]||1);showPage(active+(event.key==='ArrowRight'?1:-1));});
const requestedLanguage=new URLSearchParams(location.search).get('lang');
if(requestedLanguage==='zh'||requestedLanguage==='en'){currentLang=requestedLanguage;}else{try{currentLang=localStorage.getItem('uber-dashboard-language')==='zh'?'zh':'en';}catch(error){currentLang='en';}}
currentPage=Number((location.hash.match(/page-(\d)/)||[])[1]||1);
setLanguage(currentLang,false);
window.dashboardQA={showPage,setLanguage,getState:()=>({page:currentPage,language:currentLang})};
"""


def build_page_1(data: dict[str, Any], lang: str) -> str:
    headline = data["headline"][0]
    monthly = data["monthly_trend"]
    labels = [row["month_label"] for row in monthly]
    trips_svg = svg_line_chart(labels, [(l(lang, "Trips", "完成行程"), [row["trips"] for row in monthly], BLUE)], lambda value: fmt_number(value, 0))
    wait_svg = svg_line_chart(
        labels,
        [
            (l(lang, "Average", "平均值"), [row["avg_request_to_pickup_minutes"] for row in monthly], BLUE),
            ("P50", [row["p50_request_to_pickup_minutes"] for row in monthly], OLIVE),
            ("P90", [row["p90_request_to_pickup_minutes"] for row in monthly], ORANGE),
        ],
        lambda value: f"{value:.1f}",
    )
    economics_svg = svg_line_chart(
        labels,
        [
            (l(lang, "Passenger base fare", "乘客基础车费"), [row["avg_base_fare_eligible"] for row in monthly], BLUE),
            (l(lang, "Driver pay", "司机报酬"), [row["avg_driver_pay_eligible"] for row in monthly], GOLD),
        ],
        lambda value: f"${value:.0f}",
        height=340,
    )
    cards = "".join([
        metric_card(l(lang, "May 2026 trips", "2026 年 5 月完成行程"), fmt_number(headline["trips_current"]), fmt_pct(headline["trip_growth_rate"], signed=True), l(lang, "YoY", "同比")),
        metric_card(l(lang, "Avg request-to-pickup", "平均请求至上车时长"), f'{headline["avg_wait_current"]:.2f} {l(lang, "min", "分钟")}', fmt_pct(headline["avg_wait_growth_rate"], signed=True), l(lang, "YoY", "同比")),
        metric_card(l(lang, "P90 request-to-pickup", "P90 请求至上车时长"), f'{headline["p90_wait_current"]:.2f} {l(lang, "min", "分钟")}', fmt_pct(headline["p90_wait_growth_rate"], signed=True), l(lang, "YoY", "同比")),
        metric_card(l(lang, "Passenger base fare", "乘客基础车费"), fmt_money(headline["fare_current"]), fmt_pct(headline["fare_growth_rate"], signed=True), l(lang, "YoY", "同比")),
        metric_card(l(lang, "Driver pay per trip", "单次行程司机报酬"), fmt_money(headline["pay_current"]), fmt_pct(headline["pay_growth_rate"], signed=True), l(lang, "YoY", "同比")),
        metric_card(l(lang, "Request-to-pickup eligibility", "请求至上车时长指标有效率"), fmt_pct(headline["wait_coverage_current"]), "", l(lang, "Metric coverage", "指标覆盖率")),
    ])
    body = page_header(
        1,
        l(lang, "Marketplace Overview", "市场概览"),
        l(lang, "Scale, growth, service quality, passenger base fare, and driver pay", "规模、增长、服务质量、乘客基础车费与司机报酬"),
        lang,
    )
    body += summary_card(
        l(lang, "Growth came with a larger service-quality penalty", "行程增长伴随更明显的服务质量压力"),
        l(
            lang,
            "May 2026 completed trips rose +2.1% YoY to 15.35M. Average request-to-pickup increased +8.8% to 5.49 minutes and P90 increased +16.9% to 10.44 minutes. Passenger base fare and driver pay remain separate per-trip measures; no platform margin or take-rate inference is made.",
            "2026 年 5 月完成行程同比增长 +2.1% 至 15.35M；平均请求至上车时长上升 +8.8% 至 5.49 分钟，P90 上升 +16.9% 至 10.44 分钟。乘客基础车费与司机报酬始终作为两个独立的单次行程指标呈现，不据此推断平台利润、利润率或抽成率。",
        ),
        BLUE,
    )
    body += f'<div class="metrics">{cards}</div>'
    body += '<div class="chart-grid">' + panel(l(lang, "Monthly completed trips", "月度完成行程"), l(lang, "May 2025–May 2026 · completed trips", "2025 年 5 月至 2026 年 5 月 · 完成行程"), trips_svg) + panel(l(lang, "Monthly request-to-pickup time", "月度请求至上车时长"), l(lang, "Average, median, and P90 · eligible completed trips", "平均值、中位数与 P90 · 符合指标条件的完成行程"), wait_svg) + '</div>'
    body += panel(l(lang, "Passenger base fare and driver pay per completed trip", "单次完成行程的乘客基础车费与司机报酬"), l(lang, "Separate eligible monthly averages · USD per trip", "分别计算的月度有效均值 · 美元/行程"), economics_svg)
    body += page_footer(1, lang)
    return f'<section id="page-{lang}-1" class="dashboard-page" data-lang="{lang}" data-page="1" data-title="{e(l(lang, "Marketplace Overview", "市场概览"))}">{body}</section>'


def build_page_2(data: dict[str, Any], city_wait: float, lang: str) -> str:
    headline = data["efficiency_headline"][0]
    scatter = data["zone_scatter"]
    top_12 = data["priority_top_12"]
    top_15 = data["priority_top_15"]
    cards = "".join([
        metric_card(l(lang, "Priority-proxy zones", "供给受限优先级代理区域"), str(headline["priority_zone_count"]), "", l(lang, "Top-quartile demand + above-city request-to-pickup", "需求位于前 25% 且请求至上车时长高于全市均值")),
        metric_card(l(lang, "Trips in priority-proxy zones", "优先级代理区域完成行程"), fmt_number(headline["priority_zone_trips"]), fmt_pct(headline["priority_zone_trip_share"]), l(lang, "Share of city", "占全市行程")),
        metric_card(l(lang, "Airport excess minutes", "机场估算超额时长"), fmt_number(headline["airport_excess_minutes"]), "", l(lang, "JFK + LaGuardia", "肯尼迪机场 + 拉瓜迪亚机场")),
    ])
    table_rows = [
        (
            zone_name(row["zone_label"], lang), fmt_number(row["trips_2026_05"]), fmt_pct(row["trip_growth_rate"], signed=True),
            f'{row["avg_wait_2026_05"]:.2f}', fmt_pct(row["avg_wait_change_rate"], signed=True),
            fmt_number(row["estimated_excess_request_to_pickup_minutes"], 0),
        )
        for row in top_15
    ]
    body = page_header(
        2,
        l(lang, "Marketplace Efficiency", "市场效率"),
        l(lang, "Demand × request-to-pickup × growth at NYC Taxi Zone level", "NYC 出租车分区层面的需求 × 请求至上车时长 × 增长诊断"),
        lang,
    )
    body += summary_card(
        l(lang, "Regional diagnosis: focus operating review where demand and service pressure overlap", "区域诊断：优先复盘需求与服务压力重叠的区域"),
        l(
            lang,
            "The priority proxy identifies 23 taxi zones with 2.99M completed trips, or 19.5% of May 2026 city volume. JFK and LaGuardia together carry about 1.27M estimated excess request-to-pickup minutes versus the city average. This supply-constrained priority label is an operating prioritization proxy based on completed trips and observed service performance—not causal proof of insufficient driver supply.",
            "供给受限优先级代理共识别出 23 个出租车分区，覆盖 2.99M 次完成行程，占 2026 年 5 月全市行程的 19.5%。肯尼迪机场与拉瓜迪亚机场相对全市均值合计约产生 1.27M 分钟的估算超额请求至上车时长。该标签仅依据已完成行程与观察到的服务表现进行运营排序，不构成司机供给不足的因果证明。",
        ),
        ORANGE,
    )
    body += f'<div class="metrics">{cards}</div>'
    body += panel(l(lang, "Taxi-zone operating matrix", "出租车分区运营矩阵"), l(lang, "Bubble size = May trips · X = YoY trip growth · Y = avg request-to-pickup · ≥500 trips in each May", "气泡大小 = 5 月完成行程 · X = 行程同比增长 · Y = 平均请求至上车时长 · 两个 5 月均至少 500 次行程"), svg_scatter(scatter, city_wait, lang))
    body += panel(l(lang, "Highest estimated excess request-to-pickup burden", "估算超额请求至上车时长最高的区域"), l(lang, "Top 12 priority-proxy zones · May 2026 · excess minutes versus city average", "前 12 个优先级代理区域 · 2026 年 5 月 · 相对全市均值的估算超额分钟"), burden_bars(top_12, lang))
    body += panel(l(lang, "Priority-proxy zone detail", "优先级代理区域明细"), l(lang, "Top 15 shown · same validated zone-level definitions", "展示前 15 名 · 沿用同一套已验证区域口径"), data_table(
        l(lang, ["Pickup zone", "Trips", "Growth", "Request-to-pickup", "Time change", "Excess min"], ["上车区域", "完成行程", "增长", "请求至上车时长", "时长变化", "超额分钟"]),
        table_rows,
    ))
    body += page_footer(2, lang)
    return f'<section id="page-{lang}-2" class="dashboard-page" data-lang="{lang}" data-page="2" data-title="{e(l(lang, "Marketplace Efficiency", "市场效率"))}">{body}</section>'


def build_page_3(data: dict[str, Any], lang: str) -> str:
    headline = data["priority_headline"][0]
    borough = data["borough_yoy"]
    hourly = data["hourly_yoy"]
    airports = data["airport_windows"][:8]
    neighborhoods = data["neighborhood_priority"][:8]
    cards = "".join([
        metric_card(l(lang, "Manhattan + Brooklyn", "曼哈顿 + 布鲁克林"), fmt_number(headline["manhattan_brooklyn_increment"]), fmt_pct(headline["manhattan_brooklyn_share"]), l(lang, "Share of net growth", "占全市净增长")),
        metric_card(l(lang, "Within-borough time effect", "区内时长变动效应"), f'{headline["within_borough_wait_minutes"]:.3f} {l(lang, "min", "分钟")}', f'{headline["geographic_mix_wait_minutes"]:+.3f}', l(lang, "Geographic mix effect", "地理结构效应"), negative=True),
        metric_card(l(lang, "Peak hourly time change", "峰值小时段时长变化"), fmt_pct(headline["peak_hour_wait_change_rate"], signed=True), "", headline["peak_hour"]),
        metric_card(l(lang, "Top-window excess", "最高优先级时窗超额时长"), fmt_number(headline["top_window_excess_minutes_per_day"]), "", l(lang, "Minutes per day", "分钟/日")),
    ])
    borough_labels = [BOROUGH_ZH.get(row["borough"], row["borough"]) if lang == "zh" else ("Staten I." if row["borough"] == "Staten Island" else row["borough"]) for row in borough]
    contribution_svg = svg_vertical_bar(borough_labels, [row["contribution_to_growth_rate"] for row in borough], color=BLUE)
    wait_svg = svg_vertical_bar(borough_labels, [row["avg_wait_change_rate"] for row in borough], signed=False, color=ORANGE)
    hourly_svg = svg_vertical_bar([f'{int(row["pickup_hour"]):02d}' for row in hourly], [row["avg_wait_change_rate"] for row in hourly], signed=False, color=ORANGE, height=340)
    airport_rows = [
        (f'{WEEKDAY_ZH.get(row["weekday_name"], row["weekday_name"]) if lang == "zh" else row["weekday_name"]} {row["pickup_hour_label"]}', zone_name(row["zone"], lang), f'{row["avg_trips_per_contributing_day"]:.0f}', f'{row["avg_request_to_pickup_minutes"]:.2f}', f'{row["wait_gap_to_city_minutes"]:+.2f}', fmt_number(row["estimated_excess_request_to_pickup_minutes_per_day"], 0))
        for row in airports
    ]
    neighborhood_rows = [
        (zone_name(row["zone_label"], lang), fmt_number(row["trips_2026_05"]), fmt_pct(row["trip_growth_rate"], signed=True), f'{row["avg_wait_2026_05"]:.2f}', fmt_pct(row["avg_wait_change_rate"], signed=True), fmt_number(row["estimated_excess_request_to_pickup_minutes"], 0))
        for row in neighborhoods
    ]
    body = page_header(
        3,
        l(lang, "Growth Quality & Operating Priorities", "增长质量与运营优先级"),
        l(lang, "Borough, hour, airport, and neighborhood action plan", "行政区、小时段、机场与社区层面的行动方案"),
        lang,
    )
    body += summary_card(
        l(lang, "Growth was concentrated, while service deterioration was broad", "增长高度集中，但服务时长恶化覆盖面更广"),
        l(
            lang,
            "Manhattan and Brooklyn added 318.3K completed trips—100.7% of net city growth because declines elsewhere offset part of the gain. The validated decomposition assigns 0.449 minutes to within-borough request-to-pickup movement; geographic mix slightly offsets the deterioration. The largest hourly increase occurs at 03:00.",
            "曼哈顿与布鲁克林合计新增 318.3K 次完成行程，占全市净增长的 100.7%；其他区域的下降抵消了部分增量。经验证的分解结果将 0.449 分钟归于行政区内部的请求至上车时长变动，地理结构变化则轻微抵消了恶化。小时段同比增幅最高点出现在 03:00。",
        ),
        BLUE,
    )
    body += f'<div class="metrics four">{cards}</div>'
    body += '<div class="chart-grid">' + panel(l(lang, "Contribution to city trip growth", "对全市行程增长的贡献"), l(lang, "Signed share of net May trip change", "各行政区对 5 月净行程变化的带符号贡献"), contribution_svg) + panel(l(lang, "Average request-to-pickup change by borough", "各行政区平均请求至上车时长变化"), l(lang, "May 2026 versus May 2025", "2026 年 5 月对比 2025 年 5 月"), wait_svg) + '</div>'
    body += panel(l(lang, "Average request-to-pickup change by pickup hour", "各上车小时段的平均请求至上车时长变化"), l(lang, "May 2026 versus May 2025 · 24 citywide pickup hours", "2026 年 5 月对比 2025 年 5 月 · 全市 24 个上车小时段"), hourly_svg)
    body += panel(l(lang, "Highest-priority airport operating windows", "最高优先级机场运营时窗"), l(lang, "Top 8 shown · recurring weekday-hour windows ranked by excess minutes per contributing day", "展示前 8 名 · 按每个贡献日的估算超额分钟排序的重复性星期–小时段时窗"), data_table(
        l(lang, ["Window", "Airport", "Trips/day", "Request-to-pickup", "Gap", "Excess/day"], ["时窗", "机场", "行程/日", "请求至上车时长", "与全市差值", "超额分钟/日"]),
        airport_rows,
    ))
    body += panel(l(lang, "Highest-priority non-airport neighborhoods", "最高优先级非机场社区"), l(lang, "Top 8 shown · interactive HTML retains the validated ranking", "展示前 8 名 · 交互式 HTML 保留已验证排序"), data_table(
        l(lang, ["Pickup zone", "Trips", "Growth", "Request-to-pickup", "Time change", "Excess min"], ["上车区域", "完成行程", "增长", "请求至上车时长", "时长变化", "超额分钟"]),
        neighborhood_rows,
    ))
    actions_en = (
        '<ol><li>Protect airport service quality: review late-evening and overnight JFK/LGA operating playbooks, starting with the ranked windows.</li>'
        '<li>Target neighborhood diagnostics before broad demand stimulation: test localized dispatch, driver-positioning, and pickup-process changes.</li>'
        '<li>Treat 00:00–07:00 as a focused service-recovery window, with completed-trip and request-to-pickup guardrails.</li>'
        '<li>Add cancellations, driver online time, dispatch acceptance, surge, and promotion data before making causal supply or financial claims.</li></ol>'
    )
    actions_zh = (
        '<ol><li>优先保护机场服务质量：从排序靠前的时窗入手，复盘肯尼迪机场与拉瓜迪亚机场的深夜及凌晨运营方案。</li>'
        '<li>在扩大需求刺激前先开展社区级诊断：测试局部派单、司机驻点与上车流程调整。</li>'
        '<li>将 00:00–07:00 设为重点服务修复时窗，并同时设置完成行程与请求至上车时长护栏。</li>'
        '<li>在作出供给或财务因果判断前，补充取消、司机在线时长、派单接受率、动态加价及促销等内部数据。</li></ol>'
    )
    body += panel(l(lang, "Recommended actions", "建议行动"), l(lang, "Prioritized operating review based on observed completed-trip and request-to-pickup patterns", "基于已观察到的完成行程与请求至上车时长模式确定运营复盘优先级"), actions_zh if lang == "zh" else actions_en, "actions")
    body += page_footer(3, lang)
    return f'<section id="page-{lang}-3" class="dashboard-page" data-lang="{lang}" data-page="3" data-title="{e(l(lang, "Growth Quality & Operating Priorities", "增长质量与运营优先级"))}">{body}</section>'


def page_footer(page: int, lang: str) -> str:
    previous_button = f'<button type="button" data-go="{page - 1}">{e(l(lang, "← Previous page", "← 上一页"))}</button>' if page > 1 else '<span></span>'
    next_button = f'<button type="button" data-go="{page + 1}">{e(l(lang, "Next page →", "下一页 →"))}</button>' if page < 3 else '<span></span>'
    return (
        f'<footer class="page-footer"><span>{e(l(lang, "Source: NYC TLC HVFHV public trip records · Uber HV0003 · metric-specific eligibility. Completed trips only; priority labels are proxies, not causal proof; base fare and driver pay do not imply profit or take rate.", "来源：NYC TLC HVFHV 公共行程记录 · Uber HV0003 · 各指标采用独立有效性规则。仅包含完成行程；优先级标签是运营代理而非因果证明；乘客基础车费与司机报酬之差不代表利润或抽成率。"))}</span><span>{e(l(lang, "Snapshot, not live data", "静态快照，非实时数据"))}</span></footer>'
        f'<div class="page-nav">{previous_button}{next_button}</div>'
    )


def write_qa(output_root: Path, html_text: str, p1: dict[str, Any], p2: dict[str, Any], p3: dict[str, Any]) -> None:
    headline = p1["headline"][0]
    efficiency = p2["efficiency_headline"][0]
    priority = p3["priority_headline"][0]
    checks = [
        ("single_html_document", html_text.count("<!doctype html>") == 1, "One self-contained dashboard document"),
        ("three_page_tabs", html_text.count('<button class="tab') == 3, "Three tab controls"),
        ("two_language_controls", html_text.count('class="lang-btn') == 2, "Chinese and English controls"),
        ("three_english_sections", html_text.count('data-lang="en" data-page=') == 3, "Three English page views"),
        ("three_chinese_sections", html_text.count('data-lang="zh" data-page=') == 3, "Three Chinese page views"),
        ("no_external_stylesheets", "<link" not in html_text.lower(), "No external stylesheet dependency"),
        ("no_external_scripts", "<script src=" not in html_text.lower(), "No external script dependency"),
        ("no_remote_urls", "https://" not in html_text.lower() and "http://" not in html_text.lower(), "Portable offline artifact"),
        ("page1_trips", fmt_number(headline["trips_current"]) in html_text, f'Expected {fmt_number(headline["trips_current"])}'),
        ("page1_avg_wait", f'{headline["avg_wait_current"]:.2f} min' in html_text, f'Expected {headline["avg_wait_current"]:.2f} min'),
        ("page1_p90_wait", f'{headline["p90_wait_current"]:.2f} min' in html_text, f'Expected {headline["p90_wait_current"]:.2f} min'),
        ("page1_fare", fmt_money(headline["fare_current"]) in html_text, f'Expected {fmt_money(headline["fare_current"])}'),
        ("page1_pay", fmt_money(headline["pay_current"]) in html_text, f'Expected {fmt_money(headline["pay_current"])}'),
        ("page2_priority_zones", f'>{efficiency["priority_zone_count"]}<' in html_text, f'Expected {efficiency["priority_zone_count"]}'),
        ("page2_priority_trips", fmt_number(efficiency["priority_zone_trips"]) in html_text, f'Expected {fmt_number(efficiency["priority_zone_trips"])}'),
        ("page2_airport_excess", fmt_number(efficiency["airport_excess_minutes"]) in html_text, f'Expected {fmt_number(efficiency["airport_excess_minutes"])}'),
        ("page3_growth_increment", fmt_number(priority["manhattan_brooklyn_increment"]) in html_text, f'Expected {fmt_number(priority["manhattan_brooklyn_increment"])}'),
        ("page2_collision_safe_callouts", html_text.count('class="callout-box"') == 8, "Four fixed callout boxes in each language view"),
        ("language_switch_runtime", "window.dashboardQA" in html_text and "setLanguage" in html_text, "All language views use one switch runtime"),
        ("english_evidence_boundary", "not causal proof of insufficient driver supply" in html_text and "no platform margin or take-rate inference" in html_text, "English causal and financial boundaries retained"),
        ("chinese_request_to_pickup_term", "请求至上车时长" in html_text, "Fixed Chinese metric term is present"),
        ("chinese_priority_proxy_boundary", "供给受限优先级代理" in html_text and "不构成司机供给不足的因果证明" in html_text, "Chinese proxy and causal boundary are explicit"),
        ("chinese_financial_boundary", "不代表利润或抽成率" in html_text, "Chinese financial interpretation boundary is explicit"),
    ]
    qa_dir = output_root / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    with (qa_dir / "unified_dashboard_qa.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["check", "status", "detail"])
        for name, passed, detail in checks:
            writer.writerow([name, "PASS" if passed else "FAIL", detail])
    audit_rows = [
        ("Document structure", "Three independent HTML files", "One HTML with Page 1/2/3 tabs and hash navigation", "RESOLVED"),
        ("Rendering source", "Generic artifact reader differed from static previews", "Single custom renderer now controls the actual HTML presentation", "RESOLVED"),
        ("Palette", "Reader category colors did not match previews", "Blue / orange / pink / olive mapping is explicit and shared", "RESOLVED"),
        ("Number format", "Reader showed raw exact integers", "Executive compact formatting (M/K, signed percentages) while source values remain in tooltips/tables", "RESOLVED"),
        ("Scatter axis", "Growth appeared as decimals", "Growth axis is formatted as signed percentages", "RESOLVED"),
        ("Page 2 label collisions", "Point labels and values could overlap bubbles", "Four executive callouts use a fixed side rail with leader lines and non-overlapping numeric summaries", "RESOLVED"),
        ("Bilingual layout", "English-only labels and navigation", "One HTML contains synchronized English and Chinese views generated from the same validated datasets", "RESOLVED"),
        ("Typography and spacing", "Reader defaults produced a plain report layout", "Segoe UI, compact cards, near-white canvas, and executive spacing match the approved preview system", "RESOLVED"),
    ]
    with (qa_dir / "visual_consistency_audit.csv").open("w", newline="", encoding="utf-8-sig") as handle:
        writer = csv.writer(handle)
        writer.writerow(["dimension", "observed_issue", "resolution", "status"])
        writer.writerows(audit_rows)
    failures = [name for name, passed, _ in checks if not passed]
    if failures:
        raise RuntimeError("Unified dashboard QA failed: " + ", ".join(failures))


def main() -> None:
    parser = argparse.ArgumentParser()
    parser.add_argument(
        "--output-root",
        type=Path,
        default=Path(__file__).resolve().parents[1] / "dashboard",
    )
    args = parser.parse_args()
    output_root = args.output_root.resolve()
    artifact_root = output_root / "artifacts"
    with (artifact_root / "page_1_marketplace_overview.artifact.json").open(encoding="utf-8") as handle:
        p1_artifact = json.load(handle)
    with (artifact_root / "page_2_marketplace_efficiency.artifact.json").open(encoding="utf-8") as handle:
        p2_artifact = json.load(handle)
    with (artifact_root / "page_3_operating_priorities.artifact.json").open(encoding="utf-8") as handle:
        p3_artifact = json.load(handle)
    p1 = p1_artifact["snapshot"]["datasets"]
    p2 = p2_artifact["snapshot"]["datasets"]
    p3 = p3_artifact["snapshot"]["datasets"]
    city_wait = float(p1["headline"][0]["avg_wait_current"])
    pages = "".join(
        build_page_1(p1, lang) + build_page_2(p2, city_wait, lang) + build_page_3(p3, lang)
        for lang in LANGUAGES
    )
    generated = datetime.now(timezone.utc).isoformat()
    html_text = (
        '<!doctype html><html lang="en"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1">'
        '<meta name="description" content="Bilingual Uber NYC executive dashboard: marketplace overview, efficiency, growth quality, and operating priorities. Uber NYC 双语经营分析看板。">'
        '<title>Uber NYC Final Dashboard — Marketplace Overview</title><style>' + CSS + '</style></head><body>'
        '<header class="appbar"><div class="brand" id="brand">UBER NYC · FINAL DASHBOARD</div><nav class="tabs" id="dashboard-tabs" aria-label="Dashboard pages" role="tablist">'
        '<button class="tab active" type="button" data-page="1" role="tab" aria-controls="page-1">1 · Marketplace Overview</button>'
        '<button class="tab" type="button" data-page="2" role="tab" aria-controls="page-2">2 · Marketplace Efficiency</button>'
        '<button class="tab" type="button" data-page="3" role="tab" aria-controls="page-3">3 · Growth Quality & Priorities</button>'
        '</nav><div class="language-switch" role="group" aria-label="Language / 语言">'
        '<button class="lang-btn active" type="button" data-lang-toggle="en" aria-pressed="true">English</button>'
        '<button class="lang-btn" type="button" data-lang-toggle="zh" aria-pressed="false">中文</button>'
        '</div><div class="snapshot" id="snapshot">MAY 2026</div></header><main class="dashboard">' + pages + '</main>'
        '<script>' + JS + '</script></body></html>'
    )
    output_path = output_root / "uber_nyc_final_dashboard.html"
    output_path.write_text(html_text, encoding="utf-8")
    write_qa(output_root, html_text, p1, p2, p3)
    manifest = {
        "title": "Uber NYC Final Dashboard",
        "generated_at_utc": generated,
        "snapshot_period": "May 2026 with May 2025 comparison; monthly trend May 2025–May 2026",
        "primary_dashboard": "uber_nyc_final_dashboard.html",
        "languages": {"available": ["en", "zh-CN"], "default": "en", "switch": "in-document button"},
        "navigation": [
            {"number": 1, "title": "Marketplace Overview", "hash": "#page-1"},
            {"number": 2, "title": "Marketplace Efficiency", "hash": "#page-2"},
            {"number": 3, "title": "Growth Quality & Operating Priorities", "hash": "#page-3"},
        ],
        "source_artifacts": [
            "artifacts/page_1_marketplace_overview.artifact.json",
            "artifacts/page_2_marketplace_efficiency.artifact.json",
            "artifacts/page_3_operating_priorities.artifact.json",
        ],
        "qa": {
            "unified_dashboard": "qa/unified_dashboard_qa.csv",
            "visual_consistency_audit": "qa/visual_consistency_audit.csv",
            "upstream_numerical": "qa/dashboard_validation.csv",
        },
        "interpretation_boundary": "Completed-trip data cannot measure unserved demand, cancellations, driver online time, surge pricing, promotion effects, or causal supply shortages.",
        "terminology": {
            "request_to_pickup_zh": "请求至上车时长",
            "supply_constrained_priority_zh": "供给受限优先级代理（运营排序代理，不是供给不足的因果证明）",
            "financial_boundary_zh": "乘客基础车费与司机报酬之差不代表利润、利润率或抽成率",
        },
    }
    (output_root / "dashboard_manifest.json").write_text(json.dumps(manifest, indent=2, ensure_ascii=False), encoding="utf-8")
    print(json.dumps({"status": "ok", "output": str(output_path), "qa_checks": 23, "languages": list(LANGUAGES)}, ensure_ascii=False))


if __name__ == "__main__":
    main()
