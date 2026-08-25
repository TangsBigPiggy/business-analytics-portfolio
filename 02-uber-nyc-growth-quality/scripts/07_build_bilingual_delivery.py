"""Build English and Chinese executive-report artifacts and portable HTML files.

The Chinese report is a localized view of the same validated artifact: block,
chart, table, card, source, and dataset ids remain unchanged. Only reader-facing
language and categorical display labels are localized; numeric evidence is
asserted identical before rendering.
"""

from __future__ import annotations

import argparse
import copy
from datetime import datetime
import json
import os
import shutil
import subprocess
from pathlib import Path
from typing import Any
from zoneinfo import ZoneInfo


ROOT = Path(__file__).resolve().parents[1]


MARKDOWN_ZH = {
    "title": "# Uber NYC 增长质量复盘",
    "executive_summary": """## 执行摘要

- **2026 年 5 月行程实现温和增长，但增长质量并不理想。** 完成行程同比增长 **+2.1%** 至 **15.35M**，平均请求至上车时长上升 **+8.8%** 至 **5.49 分钟**，P90 上升 **+16.9%** 至 **10.44 分钟**。
- **服务时长恶化主要来自广泛的区内变动，而非地理结构造成的假象。** 行政区分解将约 **0.449 分钟**归于各区内部的时长上升；地理结构变化则抵消约 **0.008 分钟**。
- **增长集中在曼哈顿与布鲁克林，但服务压力更集中于其他区域。** 两区合计贡献 **318,282 次新增行程**，相当于全市净增长的 **100.7%**。布鲁克林的请求至上车时长上升 **10.5%**、皇后区上升 **12.9%**、布朗克斯上升 **15.0%**。
- **应采用定向的供给与机场运营方案，而非广泛刺激需求。** 尽管机场行程量较低，其估算超额请求至上车时长负担最高；部分仍在增长的布鲁克林与哈莱姆区域也同时出现较大需求和两位数的时长恶化。
""",
    "growth_section": """## 行程增长伴随更明显的服务质量压力

完成行程同比增长 **+2.1%**，但服务时长分布恶化得更快：平均请求至上车时长上升 **+8.8%**，P90 上升 **+16.9%**。平均值与 P90 的差异表明，长等待尾部的恶化幅度高于典型行程。

单次行程乘客基础车费与司机报酬走势几乎一致，分别上升 **+1.5%** 与 **+1.6%**；同期平均里程下降 **-3.0%**。更短的行程结构使每英里基础车费机械性上升 **+4.6%**，每英里司机报酬上升 **+4.7%**。二者分别反映乘客与司机侧的经济指标，不能据此计算平台利润、利润率或抽成率。
""",
    "wait_section": """## 服务时长恶化覆盖面广，地理结构反而略有缓冲

全市平均请求至上车时长增加 **0.442 分钟**。分解结果将约 **0.449 分钟**归于各行政区内部的时长上升；行政区行程结构变化贡献 **-0.008 分钟**，对恶化形成轻微抵消，而非造成恶化。

曼哈顿行程增长 **3.8%**，请求至上车时长仅上升 **2.8%**；布鲁克林增长 **2.9%**，时长上升 **10.5%**；皇后区在行程增长 **1.0%** 的情况下时长上升 **12.9%**；布朗克斯行程下降 **1.5%**，时长仍上升 **15.0%**。这一模式不支持用单一的全市市场机制解释全部变化。
""",
    "zone_section": """## 机场与增长型社区需要不同的运营方案

拉瓜迪亚机场与肯尼迪机场在估算超额请求至上车分钟数上排名前两位，但两者完成行程均低于上年 5 月。这一组合更像是机场上车、候车区与调度流程的结构性问题，而不是需求增长带来的压力；但公共数据不足以证明具体因果机制。

社区区域呈现出不同的模式。哈莱姆中北部、皇冠高地北部、卡纳西、斯图维森特高地、布什维克南部、东纽约与布朗斯维尔同时具备较大完成行程量和上升的请求至上车时长。相比全市性干预，这些区域更适合定向的供给再配置或受控激励试验。
""",
    "window_section": """## 深夜机场时窗与全市凌晨时段应列为首批运营优先级

最集中的重复性高优先级时窗主要位于拉瓜迪亚机场与肯尼迪机场的深夜及凌晨。与此同时，全市小时段对比显示，03:00–06:00 左右的请求至上车时长恶化最明显，完成行程增速也有所加快。运营团队应同时监控平均值与 P90，因为整体上长时长尾部恶化最快。
""",
    "recommendations": """## 建议行动

1. **将机场运营与社区市场管理分开。** 独立复盘机场候车区、队列释放、航班到达匹配及深夜司机可用性，不与城市社区的供给配置混为一谈。
2. **在负担最高的社区区域试点定向干预。** 从优先级表中的重复性区域–小时段时窗入手，在条件允许时采用分阶段或随机化设计。
3. **增加需求前先设置服务护栏。** 不把完成行程增长单独视为成功；平均与 P90 请求至上车时长、估算超额分钟及司机报酬强度均应保持在约定范围内。
4. **在作出因果判断前补充内部市场数据。** 接单、取消、未服务请求、司机在线时长、动态加价、预约与激励暴露等数据，是区分供给、调度、产品与报送因素所必需的。
""",
    "further_questions": """## 后续问题

- 请求至上车时长上升中，有多少来自预约或计划行程，而非即时派单？
- 受影响行政区和小时段的司机在线时长、接单、取消或调位行为是否发生变化？
- 机场模式能否由航班时刻、队列规则、候车区利用率或上车区域报送方式解释？
- 在控制天气、节假日和本地活动后，哪些高优先级社区时窗仍然承压？
""",
    "caveats": """## 局限与假设

- TLC 记录仅代表完成行程，不包含未服务需求、取消、司机在线时长、促销、动态加价倍数或乘客/司机标识。
- “供给受限优先级代理”和“估算超额请求至上车分钟数”只用于运营排序，不构成司机供给不足的因果证明。
- 时间戳按纽约当地时间理解；请求至上车时长限定在 0–60 分钟，`on_scene_datetime` 不作为核心 KPI。
- 乘客基础车费与司机报酬分别分析；二者之差不定义为平台收入、利润、利润率或抽成率。
- 月度质量检查发现焦点同比月份之外存在个别行程时长与车费异常。两个 5 月的指标有效率足以支持本次对比，但 TLC 公共数据由平台方提交，官方不保证其完整无误。
""",
}


ZH_TEXT = {
    "Uber NYC Growth Quality Review": "Uber NYC 增长质量复盘",
    "A decision-ready review of Uber NYC growth quality, service efficiency, and operating priorities.": "面向管理层决策的 Uber NYC 增长质量、服务效率与运营优先级复盘。",
    "May 2026 trips": "2026 年 5 月完成行程",
    "May 2025": "2025 年 5 月",
    "YoY": "同比",
    "Average request-to-pickup": "平均请求至上车时长",
    "P90 request-to-pickup": "P90 请求至上车时长",
    "Passenger base fare": "乘客基础车费",
    "Driver pay per trip": "单次行程司机报酬",
    "Completed Uber trips in May 2026 with the May 2025 comparison.": "2026 年 5 月 Uber 完成行程及其与 2025 年 5 月的对比。",
    "Average request-to-pickup among metric-eligible trips.": "符合指标条件的完成行程的平均请求至上车时长。",
    "The 90th percentile of request-to-pickup among metric-eligible trips.": "符合指标条件的完成行程中，请求至上车时长的第 90 百分位数。",
    "Average eligible passenger base fare per completed trip; not platform revenue.": "每次完成行程的有效乘客基础车费均值；不代表平台收入。",
    "Average eligible reported driver pay per completed trip.": "每次完成行程的有效报送司机报酬均值。",
    "Monthly completed trips": "月度完成行程",
    "May 2025–May 2026; Uber HV0003 completed trips": "2025 年 5 月至 2026 年 5 月；Uber HV0003 完成行程",
    "Monthly request-to-pickup distribution": "月度请求至上车时长分布",
    "Average, median, and P90 among trips with request-to-pickup between 0 and 60 minutes": "请求至上车时长在 0–60 分钟之间的完成行程：平均值、中位数与 P90",
    "Completed-trip growth by pickup borough": "各上车行政区的完成行程增长",
    "May 2026 versus May 2025; five NYC boroughs": "2026 年 5 月对比 2025 年 5 月；NYC 五个行政区",
    "Highest excess request-to-pickup burden by pickup zone": "各上车区域的估算超额请求至上车时长负担",
    "May 2026; top-quartile zone demand and wait above the city average": "2026 年 5 月；需求位于前 25% 且请求至上车时长高于全市均值",
    "Request-to-pickup change by pickup hour": "各上车小时段的请求至上车时长变化",
    "May 2026 versus May 2025; citywide completed trips": "2026 年 5 月对比 2025 年 5 月；全市完成行程",
    "Highest-priority recurring pickup windows": "最高优先级重复性上车时窗",
    "Top 15 May 2026 weekday-hour-zone combinations by estimated excess request-to-pickup minutes per contributing day": "2026 年 5 月按每个贡献日估算超额请求至上车分钟排序的前 15 个星期–小时–区域组合",
    "Monthly quality exceptions outside the focal comparison": "焦点对比月份之外的月度质量异常",
    "Months with duration, fare, or trip-time mismatch signals requiring caution": "出现行程时长、车费覆盖或行程时间不匹配信号、需谨慎解读的月份",
    "Month": "月份",
    "Trips": "完成行程",
    "Trips per active day": "每活跃日完成行程",
    "Avg request-to-pickup": "平均请求至上车时长",
    "Minutes": "分钟",
    "Statistic": "统计量",
    "Pickup borough": "上车行政区",
    "Trip growth": "行程增长",
    "Trip delta": "行程增量",
    "Contribution to city growth": "对全市增长的贡献",
    "Pickup zone": "上车区域",
    "May 2026 trips": "2026 年 5 月完成行程",
    "Estimated excess minutes": "估算超额分钟",
    "Pickup hour": "上车小时",
    "Wait change": "时长变化",
    "May 2025 avg wait": "2025 年 5 月平均时长",
    "May 2026 avg wait": "2026 年 5 月平均时长",
    "Eligibility coverage (%)": "指标有效率（%）",
    "Weekday": "星期",
    "Hour": "小时",
    "Trips/day": "行程/日",
    "Avg request-to-pickup": "平均请求至上车时长",
    "Gap vs city": "与全市差值",
    "Excess minutes/day": "超额分钟/日",
    "Review note": "质量复核说明",
    "Wait coverage": "请求至上车指标覆盖率",
    "Duration coverage": "行程时长覆盖率",
    "Fare coverage": "车费覆盖率",
    "Trip-time mismatches": "行程时间不匹配",
    "Deep-analysis summary": "深度分析摘要",
    "Monthly Uber marketplace metrics": "Uber 月度市场指标",
    "Borough growth and wait decomposition": "行政区增长与时长分解",
    "Taxi-zone marketplace priority analysis": "出租车分区市场优先级分析",
    "Pickup zone and recurring hour priorities": "上车区域与重复性小时段优先级",
    "Monthly data-quality review": "月度数据质量复核",
    "Average": "平均值",
    "Median": "中位数",
    "Bronx": "布朗克斯",
    "Brooklyn": "布鲁克林",
    "Manhattan": "曼哈顿",
    "Queens": "皇后区",
    "Staten Island": "史泰登岛",
    "Monday": "周一",
    "Tuesday": "周二",
    "Wednesday": "周三",
    "Thursday": "周四",
    "Friday": "周五",
    "Saturday": "周六",
    "Sunday": "周日",
    "Queens — JFK Airport": "皇后区 · 肯尼迪机场",
    "Queens — LaGuardia Airport": "皇后区 · 拉瓜迪亚机场",
    "Manhattan — Central Harlem North": "曼哈顿 · 哈莱姆中北部",
    "Brooklyn — Brownsville": "布鲁克林 · 布朗斯维尔",
    "Brooklyn — Crown Heights North": "布鲁克林 · 皇冠高地北部",
    "Brooklyn — Canarsie": "布鲁克林 · 卡纳西",
    "Brooklyn — Stuyvesant Heights": "布鲁克林 · 斯图维森特高地",
    "Manhattan — East Harlem North": "曼哈顿 · 东哈莱姆北部",
    "Brooklyn — Bushwick South": "布鲁克林 · 布什维克南部",
    "Bronx — Mott Haven/Port Morris": "布朗克斯 · 莫特黑文/莫里斯港",
    "Manhattan — Central Harlem": "曼哈顿 · 哈莱姆中部",
    "Brooklyn — East New York": "布鲁克林 · 东纽约",
    "Brooklyn — Bedford": "布鲁克林 · 贝德福德",
    "Brooklyn — Bushwick North": "布鲁克林 · 布什维克北部",
    "Brooklyn — Prospect-Lefferts Gardens": "布鲁克林 · 普罗斯佩克特-莱弗茨花园",
    "Duration coverage anomaly": "行程时长覆盖异常",
    "Base-fare coverage anomaly": "基础车费覆盖异常",
    "Trip-time mismatch anomaly": "行程时间不匹配异常",
    "HV0003 Uber trips": "HV0003 Uber 行程",
    "2025-05 through 2026-05": "2025 年 5 月至 2026 年 5 月",
    "May 2026 compared with May 2025": "2026 年 5 月对比 2025 年 5 月",
    "May 2025 and May 2026": "2025 年 5 月与 2026 年 5 月",
    "valid pickup taxi zones": "有效上车出租车分区",
    "May 2026": "2026 年 5 月",
    "at least 500 trips in the recurring window": "重复性时窗至少 500 次行程",
    "wait above city average": "请求至上车时长高于全市均值",
}


SOURCE_TEXT_ZH = {
    "Loads the validated headline comparison and ranked findings produced by the deep-analysis script.": "载入深度分析脚本生成并已验证的核心对比与排序结果。",
    "Trip growth assessed alongside request-to-pickup, passenger fare, driver pay, distance, and duration.": "结合请求至上车时长、乘客车费、司机报酬、里程与行程时长评估行程增长质量。",
    "Top-quartile zone demand with average request-to-pickup above the city benchmark; a prioritization proxy, not causal proof.": "区域需求位于前 25% 且平均请求至上车时长高于全市基准；仅为优先级代理，不构成因果证明。",
    "Loads monthly Uber trip, service, passenger-fare, and driver-pay metrics.": "载入 Uber 月度行程、服务、乘客车费与司机报酬指标。",
    "pickup_datetime minus request_datetime for eligible trips between 0 and 60 minutes.": "对 0–60 分钟的有效行程，以 pickup_datetime 减去 request_datetime。",
    "Passenger base fare, not platform revenue.": "乘客基础车费，不代表平台收入。",
    "Reported driver compensation, analyzed separately from passenger fare.": "报送的司机报酬，与乘客车费分开分析。",
    "Compares May 2026 with May 2025 by pickup borough and decomposes the citywide wait change into within-borough and mix components.": "按上车行政区比较 2026 年 5 月与 2025 年 5 月，并将全市请求至上车时长变化分解为区内变动与地理结构两部分。",
    "Borough trip delta divided by the total city trip delta.": "行政区行程增量除以全市行程净增量。",
    "Prior-period borough weight multiplied by the borough wait change.": "上期行政区权重乘以该区请求至上车时长变化。",
    "Change in borough trip weight multiplied by current-period borough wait.": "行政区行程权重变化乘以本期该区请求至上车时长。",
    "Ranks pickup zones by demand, wait performance, growth, and excess request-to-pickup minutes.": "按需求、请求至上车时长表现、增长与估算超额分钟对上车区域排序。",
    "Eligible trips multiplied by positive zone wait gap versus the city average.": "有效行程数乘以区域相对全市均值的正向请求至上车时长差。",
    "Top-quartile demand and above-city average request-to-pickup.": "需求位于前 25% 且平均请求至上车时长高于全市均值。",
    "Ranks May 2026 weekday, pickup-hour, and taxi-zone windows with above-city request-to-pickup and material completed-trip demand.": "对 2026 年 5 月请求至上车时长高于全市均值且完成行程量较大的星期–小时–出租车分区时窗进行排序。",
    "Eligible trips per contributing weekday multiplied by positive wait gap versus city average.": "每个贡献星期的有效行程数乘以相对全市均值的正向时长差。",
    "Reviews monthly eligibility coverage and time/fare anomalies before using results for recommendations.": "在将结果用于建议前，复核月度指标覆盖率及时间/车费异常。",
}


def translate_tree(value: Any) -> Any:
    if isinstance(value, dict):
        return {key: translate_tree(item) for key, item in value.items()}
    if isinstance(value, list):
        return [translate_tree(item) for item in value]
    if isinstance(value, str):
        return ZH_TEXT.get(value, SOURCE_TEXT_ZH.get(value, value))
    return value


def numeric_signature(value: Any, path: str = "$") -> list[tuple[str, float]]:
    rows: list[tuple[str, float]] = []
    if isinstance(value, dict):
        for key in sorted(value):
            rows.extend(numeric_signature(value[key], f"{path}.{key}"))
    elif isinstance(value, list):
        for index, item in enumerate(value):
            rows.extend(numeric_signature(item, f"{path}[{index}]"))
    elif isinstance(value, (int, float)) and not isinstance(value, bool):
        rows.append((path, float(value)))
    return rows


def find_node_executable() -> Path | None:
    located = shutil.which("node")
    return Path(located) if located else None


def find_report_builder() -> Path | None:
    configured = os.environ.get("DATA_ANALYTICS_REPORT_BUILDER")
    if configured:
        path = Path(configured).expanduser()
        return path if path.is_file() else None
    return None


def render_report(node: Path, builder: Path, artifact: Path, output: Path) -> dict[str, Any]:
    completed = subprocess.run(
        [str(node), str(builder), "--input", str(artifact), "--output", str(output)],
        check=True,
        capture_output=True,
        text=True,
    )
    receipt = json.loads(completed.stdout.strip().splitlines()[-1])
    if not receipt.get("ok"):
        raise RuntimeError(f"Portable report rendering failed: {receipt}")
    receipt["html"] = output.name
    return receipt


def postprocess_portable_html(output: Path, artifact: dict[str, Any], lang: str) -> None:
    """Apply bounded locale/overflow fixes without changing report evidence."""
    markup = output.read_text(encoding="utf-8")
    generated = datetime.fromisoformat(str(artifact["manifest"]["generatedAt"])).astimezone(ZoneInfo("Asia/Shanghai"))
    if lang == "zh":
        locale = "zh-CN"
        date_text = f"{generated.year}年{generated.month}月{generated.day}日 · {generated:%H:%M}"
        source_heading = "数据来源"
    else:
        locale = "en"
        date_text = f"{generated:%b} {generated.day}, {generated.year} · {generated:%H:%M}"
        source_heading = "Sources"
    markup = markup.replace('<html lang="en">', f'<html lang="{locale}">', 1)
    style = (
        '<style id="portfolio-bilingual-layout-fix">'
        'html,body{max-width:100%;overflow-x:hidden}'
        '</style>'
    )
    script = f"""<script id="portfolio-bilingual-locale-fix">
(() => {{
  const dateText={json.dumps(date_text, ensure_ascii=False)};
  const sourceHeading={json.dumps(source_heading, ensure_ascii=False)};
  const apply=()=>{{
    document.documentElement.lang={json.dumps(locale)};
    document.querySelectorAll('.portable-page-meta time').forEach(el=>{{
      if(el.textContent!==dateText)el.textContent=dateText;
      el.setAttribute('aria-label',(sourceHeading==='Sources'?'Generated ':'生成时间 ')+dateText);
    }});
    document.querySelectorAll('.top-bar-refresh-text').forEach(el=>{{
      if(el.textContent!==dateText)el.textContent=dateText;
      el.parentElement?.setAttribute('aria-label',(sourceHeading==='Sources'?'Last updated ':'最后更新 ')+dateText);
    }});
    if(sourceHeading!=='Sources'){{
      document.querySelectorAll('h1,h2,h3').forEach(el=>{{if(el.textContent.trim()==='Sources'&&el.textContent!==sourceHeading)el.textContent=sourceHeading;}});
      document.querySelectorAll('span,div,li').forEach(el=>{{
        if(el.children.length===0&&el.textContent.trim()==='positive')el.textContent='正向';
        if(el.children.length===0&&el.textContent.trim()==='negative')el.textContent='负向';
      }});
    }}
  }};
  apply();
  const observer=new MutationObserver(apply);observer.observe(document.documentElement,{{subtree:true,childList:true}});
  setTimeout(()=>observer.disconnect(),5000);
}})();
</script>"""
    markup = markup.replace("</head>", style + "</head>", 1)
    markup = markup.replace("</body>", script + "</body>", 1)
    output.write_text(markup, encoding="utf-8")


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser()
    parser.add_argument("--english-artifact", type=Path, default=ROOT / "reports" / "executive_report_artifact_en.json")
    parser.add_argument("--builder", type=Path, default=None)
    parser.add_argument("--node", type=Path, default=None)
    parser.add_argument("--skip-render", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    english_path = args.english_artifact.resolve()
    reports_dir = english_path.parent
    english = json.loads(english_path.read_text(encoding="utf-8"))
    chinese = translate_tree(copy.deepcopy(english))
    for block in chinese["manifest"]["blocks"]:
        if block["id"] in MARKDOWN_ZH:
            block["body"] = MARKDOWN_ZH[block["id"]]

    if numeric_signature(english) != numeric_signature(chinese):
        raise RuntimeError("Bilingual artifact numeric signatures differ")
    if [block["id"] for block in english["manifest"]["blocks"]] != [block["id"] for block in chinese["manifest"]["blocks"]]:
        raise RuntimeError("Bilingual report block order differs")

    chinese_path = reports_dir / "executive_report_artifact_zh.json"
    chinese_path.write_text(json.dumps(chinese, ensure_ascii=False, indent=2), encoding="utf-8")

    receipts: dict[str, Any] = {
        "numeric_signature": "identical",
        "block_order": "identical",
        "english_artifact": english_path.name,
        "chinese_artifact": chinese_path.name,
    }
    if not args.skip_render:
        node = args.node.resolve() if args.node else find_node_executable()
        builder = args.builder.resolve() if args.builder else find_report_builder()
        if node and builder:
            receipts["english"] = render_report(node, builder, english_path, reports_dir / "uber_nyc_growth_quality_report_en.html")
            receipts["chinese"] = render_report(node, builder, chinese_path, reports_dir / "uber_nyc_growth_quality_report_zh.html")
            postprocess_portable_html(reports_dir / "uber_nyc_growth_quality_report_en.html", english, "en")
            postprocess_portable_html(reports_dir / "uber_nyc_growth_quality_report_zh.html", chinese, "zh")
            receipts["postprocess"] = "localized document language/date and bounded global horizontal overflow"
        else:
            receipts["rendering"] = "skipped: Node.js or the portable report builder was not found"
    (reports_dir / "build_receipts.json").write_text(json.dumps(receipts, ensure_ascii=False, indent=2), encoding="utf-8")
    print(json.dumps({"status": "ok", "reports": str(reports_dir), "receipts": receipts}, ensure_ascii=False))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
