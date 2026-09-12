from datetime import date

import pandas as pd

from src.history_store import clear_all_downloads, load_state, save_symbol_result


def test_history_store_persists_success_and_failure(tmp_path, monkeypatch):
    monkeypatch.setattr("src.history_store.DATA_DIR", tmp_path)
    start = date(2026, 1, 1)
    end = date(2026, 1, 7)
    frame = pd.DataFrame(
        [{"symbol": "NSE:AAA-EQ", "timestamp": "2026-01-01 09:15", "open": 1, "high": 2, "low": 1, "close": 2, "volume": 10}]
    )

    save_symbol_result(start, end, "NSE:AAA-EQ", frame, None)
    save_symbol_result(start, end, "NSE:BBB-EQ", None, "API error")

    state = load_state(start, end)
    assert state.completed_symbols == {"NSE:AAA-EQ"}
    assert state.failed_symbols == {"NSE:BBB-EQ": "API error"}
    assert state.frame["symbol"].tolist() == ["NSE:AAA-EQ"]


def test_clear_all_downloads_removes_all_date_ranges(tmp_path, monkeypatch):
    monkeypatch.setattr("src.history_store.DATA_DIR", tmp_path)
    save_symbol_result(date(2026, 1, 1), date(2026, 1, 7), "NSE:AAA-EQ", None, "error")
    save_symbol_result(date(2026, 2, 1), date(2026, 2, 7), "NSE:BBB-EQ", None, "error")

    deleted = clear_all_downloads()

    assert deleted == 2
    assert list(tmp_path.iterdir()) == []


def test_history_store_separates_namespaces(tmp_path, monkeypatch):
    monkeypatch.setattr("src.history_store.DATA_DIR", tmp_path)
    start = end = date(2026, 1, 1)
    equity = pd.DataFrame(
        [{"symbol": "NSE:AAA-EQ", "timestamp": "2026-01-01 09:15", "open": 1, "high": 1, "low": 1, "close": 1, "volume": 1}]
    )
    option = pd.DataFrame(
        [{"symbol": "NSE:AAAOPT", "timestamp": "2026-01-01 09:15", "open": 2, "high": 2, "low": 2, "close": 2, "volume": 2}]
    )

    save_symbol_result(start, end, "NSE:AAA-EQ", equity, None)
    save_symbol_result(start, end, "NSE:AAAOPT", option, None, namespace="options_20260101")

    assert load_state(start, end).frame["symbol"].tolist() == ["NSE:AAA-EQ"]
    assert load_state(start, end, namespace="options_20260101").frame["symbol"].tolist() == ["NSE:AAAOPT"]
