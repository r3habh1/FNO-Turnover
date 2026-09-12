"""Build a deduplicated equity universe from Fyers symbol masters."""

from __future__ import annotations

from pathlib import Path

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