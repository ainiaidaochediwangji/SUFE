from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
from tqdm.asyncio import tqdm

from sufe.auth import load_credentials, login_service, login_sso
from sufe.career.export import normalize_record
from sufe.career.state import list_snapshot, save_state
from sufe.config import (
    CAREER_CONCURRENCY,
    CAREER_DETAIL_URL,
    CAREER_LIST_URL,
    CAREER_PAGE_SIZE,
    CAREER_SERVICE_URL,
    DEFAULT_HEADERS,
)

LIST_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "application/json, text/javascript, */*; q=0.01",
    "Content-Type": "application/x-www-form-urlencoded; charset=UTF-8",
    "Referer": "https://career.sufe.edu.cn/career/zpxx/sxzpxx",
    "X-Requested-With": "XMLHttpRequest",
}

DETAIL_HEADERS = {
    **LIST_HEADERS,
    "Origin": "https://career.sufe.edu.cn",
}


async def login(client: httpx.AsyncClient) -> None:
    username, password = await load_credentials()
    await login_sso(client, username, password)
    response = await login_service(client, CAREER_SERVICE_URL)
    response.raise_for_status()


async def _post(
    client: httpx.AsyncClient,
    url: str,
    headers: dict[str, str],
    data: dict[str, Any] | None = None,
) -> dict[str, Any]:
    response = await client.post(url, headers=headers, data=data, timeout=30.0)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != 200:
        raise RuntimeError(f"{url} returned code={payload.get('code')} message={payload.get('message')}")
    result = payload.get("data")
    if not isinstance(result, dict):
        raise RuntimeError(f"{url} returned invalid data payload")
    return result


async def list_page(client: httpx.AsyncClient, page_num: int) -> dict[str, Any]:
    url = f"{CAREER_LIST_URL}/{page_num}/{CAREER_PAGE_SIZE}"
    return await _post(client, url, headers=LIST_HEADERS)


async def load_details(
    client: httpx.AsyncClient,
    records: list[dict[str, Any]],
    detail_cache: dict[str, Any],
    page_cache: dict[str, Any],
    state_path: Path,
    concurrency: int = CAREER_CONCURRENCY,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], int]:
    semaphore = asyncio.Semaphore(concurrency)
    lock = asyncio.Lock()
    failures: list[dict[str, Any]] = []
    reused = 0

    async def fetch(item: dict[str, Any]) -> tuple[dict[str, Any], bool]:
        nonlocal reused
        zpxxid = str(item["zpxxid"])
        snapshot = list_snapshot(item)
        cached = detail_cache.get(zpxxid)
        if isinstance(cached, dict) and cached.get("_list_snapshot") == snapshot:
            reused += 1
            return cached, True

        async with semaphore:
            try:
                data = await _post(
                    client,
                    CAREER_DETAIL_URL,
                    headers=DETAIL_HEADERS,
                    data={"zpxxid": zpxxid},
                )
            except Exception as exc:
                failures.append({"zpxxid": zpxxid, "error": str(exc)})
                if cached:
                    return cached, True
                return {"zpxxid": zpxxid, "status": "failed", "error": str(exc)}, False
            record = normalize_record(data)
            record["_list_snapshot"] = snapshot
        async with lock:
            detail_cache[zpxxid] = record
            save_state(state_path, page_cache, detail_cache)
        return record, False

    details = await tqdm.gather(
        *(fetch(item) for item in records),
        desc="detail",
        unit="item",
        ascii=False,
    )
    return [item for item, _ in details], failures, reused
