from datetime import date, datetime, timedelta

import pandas as pd

from src.analytics import aggregate_candles, rank_top_stocks, session_buckets


def _rows(symbol: str, prices: list[float], volume: float = 100) -> list[dict[str, object]]:
    return [
        {
            "symbol": symbol,
            "timestamp": datetime(2026, 1, 5, 9, 15) + timedelta(minutes=index),
            "open": price,
            "high": price + 1,
            "low": price - 1,
            "close": price,
            "volume": volume,
        }
        for index, price in enumerate(prices)
    ]


def test_55_minute_buckets_start_at_0915_and_end_at_session_close():
    buckets = session_buckets(date(2026, 1, 5), 55)

    assert buckets.iloc[0]["bucket_start"].strftime("%H:%M") == "09:15"
    assert buckets.iloc[0]["bucket_end"].strftime("%H:%M") == "10:10"
    assert buckets.iloc[-1]["bucket_start"].strftime("%H:%M") == "14:45"
    assert buckets.iloc[-1]["bucket_end"].strftime("%H:%M") == "15:30"
    assert bool(buckets.iloc[-1]["is_partial"])


def test_requested_intervals_keep_session_anchor_and_short_final_bucket():
    for interval in (15, 25, 75, 125):
        buckets = session_buckets(date(2026, 1, 5), interval)
        assert buckets.iloc[0]["bucket_start"].strftime("%H:%M") == "09:15"
        assert buckets.iloc[-1]["bucket_end"].strftime("%H:%M") == "15:30"


def test_aggregation_calculates_vwap_turnover_and_completeness():
    data = pd.DataFrame(_rows("AAA", [100, 110, 120]))

    result = aggregate_candles(data, 15)

    assert result.iloc[0]["volume"] == 300
    assert result.iloc[0]["vwap"] == 110
    assert result.iloc[0]["turnover"] == 33000
    assert not result.iloc[0]["is_complete"]


def test_ranking_returns_three_stocks_and_breaks_ties_by_symbol():
    data = pd.DataFrame(
        _rows("CCC", [100], 100)
        + _rows("AAA", [100], 100)
        + _rows("BBB", [100], 100)
        + _rows("DDD", [100], 100)
    )

    result = rank_top_stocks(aggregate_candles(data, 15))

    assert result["symbol"].tolist() == ["AAA", "BBB", "CCC"]
    assert result["rank"].tolist() == [1, 2, 3]