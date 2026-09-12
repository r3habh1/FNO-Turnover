"""Intraday candle aggregation and turnover ranking."""

from __future__ import annotations

from datetime import date, datetime, time

import pandas as pd

SESSION_START = time(9, 15)
SESSION_END = time(15, 30)
LOCAL_TIMEZONE = "Asia/Kolkata"


def session_buckets(trading_date: date, interval_minutes: int) -> pd.DataFrame:
    """Return the regular NSE session buckets anchored at 09:15."""
    if interval_minutes <= 0:
        raise ValueError("interval_minutes must be positive")

    session_start = pd.Timestamp(datetime.combine(trading_date, SESSION_START), tz=LOCAL_TIMEZONE)
    session_end = pd.Timestamp(datetime.combine(trading_date, SESSION_END), tz=LOCAL_TIMEZONE)
    buckets: list[dict[str, object]] = []
    bucket_start = session_start
    bucket_number = 0
    while bucket_start < session_end:
        bucket_end = min(bucket_start + pd.Timedelta(minutes=interval_minutes), session_end)
        buckets.append(
            {
                "trading_date": trading_date,
                "bucket_number": bucket_number,
                "bucket_start": bucket_start,
                "bucket_end": bucket_end,
                "expected_minutes": int((bucket_end - bucket_start).total_seconds() // 60),
                "is_partial": (bucket_end - bucket_start) != pd.Timedelta(minutes=interval_minutes),
            }
        )
        bucket_start = bucket_end
        bucket_number += 1
    return pd.DataFrame(buckets)


def _normalise_input(data: pd.DataFrame) -> pd.DataFrame:
    required = {"symbol", "timestamp", "open", "high", "low", "close", "volume"}
    missing = required.difference(data.columns)
    if missing:
        raise ValueError(f"Missing required columns: {', '.join(sorted(missing))}")

    result = data.copy()
    timestamps = pd.to_datetime(result["timestamp"], errors="coerce")
    if timestamps.dt.tz is None:
        timestamps = timestamps.dt.tz_localize(LOCAL_TIMEZONE)
    else:
        timestamps = timestamps.dt.tz_convert(LOCAL_TIMEZONE)
    result["timestamp"] = timestamps
    result["volume"] = pd.to_numeric(result["volume"], errors="coerce")
    for column in ("open", "high", "low", "close"):
        result[column] = pd.to_numeric(result[column], errors="coerce")
    return result.dropna(subset=["symbol", "timestamp", "high", "low", "close", "volume"])


def aggregate_candles(data: pd.DataFrame, interval_minutes: int) -> pd.DataFrame:
    """Aggregate minute OHLCV data into session-anchored candles."""
    normalised = _normalise_input(data)
    if normalised.empty:
        return pd.DataFrame()

    normalised["trading_date"] = normalised["timestamp"].dt.date
    normalised = normalised[
        (normalised["timestamp"].dt.time >= SESSION_START)
        & (normalised["timestamp"].dt.time < SESSION_END)
    ].copy()
    if normalised.empty:
        return pd.DataFrame()

    normalised["bucket_number"] = normalised.apply(
        lambda row: int(
            (row["timestamp"] - pd.Timestamp(datetime.combine(row["trading_date"], SESSION_START), tz=LOCAL_TIMEZONE))
            / pd.Timedelta(minutes=interval_minutes)
        ),
        axis=1,
    )
    normalised["typical_value"] = (normalised["high"] + normalised["low"] + normalised["close"]) / 3

    grouped = normalised.groupby(["trading_date", "symbol", "bucket_number"], sort=True)
    candles = grouped.agg(
        open=("open", "first"),
        high=("high", "max"),
        low=("low", "min"),
        close=("close", "last"),
        volume=("volume", "sum"),
        minute_count=("timestamp", "nunique"),
    ).reset_index()
    weighted = grouped.apply(
        lambda frame: (frame["typical_value"] * frame["volume"]).sum(),
        include_groups=False,
    ).rename("weighted_typical_value")
    candles = candles.merge(
        weighted.reset_index(), on=["trading_date", "symbol", "bucket_number"]
    )
    metadata = pd.concat(
        [session_buckets(trading_date, interval_minutes) for trading_date in candles["trading_date"].unique()],
        ignore_index=True,
    )
    candles = candles.merge(metadata, on=["trading_date", "bucket_number"], how="left")
    candles["vwap"] = candles["weighted_typical_value"].div(candles["volume"].where(candles["volume"] != 0))
    candles["turnover"] = candles["volume"] * candles["vwap"]
    candles["is_complete"] = candles["minute_count"] >= candles["expected_minutes"]
    return candles.drop(columns="weighted_typical_value").sort_values(
        ["trading_date", "bucket_number", "symbol"]
    ).reset_index(drop=True)


def rank_top_stocks(candles: pd.DataFrame, limit: int = 3) -> pd.DataFrame:
    """Return the highest-turnover stocks per date and candle."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    if candles.empty:
        return candles.copy()
    ranked = candles[candles["volume"] > 0].copy()
    ranked = ranked.sort_values(
        ["trading_date", "bucket_number", "turnover", "symbol"],
        ascending=[True, True, False, True],
    )
    ranked["rank"] = ranked.groupby(["trading_date", "bucket_number"], sort=False).cumcount() + 1
    return ranked[ranked["rank"] <= limit].reset_index(drop=True)


def aggregate_option_turnover(data: pd.DataFrame, interval_minutes: int = 5, limit: int = 5) -> pd.DataFrame:
    """Aggregate option candles and rank turnover as volume * close."""
    if limit <= 0:
        raise ValueError("limit must be positive")
    candles = aggregate_candles(data, interval_minutes)
    if candles.empty:
        return candles.copy()
    candles = candles[candles["volume"] > 0].copy()
    candles["price"] = candles["close"]
    candles["turnover"] = candles["volume"] * candles["price"]
    candles = candles.sort_values(
        ["trading_date", "bucket_number", "turnover", "symbol"],
        ascending=[True, True, False, True],
    )
    candles["rank"] = candles.groupby(["trading_date", "bucket_number"], sort=False).cumcount() + 1
    return candles[candles["rank"] <= limit].reset_index(drop=True)
