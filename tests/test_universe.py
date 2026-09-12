import pandas as pd
from datetime import date, datetime, timezone

from src.universe import (
    build_equity_universe,
    build_option_universe,
    load_symbol_list,
    month_end_tuesday,
    option_expiries_for_underlyings,
    parse_expiry_input,
    resolve_option_expiry,
)


def test_user_symbols_are_normalized_and_restricted_to_cash_equity_master():
    cash = pd.DataFrame([["NSE:RELIANCE-EQ"], ["NSE:TCS-EQ"], ["NSE:INFY-EQ"]])

    result = build_equity_universe(cash, ["reliance", "NSE:INFY-EQ", "UNKNOWN"])

    assert result["symbol"].tolist() == ["NSE:INFY-EQ", "NSE:RELIANCE-EQ"]


def test_load_symbol_list_supports_comma_separated_file(tmp_path):
    symbol_file = tmp_path / "stocks.txt"
    symbol_file.write_text("NSE:RELIANCE-EQ,NSE:TCS-EQ\nNSE:INFY-EQ", encoding="utf-8")

    assert load_symbol_list(symbol_file) == ["NSE:RELIANCE-EQ", "NSE:TCS-EQ", "NSE:INFY-EQ"]


def test_parse_expiry_input_supports_short_month_text():
    assert parse_expiry_input("26sep", today=date(2026, 9, 12)) == date(2026, 9, 26)
    assert parse_expiry_input("26sep27", today=date(2026, 9, 12)) == date(2027, 9, 26)


def test_month_end_tuesday_returns_last_tuesday_of_month():
    assert month_end_tuesday(date(2026, 9, 11)) == date(2026, 9, 29)
    assert month_end_tuesday(date(2026, 10, 1)) == date(2026, 10, 27)


def test_build_option_universe_selects_atm_plus_minus_one_strike():
    expiry_epoch = int(datetime(2026, 9, 26, tzinfo=timezone.utc).timestamp())
    rows = []
    for strike in (2480, 2500, 2520, 2540):
        for option_type in ("CE", "PE"):
            rows.append(
                {
                    "symTicker": f"NSE:RELIANCE26SEP26{int(strike)}{option_type}",
                    "exSymName": "RELIANCE",
                    "optType": option_type,
                    "strikePrice": strike,
                    "expiryDate": expiry_epoch,
                }
            )
    fo_master = pd.DataFrame(rows)

    result = build_option_universe(
        fo_master,
        {"RELIANCE": 2512},
        date(2026, 9, 26),
    )

    assert result["strike"].tolist() == [2500, 2500, 2520, 2520, 2540, 2540]
    assert result["strike_offset"].tolist() == [-1, -1, 0, 0, 1, 1]
    assert set(result["option_type"]) == {"CE", "PE"}


def test_resolve_option_expiry_uses_same_month_available_expiry():
    expiry_epoch = int(datetime(2026, 9, 29, tzinfo=timezone.utc).timestamp())
    fo_master = pd.DataFrame(
        [
            {
                "symTicker": "NSE:RELIANCE26SEP2500CE",
                "exSymName": "RELIANCE26SEP2500CE",
                "underSym": "RELIANCE",
                "optType": "CE",
                "strikePrice": 2500,
                "expiryDate": expiry_epoch,
            }
        ]
    )

    result = resolve_option_expiry(fo_master, ["RELIANCE"], date(2026, 9, 26))

    assert result == date(2026, 9, 29)


def test_option_expiries_for_underlyings_filters_selected_stocks():
    reliance_expiry = int(datetime(2026, 9, 29, tzinfo=timezone.utc).timestamp())
    tcs_expiry = int(datetime(2026, 10, 27, tzinfo=timezone.utc).timestamp())
    fo_master = pd.DataFrame(
        [
            {
                "symTicker": "NSE:RELIANCE26SEP2500CE",
                "underSym": "RELIANCE",
                "optType": "CE",
                "strikePrice": 2500,
                "expiryDate": reliance_expiry,
            },
            {
                "symTicker": "NSE:TCS26OCT3000CE",
                "underSym": "TCS",
                "optType": "CE",
                "strikePrice": 3000,
                "expiryDate": tcs_expiry,
            },
        ]
    )

    result = option_expiries_for_underlyings(fo_master, ["RELIANCE"])

    assert result == [date(2026, 9, 29)]
