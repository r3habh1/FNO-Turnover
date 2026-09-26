"""Financial-year normalized price-path analysis for the current Nifty 500 universe."""

from __future__ import annotations

from datetime import date
import pandas as pd


def completed_financial_years(end_date: date | None = None, years: int = 10) -> list[tuple[str, date, date]]:
    """Return the latest completed Indian financial years, oldest first."""
    if years <= 0:
        raise ValueError("years must be positive")
    end_date = end_date or date.today()
    last_fy_end_year = end_date.year if (end_date.month, end_date.day) >= (3, 31) else end_date.year - 1
    # If today is after 31 March, that FY is complete.
    first_end_year = last_fy_end_year - years + 1
    return [
        (
            f"FY{end_year - 1}-{str(end_year)[-2:]}",
            date(end_year - 1, 4, 1),
            date(end_year, 3, 31),
        )
        for end_year in range(first_end_year, last_end_year + 1)
    ]


def load_current_nifty500(path: str) -> pd.DataFrame:
    """Load and validate the user-supplied current Nifty 500 constituent CSV."""
    frame = pd.read_csv(path)
    required = {"Company Name", "Industry", "Symbol", "Series", "ISIN Code"}
    missing = required.difference(frame.columns)
    if missing:
        raise ValueError(f"Nifty 500 CSV is missing columns: {', '.join(sorted(missing))}")
    frame = frame.copy()
    frame["Symbol"] = frame["Symbol"].astype(str).str.strip().str.upper()
    frame = frame[frame["Symbol"].ne("")].drop_duplicates("Symbol").reset_index(drop=True)
    return frame


def normalize_fy_paths(
    daily_data: pd.DataFrame,
    years: list[tuple[str, date, date]],
) -> pd.DataFrame:
    """Convert daily closes into one normalized 0%-based path per financial year."""
    required = {"symbol", "timestamp", "close"}
    missing = required.difference(daily_data.columns)
    if missing:
        raise ValueError(f"Daily data is missing columns: {', '.join(sorted(missing))}")

    frame = daily_data.copy()
    frame["symbol"] = (
        frame["symbol"].astype(str).str.upper()
        .str.replace("NSE:", "", regex=False)
        .str.removesuffix("-EQ")
    )
    timestamps = pd.to_datetime(frame["timestamp"], errors="coerce")
    if timestamps.dt.tz is not None:
        timestamps = timestamps.dt.tz_convert("Asia/Kolkata").dt.tz_localize(None)
    frame["timestamp"] = timestamps
    frame["close"] = pd.to_numeric(frame["close"], errors="coerce")
    frame = frame.dropna(subset=["symbol", "timestamp", "close"])
    frame = frame.sort_values(["symbol", "timestamp"]).drop_duplicates(
        ["symbol", "timestamp"], keep="last"
    )

    output: list[pd.DataFrame] = []
    for label, start, end in years:
        period = frame[
            (frame["timestamp"].dt.date >= start)
            & (frame["timestamp"].dt.date <= end)
        ].copy()
        if period.empty:
            continue
        period["fy"] = label
        period["fy_day"] = period.groupby("symbol").cumcount() + 1
        first_close = period.groupby("symbol")["close"].transform("first")
        period["return_pct"] = (period["close"] / first_close - 1.0) * 100.0
        period["calendar_date"] = period["timestamp"].dt.strftime("%d %b")
        output.append(
            period[["symbol", "fy", "fy_day", "timestamp", "calendar_date", "close", "return_pct"]]
        )

    if not output:
        return pd.DataFrame(
            columns=["symbol", "fy", "fy_day", "timestamp", "calendar_date", "close", "return_pct"]
        )
    return pd.concat(output, ignore_index=True)


def stock_path(paths: pd.DataFrame, symbol: str, include_median: bool = True) -> pd.DataFrame:
    """Build a wide chart dataframe with one column per FY path."""
    selected = paths[paths["symbol"].eq(symbol)].copy()
    if selected.empty:
        return pd.DataFrame(columns=["FY Day"])

    wide = selected.pivot_table(
        index="fy_day",
        columns="fy",
        values="return_pct",
        aggfunc="last",
    ).sort_index()
    wide.index.name = "FY Day"
    if include_median:
        wide["Median"] = wide.median(axis=1, skipna=True)
    wide.reset_index(inplace=True)
    return wide


def stock_summary(paths: pd.DataFrame, symbol: str) -> pd.DataFrame:
    """Return one row per financial year with endpoint and path statistics."""
    selected = paths[paths["symbol"].eq(symbol)].copy()
    if selected.empty:
        return pd.DataFrame()

    rows = []
    for fy, group in selected.groupby("fy", sort=False):
        group = group.sort_values("fy_day")
        returns = group["return_pct"]
        rows.append(
            {
                "FY": fy,
                "Trading Days": len(group),
                "FY Return %": float(returns.iloc[-1]),
                "Best %": float(returns.max()),
                "Worst %": float(returns.min()),
                "Positive": bool(returns.iloc[-1] >= 0),
            }
        )
    return pd.DataFrame(rows)


def cross_stock_snapshot(paths: pd.DataFrame) -> pd.DataFrame:
    """Create current-universe statistics useful for screening later."""
    if paths.empty:
        return pd.DataFrame()
    rows = []
    for symbol, group in paths.groupby("symbol"):
        year_end = group.sort_values("fy_day").groupby("fy").tail(1)
        rows.append(
            {
                "Symbol": symbol,
                "Years Available": year_end["fy"].nunique(),
                "Positive FYs": int((year_end["return_pct"] >= 0).sum()),
                "Positive FY %": float((year_end["return_pct"] >= 0).mean() * 100),
                "Average FY Return %": float(year_end["return_pct"].mean()),
                "Median FY Return %": float(year_end["return_pct"].median()),
            }
        )
    return pd.DataFrame(rows).sort_values(
        ["Positive FY %", "Median FY Return %", "Average FY Return %"],
        ascending=[False, False, False],
    ).reset_index(drop=True)
