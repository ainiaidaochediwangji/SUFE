from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

import httpx
from tqdm.asyncio import tqdm

from sufe.auth.session import create_session
from sufe.career.api import list_page, load_details, login
from sufe.career.export import (
    alerts,
    attachment_rows,
    normalize_record,
    position_rows,
    save_tables,
    sort_key,
    summary_row,
    write_notice,
)
from sufe.career.state import load_state, save_state
from sufe.config import CAREER_CONCURRENCY, CAREER_DIR, CAREER_MAX_ITEMS, CAREER_PAGE_CONCURRENCY, CAREER_PAGE_SIZE
from sufe.storage import ensure_directory, read_json, write_json


def run(
    concurrency: int = CAREER_CONCURRENCY,
    page_concurrency: int = CAREER_PAGE_CONCURRENCY,
    max_items: int = CAREER_MAX_ITEMS,
    output_dir: Path = CAREER_DIR,
) -> None:
    summary = asyncio.run(_run(concurrency, page_concurrency, max_items, output_dir))
    print("Done")
    for key in (
        "total", "pages", "tracked", "saved", "reused",
        "refreshed", "new_count", "updated_count", "removed_count",
    ):
        print(f"{key}: {summary[key]}")
    print(f"from_cache: {summary['from_cache']}")
    print(f"failed: {len(summary['failed'])}")
    print(f"output_dir: {summary['output_dir']}")


async def _run(
    concurrency: int,
    page_concurrency: int,
    max_items: int,
    output_dir: Path,
) -> dict[str, Any]:
    output_dir = ensure_directory(output_dir)
    previous_records = await asyncio.to_thread(read_json, output_dir / "records.json", [])
    if isinstance(previous_records, list):
        previous_records = sorted(
            [item for item in previous_records if isinstance(item, dict) and item.get("zpxxid")],
            reverse=True,
            key=sort_key,
        )[:max_items]
    else:
        previous_records = []
    page_cache, detail_cache, state_path = await asyncio.to_thread(load_state, output_dir, previous_records)

    async with create_session() as client:
        await login(client)
        from_cache = False
        try:
            first_page = await list_page(client, 1)
            page_cache["1"] = first_page
            await asyncio.to_thread(save_state, state_path, page_cache, detail_cache)
        except httpx.HTTPError:
            first_page = page_cache["1"]
            from_cache = True
        total = int(first_page["total"])
        target_items = min(max_items, total)
        target_pages = (target_items + CAREER_PAGE_SIZE - 1) // CAREER_PAGE_SIZE

        page_payloads: list[dict[str, Any] | None] = [None] * target_pages
        page_payloads[0] = first_page

        if target_pages > 1:
            semaphore = asyncio.Semaphore(page_concurrency)
            lock = asyncio.Lock()

            async def load_page(page_num: int) -> tuple[int, dict[str, Any]]:
                try:
                    async with semaphore:
                        data = await list_page(client, page_num)
                    async with lock:
                        page_cache[str(page_num)] = data
                        await asyncio.to_thread(save_state, state_path, page_cache, detail_cache)
                except httpx.HTTPError:
                    data = page_cache.get(str(page_num))
                return page_num, data

            results = await tqdm.gather(
                *(load_page(page_num) for page_num in range(2, target_pages + 1)),
                desc="list",
                unit="page",
                ascii=False,
            )
            for page_num, data in results:
                page_payloads[page_num - 1] = data

        records: list[dict[str, Any]] = []
        for payload in page_payloads:
            if not payload:
                continue
            for row in payload.get("list") or []:
                if isinstance(row, dict) and row.get("zpxxid"):
                    records.append(normalize_record(row))

        records = records[:target_items]
        records.sort(reverse=True, key=sort_key)
        details, failures, reused = await load_details(
            client,
            records,
            detail_cache,
            page_cache,
            state_path,
            concurrency=concurrency,
        )

    success = [item for item in details if item.get("status") != "failed"]
    success.sort(reverse=True, key=sort_key)
    summary_rows = [summary_row(item) for item in success]
    attachments: list[dict[str, Any]] = []
    positions: list[dict[str, Any]] = []
    for record in success:
        attachments.extend(attachment_rows(record))
        positions.extend(position_rows(record))

    change_alerts = alerts(previous_records, success)
    page_cache = {str(n): page_cache[str(n)] for n in range(1, target_pages + 1)}
    detail_cache = {str(item["zpxxid"]): detail_cache[str(item["zpxxid"])] for item in success}

    await asyncio.to_thread(save_state, state_path, page_cache, detail_cache)
    await asyncio.to_thread(write_json, output_dir / "records.json", success)
    await asyncio.to_thread(save_tables, output_dir, summary_rows, positions, attachments)
    await asyncio.to_thread(write_json, output_dir / "_alerts.json", change_alerts)
    await asyncio.to_thread(write_notice, output_dir / "_notice.txt", change_alerts)

    summary = {
        "total": total,
        "pages": target_pages,
        "tracked": target_items,
        "saved": len(success),
        "reused": reused,
        "refreshed": len(success) - reused,
        "new_count": change_alerts["new_count"],
        "updated_count": change_alerts["updated_count"],
        "removed_count": change_alerts["removed_count"],
        "from_cache": from_cache,
        "failed": failures,
        "output_dir": str(output_dir),
    }
    await asyncio.to_thread(write_json, output_dir / "_summary.json", summary)
    return summary
