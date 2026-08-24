# Business Analytics Portfolio

**Decision-focused business analytics | Commercial diagnosis | Interactive BI | Executive communication**

This repository contains business analytics case studies built around real operating questions rather than isolated technical exercises. Each case starts with a management problem, establishes defensible metrics, tests where risk or opportunity is concentrated, and translates the evidence into decisions while making the limits of the data explicit.

The work is intended for hiring managers, business leaders, and clients evaluating practical capability across **business problem framing, data analysis, KPI design, visualization, commercial interpretation, and decision support**.

## Featured case

### 01 · H2 City Hotel — Booking Reliability & Inventory Exposure

[![H2 City Hotel executive dashboard](01-hotel-booking-reliability/dashboard/preview.png)](01-hotel-booking-reliability/README.md)

**Business question:** Which booked demand should the hotel rely on, where is inventory exposure concentrated among No Deposit bookings, and which operating or policy changes are supported by the available evidence?

The case analyzes **79,330 real PMS booking records** from a Lisbon city hotel. The analytical focus is booking reliability rather than headline cancellation rate: payment status, channel concentration, lead-time risk, cancellation timing, and the distinction between observable inventory exposure and unobserved economic loss.

**Selected findings**

- No Deposit represents **83.75%** of bookings, with a **30.5%** non-materialization rate.
- Online TA accounts for **58.3%** of No Deposit bookings but **75.8%** of failed No Deposit room nights.
- After standardizing the lead-time mix, non-materialization remains **36.2% for Online TA vs 19.4% for Direct**; the result supports targeted monitoring, not a causal channel claim.
- Cancellations accounting for **54.2%** of failed No Deposit room-night exposure occur more than 30 days before arrival, creating a meaningful window for inventory-recovery action and measurement.
- The analysis deliberately does **not** translate failed room nights into lost revenue because resale, settlement, commission, contribution margin, and daily room inventory are not observed.

**Deliverables:** [Case overview](01-hotel-booking-reliability/README.md) · [Interactive dashboard](01-hotel-booking-reliability/dashboard/index.html) · [Business analytics report](01-hotel-booking-reliability/report/H2_City_Hotel_Business_Analytics_Report_EN.pdf) · [Methodology](01-hotel-booking-reliability/docs/METHOD.md)

**Tools:** Python · pandas · NumPy · Plotly · HTML/CSS/JavaScript

---

## Portfolio standard

Across cases, the emphasis is on four disciplines:

**1. Start with the business decision.** Analysis is scoped around a decision or operating question rather than around available columns or algorithms.

**2. Separate scale from rate.** High percentages are not automatically important; exposure, volume, timing, and economic context determine management priority.

**3. Control the strength of the claim.** Descriptive evidence, standardized comparisons, causal inference, and financial impact are treated as different levels of evidence.

**4. Make the output usable.** Findings are delivered through concise written analysis and decision-oriented visualizations, with definitions and analytical boundaries documented for review.

Additional business analytics cases will be added to this repository as separate, self-contained projects.