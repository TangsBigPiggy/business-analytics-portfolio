import numpy as np
import pandas as pd

DATA_URL = (
    "https://raw.githubusercontent.com/rfordatascience/tidytuesday/main/"
    "data/2020/2020-02-11/hotels.csv"
)
MONTHS = {m: i for i, m in enumerate([
    "January", "February", "March", "April", "May", "June",
    "July", "August", "September", "October", "November", "December",
], 1)}
LEAD_BINS = [-1, 7, 30, 60, 90, 180, 10_000]
LEAD_LABELS = ["0–7", "8–30", "31–60", "61–90", "91–180", "181+"]


def load_h2() -> pd.DataFrame:
    """Load the public source mirror and retain the H2 / City Hotel property only."""
    df = pd.read_csv(DATA_URL, low_memory=False)
    df = df[df["hotel"].eq("City Hotel")].copy()

    if len(df) != 79_330:
        raise ValueError(f"Unexpected H2 row count: {len(df):,}")

    df["arrival_month_num"] = df["arrival_date_month"].map(MONTHS)
    df["arrival_date"] = pd.to_datetime(dict(
        year=df["arrival_date_year"],
        month=df["arrival_month_num"],
        day=df["arrival_date_day_of_month"],
    ))
    df["reservation_status_date"] = pd.to_datetime(
        df["reservation_status_date"], errors="coerce"
    )
    df["total_nights"] = df["stays_in_weekend_nights"] + df["stays_in_week_nights"]
    df["non_materialized"] = df["is_canceled"].astype(int)
    df["realized"] = df["reservation_status"].eq("Check-Out").astype(int)
    df["no_show"] = df["reservation_status"].eq("No-Show").astype(int)
    df["explicit_cancellation"] = df["reservation_status"].eq("Canceled").astype(int)

    expected = (
        df["explicit_cancellation"].astype(bool) | df["no_show"].astype(bool)
    ).astype(int)
    if not df["non_materialized"].eq(expected).all():
        raise ValueError("is_canceled does not reconcile to final reservation status.")

    df["failed_room_nights"] = df["total_nights"] * df["non_materialized"]
    df["lead_time_band"] = pd.cut(
        df["lead_time"], bins=LEAD_BINS, labels=LEAD_LABELS
    )
    df["cancel_lead_days"] = np.where(
        df["explicit_cancellation"].eq(1),
        (df["arrival_date"] - df["reservation_status_date"]).dt.days,
        np.nan,
    )
    return df


def standardized_rate(df: pd.DataFrame, segment: str, weights: pd.Series) -> float:
    rates = (
        df[df["market_segment"].eq(segment)]
        .groupby("lead_time_band", observed=True)["non_materialized"]
        .mean()
        .reindex(LEAD_LABELS)
    )
    valid = rates.notna() & weights.gt(0)
    w = weights[valid] / weights[valid].sum()
    return float((rates[valid] * w).sum())


def summarize(df: pd.DataFrame) -> dict:
    nd = df[df["deposit_type"].eq("No Deposit")].copy()
    online = nd[nd["market_segment"].eq("Online TA")]

    combined = nd[nd["market_segment"].isin(["Online TA", "Direct"])]
    weights = (
        combined["lead_time_band"]
        .value_counts(normalize=True)
        .reindex(LEAD_LABELS, fill_value=0)
    )

    core = nd[
        nd["market_segment"].eq("Online TA")
        & nd["arrival_date_year"].isin([2016, 2017])
        & nd["arrival_date"].dt.month.le(8)
    ]

    long_ota = online[online["lead_time"].ge(91)]
    failed_long_ota = long_ota[long_ota["non_materialized"].eq(1)]
    early_long_ota = failed_long_ota[
        failed_long_ota["explicit_cancellation"].eq(1)
        & failed_long_ota["cancel_lead_days"].gt(30)
    ]

    nd_failed = nd[nd["non_materialized"].eq(1)]
    nd_early = nd_failed[
        nd_failed["explicit_cancellation"].eq(1)
        & nd_failed["cancel_lead_days"].gt(30)
    ]
    nd_late = nd_failed[
        nd_failed["no_show"].eq(1)
        | (
            nd_failed["explicit_cancellation"].eq(1)
            & nd_failed["cancel_lead_days"].le(7)
        )
    ]

    year_stats = {}
    for year in [2016, 2017]:
        x = core[core["arrival_date_year"].eq(year)]
        year_stats[year] = {
            "bookings": int(len(x)),
            "non_materialization_rate": float(x["non_materialized"].mean()),
            "failed_room_nights": int(x["failed_room_nights"].sum()),
        }

    return {
        "bookings": len(df),
        "overall_non_materialization_rate": df["non_materialized"].mean(),
        "no_deposit_bookings": len(nd),
        "no_deposit_share": len(nd) / len(df),
        "no_deposit_non_materialization_rate": nd["non_materialized"].mean(),
        "no_deposit_failed_room_nights": int(nd["failed_room_nights"].sum()),
        "online_ta_share_of_no_deposit_bookings": len(online) / len(nd),
        "online_ta_share_of_no_deposit_failed_room_nights": (
            online["failed_room_nights"].sum() / nd["failed_room_nights"].sum()
        ),
        "standardized_online_ta_rate": standardized_rate(nd, "Online TA", weights),
        "standardized_direct_rate": standardized_rate(nd, "Direct", weights),
        "long_lead_online_ta_bookings": len(long_ota),
        "long_lead_online_ta_rate": long_ota["non_materialized"].mean(),
        "long_lead_online_ta_failed_room_nights": int(long_ota["failed_room_nights"].sum()),
        "long_lead_online_ta_failed_room_night_share": (
            long_ota["failed_room_nights"].sum() / nd["failed_room_nights"].sum()
        ),
        "long_lead_online_ta_early_cancellation_share": (
            early_long_ota["failed_room_nights"].sum()
            / failed_long_ota["failed_room_nights"].sum()
        ),
        "no_deposit_early_cancellation_share": (
            nd_early["failed_room_nights"].sum() / nd_failed["failed_room_nights"].sum()
        ),
        "no_deposit_late_leakage_share": (
            nd_late["failed_room_nights"].sum() / nd_failed["failed_room_nights"].sum()
        ),
        "core_2016": year_stats[2016],
        "core_2017": year_stats[2017],
    }


if __name__ == "__main__":
    result = summarize(load_h2())
    for key, value in result.items():
        print(f"{key}: {value}")
