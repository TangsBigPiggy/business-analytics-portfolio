# H2 City Hotel — Business Analytics Report

**Management decision support | 79,330 real booking records | Lisbon | Arrivals Jul 2015–Aug 2017**

## Executive summary

The management issue is not cancellation rate in isolation. It is the **reliability and recoverability of booked demand**: which bookings are least likely to materialize, where failed room-night exposure is concentrated, and how much time remains to respond when a cancellation occurs.

The evidence supports targeted operating changes, while broader commercial-policy changes require prospective measurement of conversion, resale, settlement, channel cost, and contribution economics.

The main operating position is to treat long-lead **No Deposit + Online TA** demand as a lower-confidence forecast pool, make early-cancellation recovery measurable, concentrate near-arrival controls where recovery time is shortest, and avoid broad channel or deposit restrictions based on historical cancellation associations alone.

### Key evidence

1. **Deposit status changes the meaning of the headline rate.** Overall non-materialization is 41.7%, but deposit categories are not economically equivalent. No Deposit is the primary operating scope: 66,442 bookings (83.75% of H2) with a 30.5% non-materialization rate.
2. **Exposure is concentrated in Online TA.** Online TA represents 58.3% of No Deposit bookings but 75.8% of failed No Deposit room nights. After standardizing the lead-time mix, non-materialization remains 36.2% for Online TA versus 19.4% for Direct.
3. **Long-horizon demand is materially less reliable.** No Deposit + Online TA + 91+ days represents 21.5% of No Deposit bookings but 36.5% of failed room-night exposure, with a 46.0% non-materialization rate.
4. **Forecast risk and recovery opportunity are different problems.** Cancellations accounting for 54.2% of failed No Deposit room-night exposure occur more than 30 days before arrival. In the 91+ day Online TA cohort, that share is 82.6%.
5. **Reliability changed materially between comparable periods.** In the matched Jan–Aug comparison, core-channel bookings rose 26.9% from 2016 to 2017 while failed room nights rose 55.8%. The lead-time-standardized non-materialization rate increased by 4.3 percentage points.

---

## 1. Payment status and booking reliability

H2 records an overall non-materialization rate of **41.7%**. That figure is operationally real but economically ambiguous because deposit categories represent different recorded payment states.

The source defines **Non Refund** as payment equal to or above the total stay cost. The observed 99.8% non-materialization rate in this category is an unusually concentrated operating/data pattern and should not be treated as a normal benchmark for non-refundable policy performance. In an operating setting, booking/block, payment, settlement, and status-coding processes should be validated before commercial conclusions are drawn from this cohort.

**No Deposit** is the more decision-relevant scope for this analysis: 66,442 bookings, 83.75% of H2, and a 30.5% non-materialization rate. The label means that no deposit payment was identified in the published field; it does not prove the absence of every possible card, contractual, or channel-level guarantee.

The **Refundable** category contains only 20 H2 bookings. Its observed 70.0% non-materialization rate is real, but the sample is too small to support policy inference.

**Management interpretation:** behavioral non-materialization, recorded payment protection, and economic loss should remain separate measures. A single headline cancellation rate obscures those differences.

---

## 2. Exposure concentration

Operating attention should follow **exposure**, not failure rate alone.

Within No Deposit bookings, Online TA combines the largest booking base with materially weaker realization. It contributes **58.3% of bookings** but **75.8% of failed room-night exposure**, equivalent to 51,683 failed booked room nights.

Lead-time mix explains part, but not all, of the raw channel difference. Standardizing Online TA and Direct to the same combined No Deposit lead-time distribution produces non-materialization rates of **36.2% and 19.4%**, respectively, an observed gap of 16.8 percentage points.

This is still an observational comparison. Customer mix, offer conditions, room type, season, and other factors may differ by channel. The result supports channel-specific monitoring and targeted testing; it does not establish that Online TA itself causes the gap.

---

## 3. Lead-time risk

Long-lead demand is materially less reliable and should carry lower forecast confidence.

Within No Deposit bookings, non-materialization rises from roughly 12% at 0–7 days to above 40% at 181+ days. The relationship is not perfectly monotonic across every intermediate bucket, so the defensible conclusion is not that risk increases at every step; it is that **long-horizon bookings are materially less reliable overall**.

The concentration is sharper within the main channel. **No Deposit + Online TA + 91+ days** represents 14,294 bookings, 21.5% of No Deposit demand, with a 46.0% non-materialization rate and 24,929 failed room nights — 36.5% of all No Deposit failed room-night exposure.

**Management interpretation:** use cohort-specific reliability assumptions for planning rather than applying one realization rate to all forward bookings. This does not, by itself, justify a blanket deposit restriction.

---

## 4. Recovery timing

Failure prevention and inventory recovery are separate operating problems.

Across No Deposit failures, cancellations accounting for **54.2%** of failed room-night exposure occur more than 30 days before arrival. A further **25.6%** occurs 8–30 days before arrival. No-show and 0–7 day cancellations account for **20.2%**, where the available recovery time is much shorter.

The distinction is particularly important in the long-lead Online TA cohort: cancellations accounting for **82.6%** of its failed room-night exposure occur more than 30 days before arrival. The cohort is unreliable for forecasting, but much of the cancellation exposure becomes visible early enough to create a potential recovery window.

The dataset does **not** show whether canceled inventory returned to the sellable pool, whether it was resold, the ADR achieved on resale, or the channel and acquisition cost of any replacement demand.

**Operating response:** after an early cancellation, verify prompt return to sellable inventory subject to room-type and overbooking controls, then measure the subsequent resale outcome. Near arrival, evaluate targeted confirmation or guarantee controls where late leakage is concentrated.

---

## 5. Matched-period reliability comparison

The dataset begins in July 2015 and ends in August 2017, so a full-year comparison would mix unequal coverage windows. The analysis therefore compares **Jan–Aug 2016 with Jan–Aug 2017** for No Deposit + Online TA.

Bookings increased from 12,584 to 15,963 (**+26.9%**), while failed booked room nights increased from 15,123 to 23,560 (**+55.8%**).

The observed non-materialization rate increased by 6.9 percentage points. After standardizing the lead-time mix, the rate still increased by **4.3 percentage points**, from approximately 35.0% to 39.3%.

Two matched periods do not constitute a continuous trend, and the data do not identify why the cohort changed. The comparison does show that a fixed historical reliability assumption would have overstated the later cohort's realization.

**Management interpretation:** refresh major channel × lead-time reliability parameters periodically rather than embedding one historical rate as a permanent planning assumption.

---

## Management decision framework

| Decision area | Action supported by current evidence | Boundary |
|---|---|---|
| Forecasting | Apply lower reliability assumptions to long-lead No Deposit Online TA demand. | Planning rule, not a causal intervention. |
| Inventory recovery | Return inventory promptly after early cancellation and measure actual resale. | Current data show a time window, not realized recovery. |
| Near-arrival controls | Test targeted confirmation or guarantee controls where late leakage is concentrated. | Conversion and guest impact must be measured prospectively. |
| Channel / deposit policy | Use a controlled targeted test before broad term changes. | Historical association cannot quantify conversion loss, friction, or contribution impact. |
| Management cadence | Review reliability by major channel × lead-time cohort. | Avoid static risk assumptions. |

The objective is **not** to minimize cancellations mechanically. It is to improve the economic quality and predictability of booked demand without destroying conversion, recoverability, or contribution.

---

## Data required for the next decision

The next analytical step is better economic instrumentation rather than further historical slicing.

| Data domain | Fields to capture | Decision value |
|---|---|---|
| Recovery economics | Resale flag/timestamp, resale ADR, resale channel | Measures whether released inventory was recovered and at what quality. |
| Payment economics | Guarantee/payment status, final settlement, refunds/chargebacks | Separates behavioral cancellation from actual financial protection. |
| Channel economics | Commission, acquisition cost, contribution margin | Converts room-night exposure into contribution economics. |
| Policy response | Offer/rule shown, booking conversion/abandonment, exact event timestamps | Measures whether tighter controls destroy demand or change customer mix. |
| Inventory context | Daily available rooms, room-type capacity, overbooking state | Enables occupancy/RevPAR-style interpretation and recovery-capacity analysis. |
| Guest impact | Service contacts, complaints, exception handling | Captures friction and operating cost from policy interventions. |

## Analytical boundaries

This report identifies where management attention is most likely to matter and how the operating problems differ. It does **not** estimate the causal effect or financial return of a new commercial policy.

- 79,330 H2 booking observations are retained, matching the source article.
- `IsCanceled` reconciles to final `Canceled + No-Show` status.
- Failed booked room nights equal booked nights × non-materialization indicator and are treated as inventory exposure, not lost revenue.
- Online TA vs Direct and the matched-period comparison use common lead-time distributions to improve comparability on lead time; unobserved confounding remains.
- Zero-night bookings remain in booking-rate denominators but contribute zero room nights to exposure metrics.
- ADR is not used to infer lost revenue.

**Source:** Nuno Antonio, Ana de Almeida, Luis Nunes. *Hotel booking demand datasets*. Data in Brief 22 (2019), 41–49. DOI: 10.1016/j.dib.2018.11.126. H2 is the City Hotel property in Lisbon.