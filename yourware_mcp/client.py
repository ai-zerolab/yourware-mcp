from __future__ import annotations

from functools import cache
from typing import TYPE_CHECKING

import httpx

if TYPE_CHECKING:
    from yourware_mcp.credentials import Credentials


@cache
def get_client(credentials: Credentials) -> httpx.AsyncClient:
    return httpx.AsyncClient(base_url=credentials.base_url, headers={"Authorization": f"Bearer {credentials.api_key}"})
