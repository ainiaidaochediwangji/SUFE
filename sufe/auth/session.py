from __future__ import annotations

import httpx

from sufe.config import DEFAULT_HEADERS, SSO_LOGIN_PAGE_URL


def create_session() -> httpx.AsyncClient:
    return httpx.AsyncClient(
        headers={
            **DEFAULT_HEADERS,
            "Referer": SSO_LOGIN_PAGE_URL,
            "Origin": "https://login.sufe.edu.cn",
        },
        follow_redirects=True,
        timeout=httpx.Timeout(60.0),
    )
