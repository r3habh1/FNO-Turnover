"""Persistent Fyers market-data WebSocket wrapper for Streamlit."""

from __future__ import annotations

from threading import Lock, Thread
from typing import Any


class MarketSocket:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.status = "stopped"
        self.last_message: dict[str, Any] | None = None
        self._socket: Any = None
        self._thread: Thread | None = None
        self._lock = Lock()

    def start(self, symbols: list[str]) -> None:
        if self._thread and self._thread.is_alive():
            return
        from fyers_apiv3.FyersWebsocket import data_ws

        def on_message(message: dict[str, Any]) -> None:
            with self._lock:
                self.last_message = message

        def on_error(error: Any) -> None:
            self.status = f"error: {error}"

        def on_close(message: Any) -> None:
            self.status = "closed"

        def on_connect() -> None:
            self.status = "connected"
            self._socket.subscribe(symbols=symbols, data_type="SymbolUpdate")
            self._socket.keep_running()

        self._socket = data_ws.FyersDataSocket(
            access_token=self.access_token,
            on_message=on_message,
            on_error=on_error,
            on_connect=on_connect,
            on_close=on_close,
            reconnect=True,
        )
        self.status = "connecting"
        self._thread = Thread(target=self._socket.connect, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        if self._socket:
            self._socket.close_connection()
        self.status = "stopped"