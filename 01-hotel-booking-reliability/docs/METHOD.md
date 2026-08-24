# Method, Metric Definitions and Analytical Boundaries

## Scope

- **Property:** H2 City Hotel, Lisbon
- **Rows:** 79,330 published booking observations
- **Arrival window:** July 2015 to August 2017
- **Source:** Antonio, de Almeida & Nunes (2019), *Hotel booking demand datasets*
- **Analytical grain:** one row per published booking observation

The analysis covers H2 City Hotel only.

## Analytical focus

The dataset contains booking outcomes, booking characteristics, and booked room nights, but it does **not** contain daily available-room inventory, observed resale of canceled rooms, channel commission, final payment settlement, booking-funnel conversion, or contribution margin. Occupancy, RevPAR, GOPPAR, policy ROI, and realized lost revenue therefore cannot be estimated reliably from this extract.

The analysis is limited to three questions the data can support: **how reliably booked demand materializes, where failed booked room-night exposure is concentrated, and how much time remains before arrival when an explicit cancellation occurs.**

## Source semantics that affect interpretation

### Data timing

The source article states that the analytical data point for an observation was defined relative to the **day prior to arrival**, using booking-change-log values where available. Some fields can therefore reflect changes made after the booking was created. The dashboard is a retrospective diagnostic, not an at-booking production prediction system.

### Outcome

`IsCanceled = 1` reconciles exactly to `ReservationStatus` equal to `Canceled` or `No-Show` in H2.

- **Realized booking:** `ReservationStatus = Check-Out`
- **Non-materialized booking:** `IsCanceled = 1`
- **No-show:** `ReservationStatus = No-Show`

### Deposit type

The published `DepositType` field is payment-derived:

- **No Deposit:** no payment identified before arrival or cancellation
- **Non Refund:** payment equal to or above the total stay cost
- **Refundable:** payment below the total stay cost

These categories are not economically equivalent. The reliability analysis therefore focuses primarily on **No Deposit** bookings, for which no deposit payment was recorded. This does not prove that every other card guarantee, contractual penalty, or channel-level protection mechanism was absent.

The **99.8%** observed non-materialization rate in `Non Refund` is an unusual operating/data pattern and should not be treated as a general commercial benchmark. The cohort is concentrated in group and Offline TA/TO structures, while the public extract does not contain booking/block identifiers or settlement detail. In an operating setting, group-block, cancellation, payment, and status-coding processes should be validated before policy conclusions are drawn from this cohort.

The `Refundable` category contains only **20 H2 bookings**. Its observed non-materialization rate is **70.0%**, but the sample is too small to support a commercial-policy conclusion. Small display shares are shown with additional precision in the dashboard so that the cohort is not rounded to zero.

### Cancellation timing

For explicit cancellations:

`Cancellation lead days = ArrivalDate - ReservationStatusDate`

The source states that `ReservationStatusDate` can be used with `ReservationStatus` to identify when a booking was canceled. No-shows are kept separate because there is no pre-arrival cancellation event from which to define a recovery window.

### Room-night exposure

`Booked room nights = StaysInWeekendNights + StaysInWeekNights`

`Failed booked room nights = Booked room nights multiplied by IsCanceled`

Failed booked room nights measure **booked inventory attached to non-materialized reservations**. They are not confirmed lost room nights: canceled inventory may have returned to sale and may have been resold, neither of which is observed.

## Core KPI definitions

| KPI | Definition | Interpretation boundary |
|---|---|---|
| Realization rate | Check-Out bookings / bookings | Booking outcome rate; not occupancy |
| Non-materialization rate | Canceled + No-show / bookings | Booking outcome; not revenue loss |
| No Deposit share | No Deposit bookings / bookings | No recorded deposit payment; not proof that every other guarantee mechanism was absent |
| No Deposit non-materialization rate | Failed No Deposit bookings / No Deposit bookings | Primary reliability KPI for the No Deposit scope |
| Failed booked room nights | Room nights attached to failed bookings | Inventory exposure; resale is unobserved |
| Late leakage share | No-show + cancellations 0-7 days before arrival, weighted by failed room nights | Exposure with little remaining recovery time; 7 days is an analytical threshold |
| Early-cancellation share | Cancellations >30 days before arrival, weighted by failed room nights | Exposure with more time available for recovery attempts; actual resale is unobserved |

## Lead-time buckets

The dashboard uses six lead-time buckets:

- 0-7 days
- 8-30 days
- 31-60 days
- 61-90 days
- 91-180 days
- 181+ days

The final bucket combines the far tail, including the small 366+ day segment, to keep cohort sizes and the visual presentation stable.

## Standardized comparison: Online TA vs Direct

Online TA and Direct have different lead-time distributions. The written analysis therefore standardizes both segments to the **same combined No Deposit lead-time distribution** across the six dashboard buckets.

The standardized non-materialization rates are **36.2% for Online TA** and **19.4% for Direct**. This improves comparability with respect to lead time only. Customer mix, offer conditions, room type, season, and other observed or unobserved factors can still differ by channel, so the result remains an association rather than a causal channel effect.

## Matched-period comparison

The data begin in July 2015 and end in August 2017. A full-year comparison would therefore mix unequal coverage windows. The dashboard compares **January-August 2016 with January-August 2017** for the No Deposit + Online TA cohort.

Because only two matched periods are compared, the result should be read as a **two-period comparison**, not as a continuous time-series trend. The dashboard reports both the observed rate and a lead-time-standardized rate using a common lead-time distribution. The standardization improves comparability but does not establish a causal time effect.

## Data-quality decisions

- **79,330 rows** are retained, matching the source article.
- **25,902 rows repeat a previously observed combination across all published fields.** They are retained because the public extract has no booking ID; identical published fields can represent legitimate multi-room or group bookings and cannot be proven to be accidental duplicates.
- Literal `NULL` values in categorical fields such as Agent and Company are not automatically treated as missing because the source article defines them as a meaningful "not applicable" category.
- **331 zero-night bookings** remain in booking-rate denominators but contribute zero room nights to exposure metrics.
- ADR is not used to estimate lost revenue. H2 contains zero values and an extreme high value, and the dataset does not provide final revenue recognition or resale outcomes.

## Policy-inference boundary

Historical segmentation is used to identify where a prospective test may be most informative; it does not estimate the financial effect of a new policy. A guarantee or channel-policy change can alter booking conversion, customer mix, channel cost, guest experience, and resale behavior, none of which is identified by this retrospective extract. Broad policy changes therefore require prospective measurement rather than cancellation-rate comparisons alone.

## Claims not made

This project does **not** claim that:

- a failed booking equals lost revenue;
- changing channel mix would cause the observed rate gap to disappear;
- long lead time causes cancellation;
- an early-canceled room was subsequently resold;
- the dashboard is a production prediction model;
- recorded payment protection equals final realized revenue.

The dashboard is a **retrospective revenue-management diagnostic** designed to support cohort monitoring and to define the next measurement questions.