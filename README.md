# F&O Turnover Leaders Dashboard

This project contains a Streamlit dashboard that connects to Fyers, downloads
the current NSE F&O equity universe, fetches 1-minute historical candles, and
shows the top three stocks by turnover for each intraday candle.

The existing CSV analysis outputs in `outputs/` are retained separately from
the dashboard pipeline.

## Setup

The project uses the local `.venv` virtual environment.

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

Create a local `.env` file from `.env.example` and fill in the Fyers values:

```text
FYERS_CLIENT_ID=your_app_id
FYERS_SECRET_KEY=your_secret_key
FYERS_REDIRECT_URI=https://your-callback-url.example.com
FYERS_ACCESS_TOKEN=
```

Register the redirect URL in the Fyers developer console. For local testing it
must match `http://localhost:8501`; for deployment set it to the exact public
app URL registered with Fyers, for example `https://your-app.example.com`.
Start the dashboard:

```bash
streamlit run app.py
```

The first screen is the Fyers OAuth login page. Enter the Fyers app ID, secret
key, and registered redirect URI, then use **Sign in with Fyers**. The app ID
and secret are held only in the current Streamlit session when entered through
the page. For deployment, environment variables are preferred so users do not
need to enter developer credentials. The dashboard appears only after the
Fyers profile API confirms the session. Never commit `.env` or tokens.

## Dashboard behavior

- The **Master List** tab uses the NSE cash-equity master only. Enter the F&O
  stock list supplied by you with comma-separated input such as `RELIANCE, TCS,
  INFY`, select matching rows, and apply the watchlist.
- The checked-in `- F&O Stocks.txt` file is loaded automatically at startup as
  the default watchlist. Its symbols are validated against the current cash
  master before any history download begins.
- F&O is used only as your eligibility list. The app downloads and subscribes
  only to `NSE:<TICKER>-EQ` equity symbols. It does not download the derivatives
  master and never requests futures or options candles.
- Date range selects the historical session range.
- Candle intervals are 15, 25, 75, or 125 minutes, each anchored at 09:15.
- The final regular-session candle ends at 15:30 and may be shorter.
- The app does not reconstruct historical F&O membership. It validates the
  stock list supplied by you against the current NSE cash-equity master.
- Master files are cached for 24 hours and can be refreshed from the sidebar.
- Historical requests are cached for 15 minutes and split into 30-day chunks.
- History requests are paced at approximately 8.3 requests/second and 500
  requests/minute, below the Fyers 10/sec and 600/minute limits. Temporary 429
  responses are retried with exponential backoff.
- On authentication, the app downloads/resumes 5-minute candles for the dates
  selected in the sidebar and stores them under `data/` as Parquet plus a symbol
  status file. The sidebar shows completed progress and failed symbols.
- **Download all from scratch** removes every previous history cache before
  downloading the currently selected date range, preventing old date ranges
  from accumulating or mixing into the results.
- Live mode uses the Fyers WebSocket for current ticks after the historical
  backfill. REST remains the source for the historical cache because a socket
  cannot reconstruct candles missed while the app was offline.
- **Live refresh every 15 minutes** is enabled by default only on NSE weekdays
  from 09:15 to 15:30 IST and is disabled outside that window. Each live
  refresh reloads the selected current-day equity range through the REST API.
- The dashboard shows KPI cards for the latest candle, top turnover stock,
  combined top-three turnover, and candle completeness, followed by a latest
  candle leader chart and the detailed ranking table.
- The ranking table is grouped one row per candle with date, start/end time,
  `Symbol 1/2/3`, each symbol's `Change % 1/2/3`, and `LTP 1/2/3`.
  For historical data, LTP is the candle close and change percentage is
  `(close - open) / open * 100`.

Turnover is calculated as:

```text
VWAP = sum(((high + low + close) / 3) * minute_volume) / sum(minute_volume)
Turnover = candle_volume * VWAP
```

This is an OHLCV VWAP estimate because the historical Fyers response may not
include native VWAP.

## Existing CSV analysis

## Analyse next-day opening gap

Install requirements first:

```bash
source .venv/bin/activate
python -m pip install -r requirements.txt
```

The original analysis scripts can still be run when their source dataset is
available:

```bash
python analyze_nifty_opening.py /path/to/nifty/csv-or-folder
```

What it calculates:

- Previous trading day's last 5-minute candle OHLC/4.
- Next trading day's opening 15-minute candle OHLC/4.
- Percentage change between those two values.
- Weekday-wise average, minimum, maximum, median, and count for the latest
  3 years of available data.

Outputs are written to `outputs/`:

- `nifty_opening_gap_daily.csv`
- `nifty_opening_gap_weekday_summary.csv`
- `nifty_opening_gap_weekday_avg_min_max.png`
- `nifty_opening_gap_daily_series.png`
