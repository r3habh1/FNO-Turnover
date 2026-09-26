from datetime import date

import pandas as pd

from src.fy_path_analysis import completed_financial_years, normalize_fy_paths, stock_path


def test_completed_financial_years_after_march():
    years = completed_financial_years(date(2026, 9, 27), years=10)
    assert years[0] == ("FY2016-17", date(2016, 4, 1), date(2017, 3, 31))
    assert years[-1] == ("FY2025-26", date(2025, 4, 1), date(2026, 3, 31))
    assert len(years) == 10


def test_normalize_path_starts_at_zero_for_each_fy():
    data = pd.DataFrame(
        {
            "symbol": ["AAA", "AAA", "AAA", "AAA"],
            "timestamp": [
                "2025-04-01",
                "2025-04-02",
                "2026-03-30",
                "2026-03-31",
            ],
            "close": [100.0, 105.0, 95.0, 110.0],
        }
    )
    years = [("FY2025-26", date(2025, 4, 1), date(2026, 3, 31))]
    paths = normalize_fy_paths(data, years)

    assert paths.iloc[0]["return_pct"] == 0.0
    assert paths.iloc[1]["return_pct"] == 5.0
    assert paths.iloc[-1]["return_pct"] == 10.0


def test_stock_path_has_fy_series_and_median():
    data = pd.DataFrame(
        {
            "symbol": ["AAA"] * 4,
            "fy": ["FY1", "FY1", "FY2", "FY2"],
            "fy_day": [1, 2, 1, 2],
            "timestamp": pd.to_datetime(
                ["2025-04-01", "2025-04-02", "2026-04-01", "2026-04-02"]
            ),
            "calendar_date": ["01 Apr", "02 Apr", "01 Apr", "02 Apr"],
            "close": [100, 110, 200, 220],
            "return_pct": [0, 10, 0, 10],
        }
    )
    wide = stock_path(data, "AAA")
    assert list(wide.columns) == ["FY Day", "FY1", "FY2", "Median"]
    assert wide.loc[wide["FY Day"] == 2, "Median"].iloc[0] == 10
