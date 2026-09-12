import pandas as pd

from src.universe import build_equity_universe, load_symbol_list


def test_user_symbols_are_normalized_and_restricted_to_cash_equity_master():
    cash = pd.DataFrame([["NSE:RELIANCE-EQ"], ["NSE:TCS-EQ"], ["NSE:INFY-EQ"]])

    result = build_equity_universe(cash, ["reliance", "NSE:INFY-EQ", "UNKNOWN"])

    assert result["symbol"].tolist() == ["NSE:INFY-EQ", "NSE:RELIANCE-EQ"]


def test_load_symbol_list_supports_comma_separated_file(tmp_path):
    symbol_file = tmp_path / "stocks.txt"
    symbol_file.write_text("NSE:RELIANCE-EQ,NSE:TCS-EQ\nNSE:INFY-EQ", encoding="utf-8")

    assert load_symbol_list(symbol_file) == ["NSE:RELIANCE-EQ", "NSE:TCS-EQ", "NSE:INFY-EQ"]