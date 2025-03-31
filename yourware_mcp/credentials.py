from __future__ import annotations

import os
from pathlib import Path

from pydantic import BaseModel, ConfigDict

from yourware_mcp.client import get_client

CREDENTIALS_PATH = Path("~/.yourware/credentials.json").expanduser().resolve()
API_BASE_URL = os.getenv("YOURWARE_ENDPOINT", "https://www.yourware.so")


class Credentials(BaseModel):
    api_key: str
    base_url: str = API_BASE_URL

    model_config = ConfigDict(frozen=True)

    def store_credentials(self) -> None:
        CREDENTIALS_PATH.parent.mkdir(parents=True, exist_ok=True)
        CREDENTIALS_PATH.write_text(self.model_dump_json(include=["api_key"]))

    @classmethod
    def load(cls) -> Credentials:
        api_key_from_env = os.getenv("YOURWARE_API_KEY")
        if api_key_from_env:
            return cls(api_key=api_key_from_env)

        if not CREDENTIALS_PATH.exists():
            raise FileNotFoundError(f"Credentials not found at {CREDENTIALS_PATH}")  # noqa: TRY003

        return cls.model_validate_json(CREDENTIALS_PATH.read_text())

    async def check_credentials(self) -> bool:
        api_key_list_path = "/api/v1/api-keys/list"
        client = get_client(self)
        response = await client.get(api_key_list_path)
        return response.status_code == 200
