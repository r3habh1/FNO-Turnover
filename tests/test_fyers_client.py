from datetime import date

import pandas as pd

from src.fyers_client import FyersClient, FyersRateLimitError
from src.config import Settings


def test_empty_history_is_reported_as_symbol_failure():
    client = FyersClient(Settings("id", "secret", "http://localhost"))
    client.history = lambda symbol, start, end, resolution: __import__("pandas").DataFrame()
    progress = []

    result = client.history_for_symbols(
        ["NSE:RELIANCE-EQ"],
        date(2026, 1, 1),
        date(2026, 1, 7),
        progress_callback=lambda completed, total, symbol, frame, error: progress.append((symbol, frame, error)),
    )

    assert result.empty
    assert progress[0][0] == "NSE:RELIANCE-EQ"
    assert progress[0][1] is None
    assert "No 5-minute candles" in progress[0][2]


def test_history_sends_documented_fyers_request_types():
    client = FyersClient(Settings("id", "secret", "http://localhost"))
    requests = []

    class FakeModel:
        def history(self, payload):
            requests.append(payload)
            return {"s": "ok", "candles": []}

    client._model = FakeModel()
    client.history("NSE:RELIANCE-EQ", date(2026, 9, 8), date(2026, 9, 8), resolution="5")

    assert requests == [{
        "symbol": "NSE:RELIANCE-EQ",
        "resolution": "5",
        "date_format": 1,
        "range_from": "2026-09-08",
        "range_to": "2026-09-08",
        "cont_flag": 1,
    }]


def test_history_for_symbols_callback_contains_symbol_column():
    client = FyersClient(Settings("id", "secret", "http://localhost"))
    client.history = lambda symbol, start, end, resolution: pd.DataFrame(
        [[0, 1, 2, 0.5, 1.5, 10]],
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )
    callbacks = []

    client.history_for_symbols(
        ["NSE:RELIANCE-EQ"],
        date(2026, 1, 1),
        date(2026, 1, 1),
        progress_callback=lambda completed, total, symbol, frame, error: callbacks.append(frame),
    )

    assert callbacks[0]["symbol"].tolist() == ["NSE:RELIANCE-EQ"]


def test_history_for_symbols_retries_rate_limit_then_succeeds(monkeypatch):
    client = FyersClient(Settings("id", "secret", "http://localhost"))
    attempts = []
    frame = pd.DataFrame(
        [[0, 1, 2, 0.5, 1.5, 10]],
        columns=["timestamp", "open", "high", "low", "close", "volume"],
    )

    def fake_history(symbol, start, end, resolution):
        attempts.append(symbol)
        if len(attempts) < 3:
            raise FyersRateLimitError("Fyers history failed (429): request limit reached")
        return frame

    monkeypatch.setattr(client, "history", fake_history)
    monkeypatch.setattr("src.fyers_client.time.sleep", lambda seconds: None)

    result = client.history_for_symbols(["NSE:RELIANCE-EQ"], date(2026, 1, 1), date(2026, 1, 1))

    assert len(attempts) == 3
    assert result["symbol"].tolist() == ["NSE:RELIANCE-EQ"]