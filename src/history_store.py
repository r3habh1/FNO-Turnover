"""Local storage and metadata for resumable historical downloads."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path

import pandas as pd

DATA_DIR = Path("data")


@dataclass
class DownloadState:
    completed_symbols: set[str]
    failed_symbols: dict[str, str]
    frame: pd.DataFrame


def _cache_prefix(namespace: str) -> str:
    return "".join(char if char.isalnum() or char in ("_", "-") else "_" for char in namespace)


def history_path(start: date, end: date, resolution: str = "5", namespace: str = "history") -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{_cache_prefix(namespace)}_{resolution}m_{start.isoformat()}_{end.isoformat()}.parquet"


def state_path(start: date, end: date, resolution: str = "5", namespace: str = "history") -> Path:
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    return DATA_DIR / f"{_cache_prefix(namespace)}_{resolution}m_{start.isoformat()}_{end.isoformat()}.state.csv"


def load_state(start: date, end: date, resolution: str = "5", namespace: str = "history") -> DownloadState:
    data_file = history_path(start, end, resolution, namespace)
    state_file = state_path(start, end, resolution, namespace)
    if state_file.exists():
        state_frame = pd.read_csv(state_file)
        completed = set(state_frame.loc[state_frame["status"] == "ok", "symbol"])
        failed = dict(zip(state_frame.loc[state_frame["status"] == "error", "symbol"], state_frame.loc[state_frame["status"] == "error", "message"]))
    else:
        completed, failed = set(), {}
    frame = pd.read_parquet(data_file) if data_file.exists() else pd.DataFrame()
    if not frame.empty and "symbol" not in frame.columns:
        if len(completed) == 1:
            frame.insert(0, "symbol", next(iter(completed)))
        else:
            frame = pd.DataFrame()
    return DownloadState(completed, failed, frame)


def save_symbol_result(
    start: date,
    end: date,
    symbol: str,
    frame: pd.DataFrame | None,
    error: str | None,
    resolution: str = "5",
    namespace: str = "history",
) -> None:
    data_file = history_path(start, end, resolution, namespace)
    state_file = state_path(start, end, resolution, namespace)
    existing = pd.read_parquet(data_file) if data_file.exists() else pd.DataFrame()
    if not existing.empty and "symbol" not in existing.columns:
        existing = pd.DataFrame()
    if frame is not None and not frame.empty:
        existing = pd.concat([existing[existing["symbol"] != symbol] if not existing.empty else existing, frame], ignore_index=True)
        existing.to_parquet(data_file, index=False)
    state = pd.read_csv(state_file) if state_file.exists() else pd.DataFrame(columns=["symbol", "status", "message"])
    state = state[state["symbol"] != symbol]
    state.loc[len(state)] = [symbol, "error" if error else "ok", error or ""]
    state.to_csv(state_file, index=False)


def clear_download(start: date, end: date, resolution: str = "5", namespace: str = "history") -> None:
    """Delete one cached download so it can be fetched again."""
    for path in (history_path(start, end, resolution, namespace), state_path(start, end, resolution, namespace)):
        if path.exists():
            path.unlink()


def clear_all_downloads() -> int:
    """Delete every cached history and status file and return the file count."""
    DATA_DIR.mkdir(parents=True, exist_ok=True)
    paths = list(DATA_DIR.glob("*_*m_*.parquet")) + list(DATA_DIR.glob("*_*m_*.state.csv"))
    for path in paths:
        path.unlink()
    return len(paths)
