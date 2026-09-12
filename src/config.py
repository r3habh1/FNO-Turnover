"""Environment-backed application configuration."""

from __future__ import annotations

import os
from dataclasses import dataclass

from dotenv import load_dotenv

load_dotenv()


@dataclass(frozen=True)
class Settings:
    client_id: str
    secret_key: str
    redirect_uri: str
    access_token: str = ""

    @classmethod
    def from_environment(cls) -> "Settings":
        return cls(
            client_id=os.getenv("FYERS_CLIENT_ID", "").strip(),
            secret_key=os.getenv("FYERS_SECRET_KEY", "").strip(),
            redirect_uri=os.getenv("FYERS_REDIRECT_URI", "").strip(),
            access_token=os.getenv("FYERS_ACCESS_TOKEN", "").strip(),
        )

    @property
    def is_configured(self) -> bool:
        return bool(self.client_id and self.secret_key and self.redirect_uri)

    def missing_fields(self) -> list[str]:
        fields = {
            "FYERS_CLIENT_ID": self.client_id,
            "FYERS_SECRET_KEY": self.secret_key,
            "FYERS_REDIRECT_URI": self.redirect_uri,
        }
        return [name for name, value in fields.items() if not value]