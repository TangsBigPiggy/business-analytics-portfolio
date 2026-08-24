from pathlib import Path
import pandas as pd
import numpy as np

ROOT = Path(__file__).resolve().parent
DATA = ROOT / "data" / "H2.csv.gz"

MONTHS = {m: i for i, m in enumerate([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December"
], 1)}
LEAD_BINS = [-1, 7, 30, 60, 90, 180, 10_000]
LEAD_LABELS = ["0–7", "8–30", "31–60", "61–90", "91–180", "181+"]


def load_h2() -> pd.DataFrame:
    df = pd.read_csv(DATA, keep_default_na=False, low_memory=False)
    for c in df.select_dtypes(include="object").columns:
        df[c] = df[c].astype(str).str.strip()

    if len(df) != 79_330:
        raise ValueError(f"Unexpected H2 row count: {len(df):,}")

    df["ArrivalMonthNum"] = df["ArrivalDateMonth"].map(MONTHS)
    df["ArrivalDate"] = pd.to_datetime(dict(
        year=df["ArrivalDateYear"],
        month=df["ArrivalMonthNum"],
        day=df["ArrivalDateDayOfMonth"],
    ))
    df["ReservationStatusDate"] = pd.to_datetime(df["ReservationStatusDate"], errors="coerce")
    df["TotalNights"] = df["StaysInWeekendNights"] + df["StaysInWeekNights"]
    df["NonMaterialized"] = df["IsCanceled"].astype(int)
    df["Realized"] = df["ReservationStatus"].eq("Check-Out").astype(int)
    df["NoShow"] = df["ReservationStatus"].eq("No-Show").astype(int)
    df["ExplicitCancellation"] = df["ReservationStatus"].eq("Canceled").astype(int)

    expected = (df["ExplicitCancellation"].astype(bool) | df["NoShow"].astype(bool)).astype(int)
    if not df["NonMaterialized"].eq(expected).all():
        raise ValueError("IsCanceled does not reconcile to final reservation status.")

    df["FailedRoomNights"] = df["TotalNights"] * df["NonMaterialized"]
    df["LeadTimeBand"] = pd.cut(
        df["LeadTime"], bins=LEAD_BINS, labels=LEAD_LABELS
    )
    df["CancelLeadDays"] = np.where(
        df["ExplicitCancellation"].eq(1),
        (df["ArrivalDate"] - df["ReservationStatusDate"]).dt.days,
        np.nan,
    )
    return df


def standardized_rate(df: pd.DataFrame, segment: str, weights: pd.Series) -> float:
    rates = (
        df[df["MarketSegment"].eq(segment)]
        .groupby("LeadTimeBand", observed=True)["NonMaterialized"]
        .mean()
        .reindex(LEAD_LABELS)
    )
    valid = rates.notna() & weights.gt(0)
    w = weights[valid] / weights[valid].sum()
    return float((rates[valid] * w).sum())


def summarize(df: pd.DataFrame) -> dict:
    nd = df[df["DepositType"].eq("No Deposit")].copy()
    online = nd[nd["MarketSegment"].eq("Online TA")]

    combined = nd[nd["MarketSegment"].isin(["Online TA", "Direct"])]
    weights = (
        combined["LeadTimeBand"]
        .value_counts(normalize=True)
        .reindex(LEAD_LABELS, fill_value=0)
    )

    core = nd[
        nd["MarketSegment"].eq("Online TA")
        & nd["ArrivalDateYear"].isin([2016, 2017])
        & nd["ArrivalDate"].dt.month.le(8)
    ]

    long_ota = online[online["LeadTime"].ge(91)]
    failed_long_ota = long_ota[long_ota["NonMaterialized"].eq(1)]
    early_long_ota = failed_long_ota[
        failed_long_ota["ExplicitCancellation"].eq(1)
        & failed_long_ota["CancelLeadDays"].gt(30)
    ]

    nd_failed = nd[nd["NonMaterialized"].eq(1)]
    nd_early = nd_failed[
        nd_failed["ExplicitCancellation"].eq(1)
        & nd_failed["CancelLeadDays"].gt(30)
    ]
    nd_late = nd_failed[
        nd_failed["NoShow"].eq(1)
        | (nd_failed["ExplicitCancellation"].eq(1) & nd_failed["CancelLeadDays"].le(7))
    ]

    y = {}
    for year in [2016, 2017]:
        x = core[core["ArrivalDateYear"].eq(year)]
        y[year] = {
            "bookings": len(x),
            "non_materialization_rate": x["NonMaterialized"].mean(),
            "failed_room_nights": x["FailedRoomNights"].sum(),
        }

    return {
        "bookings": len(df),
        "overall_non_materialization_rate": df["NonMaterialized"].mean(),
        "no_deposit_bookings": len(nd),
        "no_deposit_share": len(nd) / len(df),
        "no_deposit_non_materialization_rate": nd["NonMaterialized"].mean(),
        "no_deposit_failed_room_nights": nd["FailedRoomNights"].sum(),
        "online_ta_share_of_no_deposit_bookings": len(online) / len(nd),
        "online_ta_share_of_no_deposit_failed_room_nights": (
            online["FailedRoomNights"].sum() / nd["FailedRoomNights"].sum()
        ),
        "standardized_online_ta_rate": standardized_rate(nd, "Online TA", weights),
        "standardized_direct_rate": standardized_rate(nd, "Direct", weights),
        "long_lead_online_ta_bookings": len(long_ota),
        "long_lead_online_ta_rate": long_ota["NonMaterialized"].mean(),
        "long_lead_online_ta_failed_room_nights": long_ota["FailedRoomNights"].sum(),
        "long_lead_online_ta_failed_room_night_share": (
            long_ota["FailedRoomNights"].sum() / nd["FailedRoomNights"].sum()
        ),
        "long_lead_online_ta_early_cancellation_share": (
            early_long_ota["FailedRoomNights"].sum() / failed_long_ota["FailedRoomNights"].sum()
        ),
        "no_deposit_early_cancellation_share": (
            nd_early["FailedRoomNights"].sum() / nd_failed["FailedRoomNights"].sum()
        ),
        "no_deposit_late_leakage_share": (
            nd_late["FailedRoomNights"].sum() / nd_failed["FailedRoomNights"].sum()
        ),
        "core_2016": y[2016],
        "core_2017": y[2017],
    }


if __name__ == "__main__":
    data = load_h2()
    result = summarize(data)
    for key, value in result.items():
        print(f"{key}: {value}")
