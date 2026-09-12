"""Streamlit dashboard for intraday F&O turnover rankings."""

from __future__ import annotations

from datetime import date, datetime, time, timedelta
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
import streamlit as st

from src.analytics import aggregate_candles, rank_top_stocks
from src.config import Settings
from src.fyers_client import FyersClient
from src.history_store import clear_all_downloads, clear_download, load_state, save_symbol_result
from src.market_socket import MarketSocket
from src.universe import build_equity_universe, load_symbol_list

st.set_page_config(page_title="F&O Turnover Leaders", page_icon="/", layout="wide")


@st.cache_data(ttl=24 * 60 * 60)
def load_universe() -> pd.DataFrame:
    client = FyersClient(Settings.from_environment())
    return build_equity_universe(client.download_master("cash"))


@st.cache_resource
def get_market_socket(access_token: str) -> MarketSocket:
    return MarketSocket(access_token)


def load_cached_history(start_date: date, end_date: date) -> pd.DataFrame:
    return load_state(start_date, end_date, "5").frame


def format_results(data: pd.DataFrame) -> pd.DataFrame:
    columns = [
        "trading_date", "bucket_start", "bucket_end", "rank", "symbol",
        "volume", "vwap", "turnover", "is_complete",
    ]
    result = data[columns].copy()
    result["symbol"] = result["symbol"].str.replace("NSE:", "", regex=False).str.removesuffix("-EQ")
    result["bucket_start"] = result["bucket_start"].dt.strftime("%H:%M")
    result["bucket_end"] = result["bucket_end"].dt.strftime("%H:%M")
    result["volume"] = result["volume"].round(0).astype("int64")
    result["vwap"] = result["vwap"].round(2)
    result["turnover"] = result["turnover"].round(2)
    return result.rename(
        columns={
            "trading_date": "Date", "bucket_start": "Start", "bucket_end": "End",
            "rank": "Rank", "symbol": "Symbol", "volume": "Volume",
            "vwap": "VWAP", "turnover": "Turnover", "is_complete": "Complete",
        }
    )


def format_ranked_snapshot(data: pd.DataFrame) -> pd.DataFrame:
    """Pivot ranked candles into one readable row per date and time bucket."""
    rows: list[dict[str, object]] = []
    for (trading_date, bucket_number), group in data.groupby(
        ["trading_date", "bucket_number"], sort=True
    ):
        first = group.iloc[0]
        row: dict[str, object] = {
            "Date": trading_date.strftime("%Y-%m-%d"),
            "Start": first["bucket_start"].strftime("%H:%M"),
            "End": first["bucket_end"].strftime("%H:%M"),
        }
        for rank in (1, 2, 3):
            ranked = group[group["rank"] == rank]
            if ranked.empty:
                row[f"Symbol {rank}"] = ""
                row[f"Change % {rank}"] = None
                row[f"LTP {rank}"] = None
                continue
            candle = ranked.iloc[0]
            opening_price = candle["open"]
            change_pct = ((candle["close"] - opening_price) / opening_price * 100) if opening_price else None
            row[f"Symbol {rank}"] = str(candle["symbol"]).replace("NSE:", "").removesuffix("-EQ")
            row[f"Change % {rank}"] = change_pct
            row[f"LTP {rank}"] = candle["close"]
        rows.append(row)
    return pd.DataFrame(rows)


def highlight_new_dates(frame: pd.DataFrame) -> pd.DataFrame:
    styles = pd.DataFrame("", index=frame.index, columns=frame.columns)
    previous_date = None
    for row_index, current_date in enumerate(frame["Date"]):
        if current_date != previous_date:
            styles.iloc[row_index, :] = "background-color: #fff1f0; color: #b42318; font-weight: 600; border-top: 2px solid #d92d20;"
        previous_date = current_date
    return styles


def is_market_open() -> bool:
    now = datetime.now(ZoneInfo("Asia/Kolkata"))
    return now.weekday() < 5 and time(9, 15) <= now.time() <= time(15, 30)


def render_results(raw_history: pd.DataFrame, interval: int) -> None:
    ranked = rank_top_stocks(aggregate_candles(raw_history, interval))
    if ranked.empty:
        st.warning("No positive-volume candles were available for ranking.")
        return

    latest_date = ranked["trading_date"].max()
    latest_bucket = ranked.loc[ranked["trading_date"] == latest_date, "bucket_number"].max()
    latest = ranked[
        (ranked["trading_date"] == latest_date) & (ranked["bucket_number"] == latest_bucket)
    ].sort_values("rank")
    latest_display = format_results(latest)
    top_symbol = latest_display.iloc[0]["Symbol"]
    total_turnover = latest["turnover"].sum()
    complete_count = int(latest["is_complete"].sum())
    with st.container(horizontal=True):
        st.metric("Latest candle", f"{latest_display.iloc[0]['Start']}–{latest_display.iloc[0]['End']}", border=True)
        st.metric("Top turnover stock", top_symbol, border=True)
        st.metric("Top 3 turnover", f"{total_turnover:,.0f}", border=True)
        st.metric("Complete candles", f"{complete_count}/{len(latest)}", border=True)

    with st.container(border=True):
        st.subheader("Latest candle leaders")
        chart = latest_display.set_index("Symbol")["Turnover"].sort_values(ascending=True)
        st.bar_chart(chart, horizontal=True)

    with st.container(border=True):
        st.subheader("Turnover ranking by candle")
        st.caption("LTP is the latest available close for each historical candle. New dates are highlighted.")
        snapshot = format_ranked_snapshot(ranked)
        styled_snapshot = snapshot.style.format(
            {
                "Change % 1": "{:.2f}%",
                "Change % 2": "{:.2f}%",
                "Change % 3": "{:.2f}%",
                "LTP 1": "{:.2f}",
                "LTP 2": "{:.2f}",
                "LTP 3": "{:.2f}",
            },
            na_rep="-",
        ).apply(highlight_new_dates, axis=None)
        st.dataframe(styled_snapshot, hide_index=True)
        st.download_button(
            "Download CSV",
            snapshot.to_csv(index=False).encode("utf-8"),
            file_name=f"turnover_top3_{latest_date}_{interval}m.csv",
            mime="text/csv",
        )


environment_settings = Settings.from_environment()
settings = Settings(
    client_id=st.session_state.get("login_client_id", environment_settings.client_id),
    secret_key=st.session_state.get("login_secret_key", environment_settings.secret_key),
    redirect_uri=st.session_state.get("login_redirect_uri", environment_settings.redirect_uri),
    access_token=environment_settings.access_token,
)
client = FyersClient(settings)
access_token = settings.access_token or st.session_state.get("fyers_access_token", "")
profile_data: dict[str, object] = {}
auth_error: str | None = None

if not access_token and settings.is_configured:
    auth_code = st.query_params.get("auth_code")
    if auth_code:
        try:
            access_token = client.exchange_auth_code(auth_code)
            st.session_state["fyers_access_token"] = access_token
        except Exception as error:
            auth_error = str(error)

if access_token:
    try:
        client.set_access_token(access_token)
        profile = client.profile()
        profile_data = profile.get("data", profile)
    except Exception as error:
        auth_error = str(error)
        access_token = ""


def render_login_page() -> None:
    st.title("F&O Turnover Leaders", text_alignment="center")
    st.subheader("Sign in with Fyers", text_alignment="center")
    st.caption("Connect your Fyers account to load equity candles and turnover rankings.", text_alignment="center")
    with st.container(border=True):
        client_id = st.text_input(
            "Fyers app ID",
            value=settings.client_id,
            key="login_client_id",
            placeholder="Enter your Fyers app ID",
        )
        secret_key = st.text_input(
            "Fyers secret key",
            value=settings.secret_key,
            type="password",
            key="login_secret_key",
            placeholder="Enter your Fyers secret key",
        )
        redirect_uri = st.text_input(
            "Fyers redirect URI",
            value=settings.redirect_uri or "http://localhost:8501",
            key="login_redirect_uri",
            help="This must exactly match the redirect URI registered in Fyers.",
        )
        if auth_error:
            st.error(f"Fyers sign-in failed: {auth_error}")
        st.write("Credentials are used by this server only to start the Fyers OAuth flow. The dashboard appears after your Fyers profile is verified.")
        login_settings = Settings(client_id.strip(), secret_key.strip(), redirect_uri.strip())
        if login_settings.is_configured:
            login_client = FyersClient(login_settings)
            st.link_button("Sign in with Fyers", login_client.authorization_url(), icon=":material/login:", width="stretch")
        else:
            st.info("Enter the app ID, secret key, and redirect URI to continue.")
        st.caption(f"Redirect URI: {redirect_uri}")
    st.caption("After sign-in, the dashboard downloads only the equity symbols in `- F&O Stocks.txt`.", text_alignment="center")


if not access_token:
    render_login_page()
    st.stop()

st.title("F&O Turnover Leaders")
st.caption("Top three NSE F&O equity stocks by estimated turnover in each intraday candle.")

with st.sidebar:
    st.header("Controls")
    start_date = st.date_input("From", value=date.today() - timedelta(days=7))
    end_date = st.date_input("To", value=date.today())
    interval = st.selectbox("Candle interval", (15, 25, 75, 125), index=0, format_func=lambda value: f"{value} minutes")
    st.divider()
    st.subheader("Connection")
    st.success("Connected to Fyers")
    st.write(f"**Name:** {profile_data.get('name', 'Unavailable')}")
    st.write(f"**Email:** {profile_data.get('email_id', profile_data.get('email', 'Unavailable'))}")
    st.write(f"**Account:** {profile_data.get('fy_id', profile_data.get('fyToken', 'Unavailable'))}")

    refresh = st.button("Refresh equity master", width="stretch")
    retry_download = st.button("Download all from scratch", width="stretch")
    market_open = is_market_open()
    live_refresh_enabled = st.toggle(
        "Live refresh every 15 minutes",
        value=market_open and end_date == date.today(),
        disabled=not market_open or end_date != date.today(),
        help="Reload selected current-day equity history every 15 minutes during NSE market hours.",
    )
    live_socket_enabled = st.toggle(
        "Connect live market WebSocket",
        value=False,
        disabled=not market_open,
    )
    if not market_open:
        st.caption("Live refresh is disabled outside NSE hours: 09:15–15:30 IST.")

if start_date > end_date:
    st.error("The start date must be on or before the end date.")
    st.stop()

try:
    client.set_access_token(access_token)
    if refresh:
        load_universe.clear()
    universe = load_universe()
    stock_file = Path(__file__).with_name("- F&O Stocks.txt")
    file_symbols = load_symbol_list(stock_file) if stock_file.exists() else []
    watchlist_symbols = build_equity_universe(universe, file_symbols)["symbol"].tolist()
    if not watchlist_symbols:
        st.error("No valid equity symbols were found in - F&O Stocks.txt.")
        st.stop()
    missing_file_symbols = sorted(set(file_symbols) - set(watchlist_symbols))
    st.metric("Equity stocks in file", f"{len(watchlist_symbols):,}")
    if missing_file_symbols:
        st.warning(f"{len(missing_file_symbols):,} symbols in the file are not available in the current cash master.")
    st.caption("Using - F&O Stocks.txt. Historical and live requests contain only NSE cash-equity symbols ending in -EQ.")
    def download_and_render(force_refresh: bool) -> None:
        history_start = start_date
        history_end = end_date
        if retry_download:
            deleted_files = clear_all_downloads()
            st.info(f"Cleared {deleted_files} old history cache files.")
        elif force_refresh:
            clear_download(history_start, history_end, "5")
            st.caption("Live refresh: reloading the selected current-day range.")
        history_state = load_state(history_start, history_end, "5")
        pending_symbols = [
            symbol for symbol in watchlist_symbols
            if symbol not in history_state.completed_symbols and symbol not in history_state.failed_symbols
        ]
        st.subheader("Historical 5-minute data")
        completed_count = len(history_state.completed_symbols.intersection(set(watchlist_symbols)))
        progress = completed_count / len(watchlist_symbols) if watchlist_symbols else 0
        st.progress(progress, text=f"Downloaded {completed_count:,} / {len(watchlist_symbols):,} stocks ({progress:.1%})")
        st.caption(f"Pending: {len(pending_symbols):,} stocks. Cache: {history_start} to {history_end}.")
        if pending_symbols:
            download_progress = st.progress(progress, text="Downloading equity candles...")
            download_status = st.empty()

            def on_symbol(completed: int, total: int, symbol: str, frame: pd.DataFrame | None, error: str | None) -> None:
                save_symbol_result(history_start, history_end, symbol, frame, error, "5")
                current = completed_count + completed
                ratio = current / len(watchlist_symbols) if watchlist_symbols else 1
                download_progress.progress(min(ratio, 1.0), text=f"Downloaded {current:,} / {len(watchlist_symbols):,} stocks ({ratio:.1%})")
                download_status.write(f"{symbol}: {'ok' if not error else error}")

            client.history_for_symbols(pending_symbols, history_start, history_end, resolution="5", progress_callback=on_symbol)
            history_state = load_state(history_start, history_end, "5")
            if history_state.failed_symbols:
                st.warning(f"{len(history_state.failed_symbols):,} symbols failed. See download errors below.")
            else:
                st.success("All watchlist equity data downloaded.")

        if history_state.failed_symbols:
            with st.expander(f"Download errors ({len(history_state.failed_symbols):,})"):
                st.dataframe(
                    pd.DataFrame([{"Symbol": symbol, "Error": message} for symbol, message in sorted(history_state.failed_symbols.items())]),
                    hide_index=True,
                )
        raw_history = history_state.frame
        if raw_history.empty:
            st.warning("Fyers returned no 5-minute candles for the selected range.")
            return
        if live_socket_enabled:
            market_socket = get_market_socket(access_token)
            market_socket.start(list(watchlist_symbols))
            st.info(f"Live WebSocket: {market_socket.status}")
        render_results(raw_history, interval)

    if live_refresh_enabled:
        @st.fragment(run_every="15m")
        def live_dashboard() -> None:
            download_and_render(force_refresh=True)

        live_dashboard()
    else:
        download_and_render(force_refresh=False)
except Exception as error:
    st.error(f"Unable to load Fyers data: {error}")