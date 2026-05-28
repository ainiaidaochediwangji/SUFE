from __future__ import annotations

import shutil
from pathlib import Path
from typing import Any

from sufe.storage import ensure_directory, read_json, write_json


def list_snapshot(item: dict[str, Any]) -> dict[str, Any]:
    keys = [
        "zpxxid",
        "fbrq",
        "zpzt",
        "dwmc",
        "hyyjmc",
        "xzyjmc",
        "rsgmmc",
        "szssmc",
        "szsmc",
        "szxmc",
        "xxdz",
        "zpjzrq",
        "jltdyx",
        "zpxxwz",
        "dwwz",
        "xqrs",
        "zws",
        "zpxxAttach",
    ]
    return {key: item.get(key) for key in keys}


def load_state(output_dir: Path, records: list[dict[str, Any]]) -> tuple[dict[str, Any], dict[str, Any], Path]:
    cache_dir = ensure_directory(output_dir / "cache")
    path = cache_dir / "state.json"
    state = read_json(path, {})
    if not isinstance(state, dict):
        state = {}
    pages = state.get("pages") if isinstance(state.get("pages"), dict) else {}
    details = state.get("details") if isinstance(state.get("details"), dict) else {}

    legacy_page_path = output_dir / "cache" / "pages.json"
    legacy_detail_path = output_dir / "cache" / "details.json"
    legacy_pages = read_json(legacy_page_path, {})
    legacy_details = read_json(legacy_detail_path, {})
    if isinstance(legacy_pages, dict):
        pages.update({str(key): value for key, value in legacy_pages.items()})
    if isinstance(legacy_details, dict):
        details.update({str(key): value for key, value in legacy_details.items()})
    for item in records:
        details.setdefault(str(item["zpxxid"]), item)

    for legacy_path in (legacy_page_path, legacy_detail_path):
        if legacy_path.exists():
            legacy_path.unlink()

    if not isinstance(pages, dict):
        pages = {}

    for legacy_dir in (output_dir / "pages", output_dir / "cache" / "pages"):
        if not legacy_dir.exists() or not legacy_dir.is_dir():
            continue
        for item_path in legacy_dir.glob("*.json"):
            key = item_path.stem.removeprefix("page-").lstrip("0") or "0"
            if key not in pages:
                pages[key] = read_json(item_path, {})
        shutil.rmtree(legacy_dir)
    for legacy_dir in (output_dir / "details", output_dir / "cache" / "details"):
        if not legacy_dir.exists() or not legacy_dir.is_dir():
            continue
        for item_path in legacy_dir.glob("*.json"):
            details.setdefault(item_path.stem, read_json(item_path, {}))
        shutil.rmtree(legacy_dir)
    return pages, details, path


def save_state(path: Path, pages: dict[str, Any], details: dict[str, Any]) -> None:
    write_json(path, {"pages": pages, "details": details})
