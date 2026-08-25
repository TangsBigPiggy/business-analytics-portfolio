# Business Analytics Portfolio

**Decision-focused business analytics | Commercial diagnosis | Interactive BI | Executive communication**

This repository contains business analytics case studies built around real operating questions rather than isolated technical exercises. Each case starts with a management problem, establishes defensible metrics, tests where risk or opportunity is concentrated, and translates the evidence into decisions while making the limits of the data explicit.

The work is intended for hiring managers, business leaders, and clients evaluating practical capability across **business problem framing, data analysis, KPI design, visualization, commercial interpretation, and decision support**.

## Featured cases

### 02 · Uber NYC — Marketplace Growth Quality & Service Efficiency

[![Uber NYC marketplace dashboard preview](02-uber-nyc-growth-quality/assets/dashboard/dashboard-cover-en.jpg)](https://raw.githack.com/TangsBigPiggy/business-analytics-portfolio/main/02-uber-nyc-growth-quality/dashboard/uber_nyc_final_dashboard.html?lang=en#page-1)

**Business question:** Did May 2026 trip growth come with worsening marketplace service quality—and where should operators investigate first?

The case analyzes **193.4 million completed Uber HVFHV trips** across **13 months in New York City**. It combines a scalable DuckDB/Python pipeline with a bilingual three-page management dashboard, bilingual executive reports, taxi-zone prioritization, and explicit evidence boundaries.

**Selected findings**

- May 2026 completed trips increased **2.1% YoY to 15.35M**, while average request-to-pickup rose **8.8% to 5.49 minutes** and P90 rose **16.9% to 10.44 minutes**.
- The citywide time increase was driven by **+0.449 minutes of within-borough movement**; geographic mix offset roughly **0.008 minutes**.
- Manhattan and Brooklyn contributed **318.3K trips**, equivalent to **100.7% of net city growth** because declines elsewhere offset part of the gain.
- A supply-constrained priority proxy identified **23 taxi zones covering 2.99M trips**. It is an operating-priority proxy from completed trips and observed service performance—not causal proof of insufficient driver supply.
- Passenger base fare and driver pay remain separate measures; their difference is not interpreted as profit, margin, or take rate.

**Deliverables:** [Case overview](02-uber-nyc-growth-quality/README.md) · [中文说明](02-uber-nyc-growth-quality/README_zh.md) · [Live bilingual dashboard](https://raw.githack.com/TangsBigPiggy/business-analytics-portfolio/main/02-uber-nyc-growth-quality/dashboard/uber_nyc_final_dashboard.html?lang=en#page-1) · [English report](https://raw.githack.com/TangsBigPiggy/business-analytics-portfolio/main/02-uber-nyc-growth-quality/reports/uber_nyc_growth_quality_report_en.html) · [中文报告](https://raw.githack.com/TangsBigPiggy/business-analytics-portfolio/main/02-uber-nyc-growth-quality/reports/uber_nyc_growth_quality_report_zh.html)

**Tools:** Python · DuckDB · Parquet · HTML/CSS/JavaScript

---

### 01 · H2 City Hotel — Booking Reliability & Inventory Exposure

[![H2 City Hotel dashboard preview](01-hotel-booking-reliability/dashboard/preview.svg)](01-hotel-booking-reliability/README.md)

**Business question:** Which booked demand should the hotel rely on, where is inventory exposure concentrated among No Deposit bookings, and which operating or policy changes are supported by the available evidence?

The case analyzes **79,330 real PMS booking records** from a Lisbon city hotel. The analytical focus is booking reliability rather than headline cancellation rate: payment status, channel concentration, lead-time risk, cancellation timing, and the distinction between observable inventory exposure and unobserved economic loss.

**Selected findings**

- No Deposit represents **83.75%** of bookings, with a **30.5%** non-materialization rate.
- Online TA accounts for **58.3%** of No Deposit bookings but **75.8%** of failed No Deposit room nights.
- After standardizing the lead-time mix, non-materialization remains **36.2% for Online TA vs 19.4% for Direct**; the result supports targeted monitoring, not a causal channel claim.
- Cancellations accounting for **54.2%** of failed No Deposit room-night exposure occur more than 30 days before arrival, creating a meaningful window for inventory-recovery action and measurement.
- The analysis deliberately does **not** translate failed room nights into lost revenue because resale, settlement, commission, contribution margin, and daily room inventory are not observed.

**Deliverables:** [Case overview](01-hotel-booking-reliability/README.md) · [Live dashboard](https://raw.githack.com/TangsBigPiggy/business-analytics-portfolio/main/01-hotel-booking-reliability/dashboard/index.html) · [Management report](01-hotel-booking-reliability/report/REPORT.md) · [Methodology](01-hotel-booking-reliability/docs/METHOD.md) · [Reproducible analysis](01-hotel-booking-reliability/analysis.py)

**Tools:** Python · pandas · NumPy · Plotly · HTML/CSS/JavaScript

---

## Portfolio standard

Across cases, the emphasis is on four disciplines:

**1. Start with the business decision.** Analysis is scoped around a decision or operating question rather than around available columns or algorithms.

**2. Separate scale from rate.** High percentages are not automatically important; exposure, volume, timing, and economic context determine management priority.

**3. Control the strength of the claim.** Descriptive evidence, standardized comparisons, causal inference, and financial impact are treated as different levels of evidence.

**4. Make the output usable.** Findings are delivered through concise written analysis and decision-oriented visualizations, with definitions and analytical boundaries documented for review.

Each case is maintained as a separate, self-contained project with its own evidence, methodology, deliverables, and reproduction path.
