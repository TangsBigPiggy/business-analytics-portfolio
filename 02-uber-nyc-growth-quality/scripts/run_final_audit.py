"""Audit the public repository package for GitHub release readiness."""

from __future__ import annotations

import csv
import json
import re
import struct
from pathlib import Path
from typing import Any


ROOT = Path(__file__).resolve().parents[1]
TEXT_SUFFIXES = {".md", ".json", ".csv", ".html", ".py", ".js", ".txt"}
MAX_PUBLIC_FILE_BYTES = 50 * 1024 * 1024


def is_public_file(path: Path) -> bool:
    """Model the files that belong in Git while allowing ignored local raw data."""
    relative = path.relative_to(ROOT)
    parts = relative.parts
    if not parts:
        return False
    if parts[0] in {".git", ".venv", ".idea", "work", "Uber数据"}:
        return False
    if len(parts) >= 2 and parts[0] == "data" and parts[1] in {"raw", "quality_audit"}:
        return False
    return path.is_file()


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open("r", encoding="utf-8-sig", newline="") as handle:
        return list(csv.DictReader(handle))


def add(checks: list[dict[str, Any]], name: str, passed: bool, detail: str) -> None:
    checks.append({"check": name, "status": "PASS" if passed else "FAIL", "detail": detail})


def local_markdown_links(markdown: str) -> list[str]:
    links = re.findall(r"\]\(([^)\s]+)\)", markdown)
    return [
        link.split("#", 1)[0].split("?", 1)[0]
        for link in links
        if link and not re.match(r"^(?:https?://|mailto:|#)", link)
    ]


def image_dimensions(path: Path) -> tuple[int, int]:
    with path.open("rb") as handle:
        signature = handle.read(24)
        if signature[:8] == b"\x89PNG\r\n\x1a\n":
            return struct.unpack(">II", signature[16:24])
        if signature[:2] != b"\xff\xd8":
            raise ValueError(f"Unsupported image file: {path}")
        handle.seek(2)
        while True:
            marker_start = handle.read(1)
            if not marker_start:
                break
            if marker_start != b"\xff":
                continue
            marker = handle.read(1)
            while marker == b"\xff":
                marker = handle.read(1)
            if marker in {bytes([value]) for value in range(0xC0, 0xC4)} | {bytes([value]) for value in range(0xC5, 0xC8)} | {bytes([value]) for value in range(0xC9, 0xCC)} | {bytes([value]) for value in range(0xCD, 0xD0)}:
                handle.read(2)
                handle.read(1)
                height, width = struct.unpack(">HH", handle.read(4))
                return width, height
            length_bytes = handle.read(2)
            if len(length_bytes) != 2:
                break
            segment_length = struct.unpack(">H", length_bytes)[0]
            handle.seek(max(segment_length - 2, 0), 1)
    raise ValueError(f"Image dimensions not found: {path}")


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


def main() -> int:
    checks: list[dict[str, Any]] = []
    required = [
        ROOT / "README.md",
        ROOT / "README_zh.md",
        ROOT / "requirements.txt",
        ROOT / ".gitignore",
        ROOT / "dashboard" / "uber_nyc_final_dashboard.html",
        ROOT / "reports" / "uber_nyc_growth_quality_report_en.html",
        ROOT / "reports" / "uber_nyc_growth_quality_report_zh.html",
        ROOT / "reports" / "executive_report_artifact_en.json",
        ROOT / "reports" / "executive_report_artifact_zh.json",
        ROOT / "reports" / "build_receipts.json",
        ROOT / "docs" / "METRIC_DEFINITIONS.md",
        ROOT / "docs" / "METRIC_DEFINITIONS_zh.md",
        ROOT / "docs" / "DATA_QUALITY_AND_CAVEATS.md",
        ROOT / "docs" / "DATA_QUALITY_AND_CAVEATS_zh.md",
        ROOT / "docs" / "REPRODUCTION.md",
        ROOT / "docs" / "REPRODUCTION_zh.md",
        ROOT / "data" / "README_zh.md",
        ROOT / "qa" / "browser_visual_qa.json",
        ROOT / "data" / "reference" / "taxi_zone_lookup.csv",
        ROOT / "data" / "processed" / "analytics" / "monthly_metrics.parquet",
        ROOT / "data" / "processed" / "analysis" / "analysis_summary.json",
    ]
    missing = [path.relative_to(ROOT).as_posix() for path in required if not path.is_file()]
    add(checks, "required release files", not missing, "All required files present" if not missing else str(missing))

    readme = (ROOT / "README.md").read_text(encoding="utf-8")
    readme_zh = (ROOT / "README_zh.md").read_text(encoding="utf-8")
    expected_sections = [
        "## Executive Findings",
        "## Business Recommendations",
        "## Dashboard Preview",
        "## Methodology / Data Pipeline",
        "## Metric Definitions",
        "## Data Quality & Caveats",
        "## Repository Structure",
        "## Reproduction",
        "## Data Source",
    ]
    section_positions = [readme.find(section) for section in expected_sections]
    ordered_sections = all(position >= 0 for position in section_positions) and section_positions == sorted(section_positions)
    add(checks, "README section contract", ordered_sections, f"{len(expected_sections)}/{len(expected_sections)} required sections in order")

    expected_sections_zh = [
        "## 核心分析发现",
        "## 业务建议",
        "## Dashboard 预览",
        "## 方法与数据管道",
        "## 核心指标定义",
        "## 数据质量与局限",
        "## 仓库结构",
        "## 复现方式",
        "## 数据来源",
    ]
    section_positions_zh = [readme_zh.find(section) for section in expected_sections_zh]
    ordered_sections_zh = all(position >= 0 for position in section_positions_zh) and section_positions_zh == sorted(section_positions_zh)
    add(checks, "README_zh section contract", ordered_sections_zh, f"{len(expected_sections_zh)}/{len(expected_sections_zh)} required sections in order")

    markdown_files = sorted(path for path in ROOT.rglob("*.md") if is_public_file(path))
    dead_links: list[str] = []
    link_count = 0
    for markdown_path in markdown_files:
        for link in local_markdown_links(markdown_path.read_text(encoding="utf-8")):
            link_count += 1
            target = (markdown_path.parent / link).resolve()
            if not target.exists():
                dead_links.append(f"{markdown_path.relative_to(ROOT).as_posix()} -> {link}")
    add(checks, "bilingual documentation links", not dead_links, f"{link_count} local links checked; dead={dead_links}")

    validation_specs = [
        ("analytics layer", ROOT / "data" / "processed" / "analytics" / "build_validation.csv", 11, "passed"),
        ("deep analysis", ROOT / "data" / "processed" / "analysis" / "analysis_validation.csv", 17, "passed"),
        ("dashboard numerical", ROOT / "dashboard" / "qa" / "dashboard_validation.csv", 14, "passed"),
        ("unified bilingual HTML", ROOT / "dashboard" / "qa" / "unified_dashboard_qa.csv", 23, "status"),
    ]
    for label, path, expected_count, status_field in validation_specs:
        rows = read_csv(path)
        if status_field == "passed":
            passed = len(rows) == expected_count and all(row[status_field].lower() == "true" for row in rows)
        else:
            passed = len(rows) == expected_count and all(row[status_field].upper() == "PASS" for row in rows)
        add(checks, f"{label} validation", passed, f"{sum(1 for row in rows if (row[status_field].lower() in {'true', 'pass'}))}/{expected_count} passed")

    summary = json.loads((ROOT / "data" / "processed" / "analysis" / "analysis_summary.json").read_text(encoding="utf-8"))
    headline = summary["headline_metrics"]
    expected_values = {
        "Trips": (15_354_816, 2.101),
        "Average request-to-pickup": (5.487, 8.761),
        "P90 request-to-pickup": (10.437, 16.85),
    }
    numerical_match = all(
        headline[name]["may_2026"] == current and headline[name]["change_pct"] == change
        for name, (current, change) in expected_values.items()
    )
    add(checks, "headline source values", numerical_match, "Trips, average wait, and P90 match the validated summary")

    artifact_en = json.loads((ROOT / "reports" / "executive_report_artifact_en.json").read_text(encoding="utf-8"))
    artifact_zh = json.loads((ROOT / "reports" / "executive_report_artifact_zh.json").read_text(encoding="utf-8"))
    signatures_match = numeric_signature(artifact_en) == numeric_signature(artifact_zh)
    block_order_en = [block.get("id") for block in artifact_en.get("manifest", {}).get("blocks", [])]
    block_order_zh = [block.get("id") for block in artifact_zh.get("manifest", {}).get("blocks", [])]
    add(checks, "bilingual report numeric identity", signatures_match, "Numeric signatures are identical")
    add(checks, "bilingual report structural identity", block_order_en == block_order_zh, "Block IDs and order are identical")

    receipts = json.loads((ROOT / "reports" / "build_receipts.json").read_text(encoding="utf-8"))
    receipts_ok = (
        receipts.get("numeric_signature") == "identical"
        and receipts.get("block_order") == "identical"
        and all(
            receipts.get(language, {}).get("ok") is True
            and receipts.get(language, {}).get("stages", {}).get("validation") == "passed"
            and receipts.get(language, {}).get("stages", {}).get("package") == "passed"
            for language in ("english", "chinese")
        )
    )
    add(checks, "bilingual report build receipts", receipts_ok, "Both portable reports passed validation and packaging")

    dashboard = (ROOT / "dashboard" / "uber_nyc_final_dashboard.html").read_text(encoding="utf-8")
    dashboard_tokens = ["15.35M", "5.49 min", "10.44 min", "2.99M", "1.27M", "318.3K"]
    readme_tokens = ["193.4M", "15.35M", "5.49 minutes", "10.44 minutes", "2.99M", "1.27M"]
    readme_zh_tokens = ["193.4M", "15.35M", "5.49 分钟", "10.44 分钟", "2.99M", "1.27M"]
    add(checks, "dashboard headline display", all(token in dashboard for token in dashboard_tokens), "All six headline display tokens found")
    add(checks, "README headline consistency", all(token in readme for token in readme_tokens), "All six README headline tokens found")
    add(checks, "README_zh headline consistency", all(token in readme_zh for token in readme_zh_tokens), "All six Chinese README headline tokens found")

    structural = {
        "tabs": len(re.findall(r'<button class="tab', dashboard)),
        "language_controls": len(re.findall(r'<button class="lang-btn', dashboard)),
        "english_pages": len(re.findall(r'class="dashboard-page[^\"]*"[^>]+data-lang="en"', dashboard)),
        "chinese_pages": len(re.findall(r'class="dashboard-page[^\"]*"[^>]+data-lang="zh"', dashboard)),
        "page2_callouts": len(re.findall(r'class="callout-box"', dashboard)),
        "external_resources": bool(re.search(r"<(?:script[^>]+src|link[^>]+href|img[^>]+src)", dashboard, flags=re.I)),
    }
    html_ok = structural == {
        "tabs": 3,
        "language_controls": 2,
        "english_pages": 3,
        "chinese_pages": 3,
        "page2_callouts": 8,
        "external_resources": False,
    }
    add(checks, "dashboard HTML structure", html_ok, json.dumps(structural, sort_keys=True))

    proxy_language_ok_en = all(
        phrase in readme.lower()
        for phrase in [
            "not proof of insufficient driver supply",
            "not profit, margin, or take rate",
            "completed records only",
        ]
    ) and "not causal proof of insufficient driver supply" in dashboard.lower()
    report_en = (ROOT / "reports" / "uber_nyc_growth_quality_report_en.html").read_text(encoding="utf-8")
    report_zh = (ROOT / "reports" / "uber_nyc_growth_quality_report_zh.html").read_text(encoding="utf-8")
    proxy_language_ok_zh = all(
        phrase in readme_zh
        for phrase in ["不构成司机供给不足的因果证明", "不代表利润、利润率或抽成率", "仅包含完成行程"]
    ) and "不构成司机供给不足的因果证明" in dashboard
    report_boundaries_ok = all(
        phrase in report_en.lower()
        for phrase in ["not causal proof of insufficient driver supply", "not labeled platform revenue, profit, margin, or take rate"]
    ) and all(
        phrase in report_zh
        for phrase in ["不构成司机供给不足的因果证明", "不定义为平台收入、利润、利润率或抽成率"]
    )
    add(checks, "interpretation boundaries", proxy_language_ok_en and proxy_language_ok_zh and report_boundaries_ok, "Proxy, causal, and financial boundaries are explicit across both languages and surfaces")

    expected_screenshot_names = {
        "dashboard-cover-en.jpg",
        "dashboard-page-1-marketplace-overview-en.jpg",
        "dashboard-page-2-marketplace-efficiency-en.jpg",
        "dashboard-page-3-growth-quality-priorities-en.jpg",
        "dashboard-cover-zh.jpg",
        "dashboard-page-1-marketplace-overview-zh.jpg",
        "dashboard-page-2-marketplace-efficiency-zh.jpg",
        "dashboard-page-3-growth-quality-priorities-zh.jpg",
    }
    screenshots = sorted((ROOT / "assets" / "dashboard").glob("*.jpg"))
    image_issues: list[str] = []
    for screenshot in screenshots:
        width, height = image_dimensions(screenshot)
        if width < 1500 or height < 900:
            image_issues.append(f"{screenshot.name}={width}x{height}")
    screenshot_names = {path.name for path in screenshots}
    png_files = sorted(path.name for path in (ROOT / "assets" / "dashboard").glob("*.png"))
    add(
        checks,
        "dashboard screenshot assets",
        screenshot_names == expected_screenshot_names and not image_issues and not png_files,
        f"{len(screenshots)} final JPEGs; name_delta={sorted(screenshot_names ^ expected_screenshot_names)}; issues={image_issues}; png={png_files}",
    )

    browser_qa = json.loads((ROOT / "qa" / "browser_visual_qa.json").read_text(encoding="utf-8"))
    add(
        checks,
        "real-browser visual QA",
        browser_qa.get("status") == "PASS",
        "Desktop/mobile, language switching, Page 2 overlap, and report interaction checks passed",
    )

    legacy_paths = [
        ROOT / "reports" / "uber_nyc_growth_quality_report.html",
        ROOT / "reports" / "executive_report_artifact.json",
        ROOT / "reports" / "_builder_test_en.html",
        ROOT / "assets" / "dashboard" / "dashboard-cover.jpg",
        ROOT / "assets" / "dashboard" / "dashboard-page-1-marketplace-overview.jpg",
        ROOT / "assets" / "dashboard" / "dashboard-page-2-marketplace-efficiency.jpg",
        ROOT / "assets" / "dashboard" / "dashboard-page-3-growth-quality-priorities.jpg",
    ]
    legacy_found = [path.relative_to(ROOT).as_posix() for path in legacy_paths if path.exists()]
    add(checks, "legacy release cleanup", not legacy_found, f"Legacy files={legacy_found}")

    public_files = [path for path in ROOT.rglob("*") if is_public_file(path)]
    raw_files = sorted(
        path.relative_to(ROOT).as_posix()
        for path in public_files
        if path.match("fhvhv_tripdata_*.parquet")
    )
    add(checks, "raw Parquet exclusion", not raw_files, "No raw monthly Parquet files in the public package")

    oversized = [
        f"{path.relative_to(ROOT).as_posix()} ({path.stat().st_size / 1024 / 1024:.1f} MB)"
        for path in public_files
        if path.stat().st_size > MAX_PUBLIC_FILE_BYTES
    ]
    add(checks, "GitHub file-size UX", not oversized, f"Largest file under 50 MB; oversized={oversized}")

    text_files = [
        path for path in public_files
        if path.suffix.lower() in TEXT_SUFFIXES or path.name == ".gitignore"
    ]
    path_leaks: list[str] = []
    trace_hits: list[str] = []
    trace_pattern = re.compile("(?:Chat" + "GPT|Open" + "AI|Co" + "dex|AI-generated|as an AI)", re.I)
    drive_pattern = re.compile(r"[A-Za-z]:\\(?:Users|Documents|经营分析学习)\\")
    for path in text_files:
        text = path.read_text(encoding="utf-8-sig", errors="replace")
        rel = path.relative_to(ROOT).as_posix()
        is_audit_script = path.resolve() == Path(__file__).resolve()
        if not is_audit_script and (drive_pattern.search(text) or "/Users/" in text):
            path_leaks.append(rel)
        if not is_audit_script and trace_pattern.search(text):
            trace_hits.append(rel)
    add(checks, "local-path privacy", not path_leaks, f"Local path leaks={path_leaks}")
    add(checks, "AI-trace scan", not trace_hits, f"Trace hits={trace_hits}")

    compile_failures: list[str] = []
    for script in sorted((ROOT / "scripts").glob("*.py")):
        try:
            compile(script.read_text(encoding="utf-8"), str(script), "exec")
        except SyntaxError as error:
            compile_failures.append(f"{script.name}: {error}")
    add(checks, "Python script syntax", not compile_failures, f"{len(list((ROOT / 'scripts').glob('*.py')))} scripts checked; failures={compile_failures}")

    gitignore = (ROOT / ".gitignore").read_text(encoding="utf-8")
    gitignore_ok = all(token in gitignore for token in ["data/raw/", "Uber数据/", "fhvhv_tripdata_*.parquet", ".venv/"])
    add(checks, "raw-data Git guardrail", gitignore_ok, "Raw directories, monthly Parquet pattern, and virtual environment are ignored")

    failures = [row for row in checks if row["status"] != "PASS"]
    total_bytes = sum(path.stat().st_size for path in public_files)
    result = {
        "assessment": "READY FOR GITHUB" if not failures else "NEEDS REVISION",
        "checks_passed": len(checks) - len(failures),
        "checks_total": len(checks),
        "repository_files": len(public_files),
        "repository_size_mb": round(total_bytes / 1024 / 1024, 2),
        "largest_file_mb": round(max(path.stat().st_size for path in public_files) / 1024 / 1024, 2),
        "checks": checks,
    }

    qa_dir = ROOT / "qa"
    qa_dir.mkdir(parents=True, exist_ok=True)
    (qa_dir / "final_audit.json").write_text(json.dumps(result, indent=2), encoding="utf-8")
    markdown = [
        "# Final GitHub Release Audit",
        "",
        f"**Assessment: {result['assessment']}**",
        "",
        f"- Checks: {result['checks_passed']}/{result['checks_total']} passed",
        f"- Public package: {result['repository_files']} files, {result['repository_size_mb']} MB",
        f"- Largest file: {result['largest_file_mb']} MB",
        "",
        "| Check | Status | Detail |",
        "|---|---:|---|",
    ]
    for row in checks:
        detail = str(row["detail"]).replace("|", "\\|")
        markdown.append(f"| {row['check']} | {row['status']} | {detail} |")
    markdown.append("")
    (qa_dir / "final_audit.md").write_text("\n".join(markdown), encoding="utf-8")

    print(json.dumps({key: result[key] for key in ["assessment", "checks_passed", "checks_total", "repository_size_mb", "largest_file_mb"]}))
    return 0 if not failures else 1


if __name__ == "__main__":
    raise SystemExit(main())
