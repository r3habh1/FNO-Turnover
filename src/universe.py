"""Build a deduplicated equity universe from Fyers symbol masters."""

from __future__ import annotations

from calendar import monthrange
from pathlib import Path
from datetime import UTC, date, datetime

import pandas as pd


def _columns(frame: pd.DataFrame) -> pd.DataFrame:
    result = frame.copy()
    result.columns = [str(column).strip().lower() for column in result.columns]
    return result


def _find_column(frame: pd.DataFrame, candidates: tuple[str, ...]) -> str | None:
    named = next((candidate for candidate in candidates if candidate in frame.columns), None)
    if named:
        return named
    for column in frame.columns:
        values = frame[column].astype(str).str.upper()
        if values.str.contains(r"NSE:", regex=True).any():
            return column
    return None


def _normalise_equity_symbol(value: str) -> str:
    symbol = str(value).strip().upper()
    if symbol.startswith("NSE:"):
        symbol = symbol[4:]
    if symbol.endswith("-EQ"):
        symbol = symbol[:-3]
    return f"NSE:{symbol}-EQ"


def load_symbol_list(path: str | Path) -> list[str]:
    """Read comma- or newline-separated equity symbols from a text file."""
    contents = Path(path).read_text(encoding="utf-8")
    return [value.strip().upper() for value in contents.replace("\n", ",").split(",") if value.strip()]


def build_equity_universe(
    cash_master: pd.DataFrame,
    requested_symbols: list[str] | None = None,
) -> pd.DataFrame:
    """Return NSE cash-equity symbols, optionally restricted by user input."""
    cash = _columns(cash_master)
    cash_symbol_column = _find_column(cash, ("symbol", "trading_symbol", "ticker"))
    if not cash_symbol_column:
        raise ValueError("Cash master data must include a symbol column")

    cash_symbols = cash[cash_symbol_column].astype(str).str.upper().str.strip()
    available_symbols = {
        _normalise_equity_symbol(symbol)
        for symbol in cash_symbols
        if symbol.startswith("NSE:") and symbol.endswith("-EQ")
    }
    if requested_symbols is None:
        symbols = sorted(available_symbols)
    else:
        requested = {_normalise_equity_symbol(symbol) for symbol in requested_symbols if str(symbol).strip()}
        symbols = sorted(requested.intersection(available_symbols))
    return pd.DataFrame({"symbol": symbols})


def _expiry_date(value: object) -> date | None:
    if value in (None, "") or pd.isna(value):
        return None
    try:
        return datetime.fromtimestamp(int(float(value)), UTC).date()
    except (TypeError, ValueError, OverflowError):
        parsed = pd.to_datetime(value, errors="coerce", dayfirst=True)
        if pd.isna(parsed):
            return None
        return parsed.date()


def parse_expiry_input(value: str, today: date | None = None) -> date:
    """Parse sidebar expiry text such as 26sep, 26sep26, or 2026-09-26."""
    current = today or date.today()
    text = value.strip()
    for fmt in ("%Y-%m-%d", "%d-%m-%Y", "%d/%m/%Y", "%d%b%y", "%d%b%Y"):
        try:
            parsed = datetime.strptime(text, fmt)
        except ValueError:
            continue
        return parsed.date()
    try:
        parsed_without_year = datetime.strptime(f"{text}{current.year}", "%d%b%Y")
    except ValueError:
        pass
    else:
        result = date(current.year, parsed_without_year.month, parsed_without_year.day)
        if result < current:
            result = date(current.year + 1, parsed_without_year.month, parsed_without_year.day)
        return result
    raise ValueError("Use expiry like 26sep or 2026-09-26")


def month_end_tuesday(value: date) -> date:
    """Return the last Tuesday of value's calendar month."""
    last_day = date(value.year, value.month, monthrange(value.year, value.month)[1])
    while last_day.weekday() != 1:
        last_day = date(last_day.year, last_day.month, last_day.day - 1)
    return last_day


def _normalise_option_rows(fo_master: pd.DataFrame) -> pd.DataFrame:
    required = {"symTicker", "optType", "strikePrice", "expiryDate"}
    missing = required.difference(fo_master.columns)
    if missing:
        raise ValueError(f"FO master data must include: {', '.join(sorted(missing))}")

    rows = fo_master.copy()
    rows["option_symbol"] = rows["symTicker"].astype(str).str.upper().str.strip()
    rows["option_type"] = rows["optType"].astype(str).str.upper().str.strip()
    rows["strike"] = pd.to_numeric(rows["strikePrice"], errors="coerce")
    rows["expiry"] = rows["expiryDate"].map(_expiry_date)
    rows["underlying"] = rows.apply(_option_underlying, axis=1)
    return rows[
        rows["option_symbol"].str.startswith("NSE:")
        & rows["option_type"].isin(["CE", "PE"])
        & rows["strike"].notna()
        & (rows["strike"] >= 0)
        & rows["expiry"].notna()
    ].copy()


def _option_underlying(row: pd.Series) -> str:
    for column in ("underSym", "underlyingSymbol", "baseSym", "exSymName"):
        if column in row and not pd.isna(row[column]):
            value = str(row[column]).strip().upper()
            if value:
                return value
    symbol = str(row.get("symTicker", "")).upper()
    if symbol.startswith("NSE:"):
        symbol = symbol[4:]
    letters = []
    for char in symbol:
        if char.isalpha():
            letters.append(char)
        else:
            break
    return "".join(letters)


def resolve_option_expiry(
    fo_master: pd.DataFrame,
    underlyings: list[str],
    requested_expiry: date,
) -> date | None:
    """Return the exact or same-month available expiry for selected underlyings."""
    rows = _normalise_option_rows(fo_master)
    if rows.empty:
        return None
    tickers = {str(value).upper().replace("NSE:", "").removesuffix("-EQ") for value in underlyings}
    rows = rows[rows["underlying"].isin(tickers)]
    if rows.empty:
        return None
    expiries = sorted(rows["expiry"].dropna().unique())
    if requested_expiry in expiries:
        return requested_expiry
    month_matches = [
        expiry for expiry in expiries
        if expiry.year == requested_expiry.year and expiry.month == requested_expiry.month
    ]
    if month_matches:
        return min(month_matches, key=lambda expiry: abs((expiry - requested_expiry).days))
    future_expiries = [expiry for expiry in expiries if expiry >= requested_expiry]
    return future_expiries[0] if future_expiries else expiries[-1]


def option_expiries_for_underlyings(fo_master: pd.DataFrame, underlyings: list[str]) -> list[date]:
    """Return available option expiry dates for selected underlyings."""
    rows = _normalise_option_rows(fo_master)
    if rows.empty:
        return []
    tickers = {str(value).upper().replace("NSE:", "").removesuffix("-EQ") for value in underlyings}
    rows = rows[rows["underlying"].isin(tickers)]
    return sorted(rows["expiry"].dropna().unique())


def build_option_universe(
    fo_master: pd.DataFrame,
    underlying_ltp: dict[str, float],
    expiry: date,
    strikes_around: int = 1,
) -> pd.DataFrame:
    """Return CE/PE option symbols at ATM +/- N strikes for each underlying."""
    if fo_master.empty or not underlying_ltp:
        return pd.DataFrame()
    rows = _normalise_option_rows(fo_master)
    rows = rows[rows["expiry"] == expiry].copy()
    if rows.empty:
        return pd.DataFrame()

    selected: list[pd.DataFrame] = []
    for underlying, ltp in underlying_ltp.items():
        ticker = str(underlying).upper().replace("NSE:", "").removesuffix("-EQ")
        group = rows[rows["underlying"] == ticker].copy()
        if group.empty:
            group = rows[rows["option_symbol"].str.startswith(f"NSE:{ticker}")]
        if group.empty:
            continue
        strikes = sorted(group["strike"].dropna().unique())
        if not strikes:
            continue
        atm_index = min(range(len(strikes)), key=lambda index: abs(strikes[index] - float(ltp)))
        lower = max(0, atm_index - strikes_around)
        upper = min(len(strikes), atm_index + strikes_around + 1)
        strike_offsets = {strike: index - atm_index for index, strike in enumerate(strikes[lower:upper], start=lower)}
        subset = group[group["strike"].isin(list(strike_offsets))].copy()
        subset["underlying"] = ticker
        subset["underlying_ltp"] = float(ltp)
        subset["atm_strike"] = strikes[atm_index]
        subset["strike_offset"] = subset["strike"].map(strike_offsets)
        selected.append(subset)

    if not selected:
        return pd.DataFrame()
    result = pd.concat(selected, ignore_index=True)
    return result[
        [
            "underlying", "underlying_ltp", "atm_strike", "strike_offset",
            "strike", "option_type", "option_symbol", "expiry",
        ]
    ].sort_values(["underlying", "strike", "option_type"]).reset_index(drop=True)
