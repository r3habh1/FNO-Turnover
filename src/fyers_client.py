"""Small Fyers API adapter with lazy SDK loading."""

from __future__ import annotations

from datetime import date, timedelta
from collections.abc import Callable
import threading
import time
from typing import Any

import pandas as pd
import requests

from .config import Settings

MASTER_URLS = {
    "cash": "https://public.fyers.in/sym_details/NSE_CM.csv",
}
HISTORY_REQUEST_INTERVAL_SECONDS = 0.12
MAX_HISTORY_RETRIES = 4


class FyersRateLimitError(RuntimeError):
    """Raised when Fyers rejects a history request because of rate limits."""


class FyersClient:
    def __init__(self, settings: Settings):
        self.settings = settings
        self._access_token = settings.access_token
        self._model: Any = None
        self._history_lock = threading.Lock()
        self._last_history_request = 0.0

    def set_access_token(self, access_token: str) -> None:
        self._access_token = access_token
        self._model = None

    def _sdk(self) -> Any:
        if self._model is None:
            try:
                from fyers_apiv3 import fyersModel
            except ImportError as error:
                raise RuntimeError("Install fyers-apiv3 before connecting to Fyers") from error
            if not self.settings.is_configured:
                missing = ", ".join(self.settings.missing_fields())
                raise RuntimeError(f"Missing Fyers configuration: {missing}")
            if not self._access_token:
                raise RuntimeError("Missing FYERS_ACCESS_TOKEN. Complete Fyers login before requesting market data.")
            self._model = fyersModel.FyersModel(
                client_id=self.settings.client_id,
                token=self._access_token,
                log_path="",
            )
        return self._model

    def profile(self) -> dict[str, Any]:
        """Return the authenticated Fyers profile or raise a useful error."""
        response = self._sdk().get_profile()
        if response.get("s") != "ok":
            raise RuntimeError(response.get("message", "Fyers profile request failed"))
        return response

    def authorization_url(self) -> str:
        if not self.settings.is_configured:
            missing = ", ".join(self.settings.missing_fields())
            raise RuntimeError(f"Missing Fyers configuration: {missing}")
        from fyers_apiv3 import fyersModel

        session = fyersModel.SessionModel(
            client_id=self.settings.client_id,
            secret_key=self.settings.secret_key,
            redirect_uri=self.settings.redirect_uri,
            response_type="code",
            grant_type="authorization_code",
        )
        return session.generate_authcode()

    def exchange_auth_code(self, auth_code: str) -> str:
        if not self.settings.is_configured:
            missing = ", ".join(self.settings.missing_fields())
            raise RuntimeError(f"Missing Fyers configuration: {missing}")
        from fyers_apiv3 import fyersModel

        session = fyersModel.SessionModel(
            client_id=self.settings.client_id,
            secret_key=self.settings.secret_key,
            redirect_uri=self.settings.redirect_uri,
            response_type="code",
            grant_type="authorization_code",
        )
        session.set_token(auth_code)
        response = session.generate_token()
        if response.get("s") != "ok" or not response.get("access_token"):
            raise RuntimeError(response.get("message", "Fyers token exchange failed"))
        self._access_token = response["access_token"]
        self._model = None
        return self._access_token

    def download_master(self, kind: str) -> pd.DataFrame:
        if kind not in MASTER_URLS:
            raise ValueError(f"Unknown master type: {kind}")
        response = requests.get(MASTER_URLS[kind], timeout=30)
        response.raise_for_status()
        from io import StringIO

        return pd.read_csv(StringIO(response.text), header=None)

    def history(self, symbol: str, start: date, end: date, resolution: str = "1") -> pd.DataFrame:
        with self._history_lock:
            elapsed = time.monotonic() - self._last_history_request
            if elapsed < HISTORY_REQUEST_INTERVAL_SECONDS:
                time.sleep(HISTORY_REQUEST_INTERVAL_SECONDS - elapsed)
            self._last_history_request = time.monotonic()
        response = self._sdk().history(
            {
                "symbol": symbol,
                "resolution": resolution,
                "date_format": 1,
                "range_from": start.isoformat(),
                "range_to": end.isoformat(),
                "cont_flag": 1,
            }
        )
        if response.get("s") != "ok":
            code = response.get("code", "unknown")
            message = response.get("message", "Fyers history request failed")
            if str(code) == "429" or "limit" in str(message).lower() or "too many" in str(message).lower():
                raise FyersRateLimitError(f"Fyers history failed ({code}): {message}")
            raise RuntimeError(f"Fyers history failed ({code}): {message}")
        candles = response.get("candles", response.get("Candels", []))
        result = pd.DataFrame(candles, columns=["timestamp", "open", "high", "low", "close", "volume"])
        if not result.empty:
            result["timestamp"] = pd.to_datetime(result["timestamp"], unit="s", utc=True).dt.tz_convert("Asia/Kolkata")
        return result

    def history_for_symbols(
        self,
        symbols: list[str],
        start: date,
        end: date,
        resolution: str = "5",
        chunk_days: int = 30,
        progress_callback: Callable[[int, int, str, pd.DataFrame | None, str | None], None] | None = None,
    ) -> pd.DataFrame:
        """Fetch and label history in bounded date chunks."""
        if chunk_days <= 0:
            raise ValueError("chunk_days must be positive")
        frames: list[pd.DataFrame] = []
        total = len(symbols)
        completed = 0
        for symbol in symbols:
            symbol_frames: list[pd.DataFrame] = []
            error_message: str | None = None
            callback_frame: pd.DataFrame | None = None
            try:
                chunk_start = start
                while chunk_start <= end:
                    chunk_end = min(chunk_start + timedelta(days=chunk_days - 1), end)
                    for attempt in range(MAX_HISTORY_RETRIES + 1):
                        try:
                            frame = self.history(symbol, chunk_start, chunk_end, resolution)
                            break
                        except FyersRateLimitError:
                            if attempt == MAX_HISTORY_RETRIES:
                                raise
                            time.sleep(2**attempt)
                    if not frame.empty:
                        symbol_frames.append(frame)
                    chunk_start = chunk_end + timedelta(days=1)
                if symbol_frames:
                    combined = pd.concat(symbol_frames, ignore_index=True)
                    combined.insert(0, "symbol", symbol)
                    frames.append(combined)
                    callback_frame = combined
                else:
                    error_message = f"No {resolution}-minute candles returned for {symbol} between {start} and {end}"
            except Exception as error:
                error_message = str(error)
            completed += 1
            if progress_callback:
                progress_callback(completed, total, symbol, callback_frame, error_message)
        if not frames:
            return pd.DataFrame(columns=["symbol", "timestamp", "open", "high", "low", "close", "volume"])
        return pd.concat(frames, ignore_index=True)