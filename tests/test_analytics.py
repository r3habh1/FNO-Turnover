from datetime import date, datetime, timedelta

import pandas as pd

from src.analytics import aggregate_candles, aggregate_option_turnover, rank_top_stocks, session_buckets


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


def test_option_turnover_uses_volume_times_close_price():
    data = pd.DataFrame(
        [
            {
                "symbol": "NSE:AAAOPT",
                "timestamp": datetime(2026, 1, 5, 9, 15),
                "open": 10,
                "high": 30,
                "low": 10,
                "close": 20,
                "volume": 100,
            },
            {
                "symbol": "NSE:BBBOPT",
                "timestamp": datetime(2026, 1, 5, 9, 15),
                "open": 10,
                "high": 10,
                "low": 10,
                "close": 15,
                "volume": 120,
            },
            {
                "symbol": "NSE:CCCOPT",
                "timestamp": datetime(2026, 1, 5, 9, 15),
                "open": 10,
                "high": 10,
                "low": 10,
                "close": 10,
                "volume": 100,
            },
            {
                "symbol": "NSE:DDDOPT",
                "timestamp": datetime(2026, 1, 5, 9, 15),
                "open": 10,
                "high": 10,
                "low": 10,
                "close": 5,
                "volume": 100,
            },
        ]
    )

    result = aggregate_option_turnover(data)

    assert result["symbol"].tolist() == ["NSE:AAAOPT", "NSE:BBBOPT", "NSE:CCCOPT", "NSE:DDDOPT"]
    assert result["turnover"].tolist() == [2000, 1800, 1000, 500]
    assert result["rank"].tolist() == [1, 2, 3, 4]


def test_option_turnover_can_display_selected_timeframe_from_5_minute_data():
    data = pd.DataFrame(
        [
            {
                "symbol": "NSE:AAAOPT",
                "timestamp": datetime(2026, 1, 5, 9, 15),
                "open": 10,
                "high": 12,
                "low": 9,
                "close": 10,
                "volume": 100,
            },
            {
                "symbol": "NSE:AAAOPT",
                "timestamp": datetime(2026, 1, 5, 9, 20),
                "open": 10,
                "high": 13,
                "low": 10,
                "close": 12,
                "volume": 150,
            },
        ]
    )

    result = aggregate_option_turnover(data, 15)

    assert len(result) == 1
    assert result.iloc[0]["bucket_start"].strftime("%H:%M") == "09:15"
    assert result.iloc[0]["bucket_end"].strftime("%H:%M") == "09:30"
    assert result.iloc[0]["volume"] == 250
    assert result.iloc[0]["price"] == 12
    assert result.iloc[0]["turnover"] == 3000
