from __future__ import annotations

import asyncio
import html
import json
import re
from pathlib import Path
from typing import Any, AsyncIterator
from urllib.parse import quote, urlparse

import aiofiles
import httpx

from sufe.config import (
    CANVAS_API_ROOT,
    CANVAS_BASE_URL,
    CANVAS_CAS_LOGIN_URL,
    CANVAS_FILE_CONCURRENCY,
    CANVAS_MODULE_CONCURRENCY,
    FILE_HEADERS,
    HTML_HEADERS,
    JSON_HEADERS,
    SSO_SERVICE_LOGIN_URL,
)
from sufe.storage import course_directory, ensure_directory, read_json, sanitize_name, write_json

COURSE_CODE_RE = re.compile(r"^[A-Za-z]{2,}[A-Za-z0-9_-]*\d+[A-Za-z0-9_-]*$")
ENV_JSON_RE = re.compile(r"ENV = (\{.*?\});", re.DOTALL)
ASSIGNMENT_API_ENDPOINT_RE = re.compile(r'data-api-endpoint="([^"]*?/api/v1/(?:courses/\d+/)?files/\d+)"')
ASSIGNMENT_COURSE_FILE_RE = re.compile(r"/courses/(\d+)/files/(\d+)")
ASSIGNMENT_GLOBAL_FILE_RE = re.compile(r"/files/(\d+)/download")
VIEWER_PREVIEW_SRC_RE = re.compile(r'src="/(preview/\d+\.[A-Za-z0-9]+)"')


def _next_link(response: httpx.Response) -> str | None:
    for value in response.headers.get_list("link"):
        for part in value.split(","):
            segment = part.strip()
            if 'rel="next"' in segment:
                url = segment.split(";", 1)[0].strip()
                if url.startswith("<") and url.endswith(">"):
                    return url[1:-1]
    return None


async def _html_get(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    headers = {**HTML_HEADERS, **kwargs.pop("headers", {})}
    response = await client.get(url, headers=headers, **kwargs)
    response.raise_for_status()
    return response


async def _json_get(client: httpx.AsyncClient, url: str, **kwargs: Any) -> httpx.Response:
    headers = {**JSON_HEADERS, **kwargs.pop("headers", {})}
    response = await client.get(url, headers=headers, **kwargs)
    response.raise_for_status()
    return response


def _is_canvas_host(url: str) -> bool:
    return urlparse(url).netloc.lower() == "canvas.shufe.edu.cn"


async def _canvas_api_ready(client: httpx.AsyncClient) -> bool:
    response = await client.get(
        f"{CANVAS_API_ROOT}/courses",
        params={"per_page": 1},
        headers=JSON_HEADERS,
    )
    return response.status_code == 200


async def login(client: httpx.AsyncClient) -> str:
    initial = await _html_get(client, CANVAS_BASE_URL)
    if _is_canvas_host(str(initial.url)) and await _canvas_api_ready(client):
        return str(initial.url)

    service_url = f"{SSO_SERVICE_LOGIN_URL}?service={quote(CANVAS_CAS_LOGIN_URL, safe='')}"
    service_response = await _html_get(client, service_url)
    if not _is_canvas_host(str(service_response.url)):
        raise RuntimeError(f"Canvas CAS handoff did not finish on Canvas: {service_response.url}")
    if not await _canvas_api_ready(client):
        raise RuntimeError(f"Canvas page loaded but API is still unauthorized: {service_response.url}")
    return str(service_response.url)


async def _paginate(
    client: httpx.AsyncClient,
    url: str,
    params: list[tuple[str, str]] | dict[str, Any] | None = None,
) -> AsyncIterator[Any]:
    next_url: str | None = url
    next_params = params
    while next_url:
        response = await client.get(next_url, params=next_params, headers=JSON_HEADERS)
        if response.status_code == 401:
            raise RuntimeError(f"Canvas API request was unauthorized: {next_url}")
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            for item in data:
                yield item
        else:
            yield data
        next_url = _next_link(response)
        next_params = None


def _extract_subject(course: dict[str, Any]) -> str | None:
    for key in ("sis_course_id", "integration_id"):
        value = course.get(key)
        if isinstance(value, str) and value.strip():
            return value.strip()

    name = str(course.get("name") or "")
    course_code = str(course.get("course_code") or "").strip()
    if course_code and course_code != name:
        return course_code

    for token in re.split(r"[\s\-_()]+", name):
        token = token.strip()
        if COURSE_CODE_RE.match(token):
            return token
    return None


def _normalize_course_record(raw: dict[str, Any]) -> dict[str, Any]:
    course_id = int(raw["id"])
    name = raw.get("name") or raw.get("shortName") or raw.get("originalName") or raw.get("courseCode") or f"course-{course_id}"
    course_code = raw.get("course_code") or raw.get("courseCode") or ""
    normalized = {
        "id": course_id,
        "name": str(name),
        "course_code": str(course_code),
        "subject": None,
        "term": None,
    }
    normalized["subject"] = _extract_subject(normalized | raw)
    term = raw.get("term")
    if isinstance(term, dict):
        normalized["term"] = term.get("name")
    elif raw.get("term"):
        normalized["term"] = raw.get("term")
    return normalized


async def _courses_from_api(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    params = [
        ("enrollment_state", "active"),
        ("enrollment_state", "completed"),
        ("enrollment_state", "invited_or_pending_creation"),
        ("include[]", "term"),
        ("include[]", "favorites"),
        ("include[]", "teachers"),
        ("per_page", "100"),
    ]
    seen: set[int] = set()
    courses: list[dict[str, Any]] = []
    async for raw in _paginate(client, f"{CANVAS_API_ROOT}/courses", params=params):
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        course_id = int(raw["id"])
        if course_id in seen:
            continue
        seen.add(course_id)
        courses.append(_normalize_course_record(raw))
    return courses


async def _courses_from_dashboard_html(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    response = await _html_get(client, CANVAS_BASE_URL)
    if not _is_canvas_host(str(response.url)):
        raise RuntimeError(f"Dashboard HTML fallback landed off Canvas: {response.url}")

    match = ENV_JSON_RE.search(response.text)
    if not match:
        raise RuntimeError("Could not locate Canvas ENV payload in dashboard HTML")
    env_payload = json.loads(match.group(1))
    planner_courses = env_payload.get("STUDENT_PLANNER_COURSES") or []
    return [_normalize_course_record(c) for c in planner_courses if isinstance(c, dict) and c.get("id")]


async def load_courses(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    api_error: Exception | None = None
    try:
        courses = await _courses_from_api(client)
        if courses:
            return courses
        api_error = RuntimeError("Canvas API returned no courses")
    except Exception as exc:
        api_error = exc

    html_courses = await _courses_from_dashboard_html(client)
    if html_courses:
        return html_courses
    raise RuntimeError(f"Failed to load Canvas courses via API or HTML fallback: {api_error}")


def _normalize_file_record(raw: dict[str, Any], source: str, module_name: str | None = None) -> dict[str, Any]:
    return {
        "id": raw.get("id"),
        "display_name": raw.get("display_name") or raw.get("filename") or f"file-{raw.get('id')}",
        "filename": raw.get("filename") or raw.get("display_name") or f"file-{raw.get('id')}",
        "size": raw.get("size"),
        "url": raw.get("url") or raw.get("download_url") or raw.get("html_url"),
        "folder_full_name": raw.get("folder_full_name"),
        "content_type": raw.get("content-type") or raw.get("content_type"),
        "updated_at": raw.get("updated_at") or raw.get("modified_at"),
        "locked_for_user": raw.get("locked_for_user"),
        "lock_explanation": raw.get("lock_explanation"),
        "preview_url": raw.get("preview_url") or raw.get("enhanced_preview_url"),
        "source": source,
        "module_name": module_name,
    }


def _local_filename(record: dict[str, Any]) -> str:
    return sanitize_name(record.get("display_name") or record.get("filename") or "unnamed")


def _normalize_assignment_record(raw: dict[str, Any]) -> dict[str, Any]:
    assignment_id = int(raw["id"])
    return {
        "id": assignment_id,
        "name": str(raw.get("name") or f"assignment-{assignment_id}"),
        "description": str(raw.get("description") or ""),
        "html_url": str(raw.get("html_url") or ""),
        "due_at": raw.get("due_at"),
        "unlock_at": raw.get("unlock_at"),
        "lock_at": raw.get("lock_at"),
        "points_possible": raw.get("points_possible"),
        "submission_types": raw.get("submission_types") or [],
        "published": raw.get("published"),
        "locked_for_user": raw.get("locked_for_user"),
        "lock_explanation": raw.get("lock_explanation"),
    }


async def _course_files(client: httpx.AsyncClient, course_id: int) -> list[dict[str, Any]]:
    raw_items = [
        item
        async for item in _paginate(client, f"{CANVAS_API_ROOT}/courses/{course_id}/files", params={"per_page": 100})
        if isinstance(item, dict)
    ]

    folder_ids = sorted(
        {
            int(item["folder_id"])
            for item in raw_items
            if item.get("folder_id") is not None and str(item.get("folder_id")).isdigit()
        }
    )
    folder_details: dict[int, dict[str, Any]] = {}
    for folder_id in folder_ids:
        async for item in _paginate(
            client,
            f"{CANVAS_API_ROOT}/folders/{folder_id}/files",
            params=[
                ("include[]", "user"),
                ("include[]", "usage_rights"),
                ("include[]", "enhanced_preview_url"),
                ("include[]", "context_asset_string"),
                ("per_page", "100"),
            ],
        ):
            if isinstance(item, dict) and item.get("id"):
                folder_details[int(item["id"])] = item

    normalized: list[dict[str, Any]] = []
    for item in raw_items:
        merged = dict(item)
        item_id = item.get("id")
        if item_id is not None:
            detail = folder_details.get(int(item_id))
            if detail:
                merged.update(detail)
        normalized.append(_normalize_file_record(merged, source="files"))
    return normalized


async def _course_assignments(client: httpx.AsyncClient, course_id: int) -> list[dict[str, Any]]:
    return [
        _normalize_assignment_record(item)
        async for item in _paginate(client, f"{CANVAS_API_ROOT}/courses/{course_id}/assignments", params={"per_page": 100})
        if isinstance(item, dict) and item.get("id")
    ]


async def _module_files(
    client: httpx.AsyncClient,
    course_id: int,
    concurrency: int = CANVAS_MODULE_CONCURRENCY,
) -> list[dict[str, Any]]:
    modules = [
        m
        async for m in _paginate(client, f"{CANVAS_API_ROOT}/courses/{course_id}/modules", params={"per_page": 100})
        if isinstance(m, dict) and m.get("id")
    ]

    semaphore = asyncio.Semaphore(concurrency)

    async def fetch_file(module: dict[str, Any], item: dict[str, Any]) -> dict[str, Any] | None:
        content_id = item.get("content_id")
        if not content_id:
            return None
        async with semaphore:
            try:
                response = await _json_get(client, f"{CANVAS_API_ROOT}/files/{content_id}")
                return _normalize_file_record(
                    response.json(),
                    source="modules",
                    module_name=str(module.get("name") or f"module-{module['id']}"),
                )
            except httpx.HTTPError:
                return None

    tasks = []
    for module in modules:
        async for item in _paginate(
            client,
            f"{CANVAS_API_ROOT}/courses/{course_id}/modules/{module['id']}/items",
            params={"per_page": 100},
        ):
            if isinstance(item, dict) and item.get("type") == "File":
                tasks.append(fetch_file(module, item))

    results = await asyncio.gather(*tasks)
    return [r for r in results if r is not None]


async def load_materials(
    client: httpx.AsyncClient,
    course: dict[str, Any],
    concurrency: int = CANVAS_MODULE_CONCURRENCY,
) -> list[dict[str, Any]]:
    files = await _course_files(client, course["id"])
    module_files = await _module_files(client, course["id"], concurrency=concurrency)
    merged: dict[tuple[Any, str, str | None], dict[str, Any]] = {}
    for record in files + module_files:
        key = (record.get("id"), record.get("source"), record.get("module_name"))
        merged[key] = record
    return list(merged.values())


def _target_dir_for_record(base_dir: Path, record: dict[str, Any]) -> Path:
    if record["source"] == "modules":
        module_name = sanitize_name(record.get("module_name") or "module")
        return ensure_directory(base_dir / "modules" / module_name)

    target_dir = base_dir / "files"
    folder_full_name = str(record.get("folder_full_name") or "").strip()
    if folder_full_name:
        for segment in folder_full_name.split("/"):
            segment = segment.strip()
            if segment:
                target_dir /= sanitize_name(segment)
    return ensure_directory(target_dir)


def _assignment_directory(base_dir: Path, assignment: dict[str, Any], used_names: set[str]) -> Path:
    base_name = sanitize_name(assignment["name"])
    folder_name = base_name if base_name not in used_names else sanitize_name(f"{assignment['name']} ({assignment['id']})")
    used_names.add(folder_name)
    return ensure_directory(base_dir / "assignments" / folder_name)


async def _write_text_if_changed(path: Path, content: str) -> dict[str, Any]:
    ensure_directory(path.parent)
    if path.exists():
        existing = await asyncio.to_thread(path.read_text, encoding="utf-8")
        if existing == content:
            return {"status": "skipped", "path": str(path), "reason": "already_exists"}
    async with aiofiles.open(path, "w", encoding="utf-8") as f:
        await f.write(content)
    return {"status": "downloaded", "path": str(path), "size": path.stat().st_size}


def _render_assignment_html(course: dict[str, Any], assignment: dict[str, Any]) -> str:
    metadata_lines = [
        f"<li><strong>课程</strong>: {html.escape(course['name'])}</li>",
        f"<li><strong>作业 ID</strong>: {assignment['id']}</li>",
        f"<li><strong>截止时间</strong>: {html.escape(str(assignment.get('due_at') or ''))}</li>",
        f"<li><strong>开放时间</strong>: {html.escape(str(assignment.get('unlock_at') or ''))}</li>",
        f"<li><strong>锁定时间</strong>: {html.escape(str(assignment.get('lock_at') or ''))}</li>",
        f"<li><strong>分值</strong>: {html.escape(str(assignment.get('points_possible') or ''))}</li>",
        f"<li><strong>提交类型</strong>: {html.escape(', '.join(assignment.get('submission_types') or []))}</li>",
        f"<li><strong>页面链接</strong>: <a href=\"{html.escape(assignment.get('html_url') or '')}\">{html.escape(assignment.get('html_url') or '')}</a></li>",
    ]
    if assignment.get("lock_explanation"):
        metadata_lines.append(f"<li><strong>锁定说明</strong>: {html.escape(str(assignment['lock_explanation']))}</li>")

    description = assignment.get("description") or "<p>(No description)</p>"
    return (
        "<!DOCTYPE html>\n"
        '<html lang="zh-CN">\n'
        "<head>\n"
        '  <meta charset="utf-8">\n'
        f"  <title>{html.escape(assignment['name'])}</title>\n"
        "</head>\n"
        "<body>\n"
        f"  <h1>{html.escape(assignment['name'])}</h1>\n"
        "  <ul>\n"
        f"    {' '.join(metadata_lines)}\n"
        "  </ul>\n"
        "  <hr>\n"
        f"  <div>{description}</div>\n"
        "</body>\n"
        "</html>\n"
    )


def _assignment_file_api_urls(course_id: int, description_html: str) -> list[str]:
    urls: set[str] = set()
    if not description_html:
        return []

    for url in ASSIGNMENT_API_ENDPOINT_RE.findall(description_html):
        if url.startswith("/"):
            url = f"{CANVAS_BASE_URL.rstrip('/')}{url}"
        urls.add(url)

    for match in ASSIGNMENT_COURSE_FILE_RE.finditer(description_html):
        matched_course_id, file_id = match.groups()
        urls.add(f"{CANVAS_API_ROOT}/courses/{matched_course_id}/files/{file_id}")

    for match in ASSIGNMENT_GLOBAL_FILE_RE.finditer(description_html):
        file_id = match.group(1)
        urls.add(f"{CANVAS_API_ROOT}/files/{file_id}")

    if not urls and "/files/" in description_html:
        for match in re.finditer(r"/files/(\d+)", description_html):
            file_id = match.group(1)
            urls.add(f"{CANVAS_API_ROOT}/courses/{course_id}/files/{file_id}")

    return sorted(urls)


async def _assignment_linked_files(
    client: httpx.AsyncClient,
    course_id: int,
    assignment: dict[str, Any],
    concurrency: int = CANVAS_MODULE_CONCURRENCY,
) -> list[dict[str, Any]]:
    api_urls = _assignment_file_api_urls(course_id, assignment.get("description") or "")
    if not api_urls:
        return []

    semaphore = asyncio.Semaphore(concurrency)
    seen_ids: set[int] = set()

    async def fetch(api_url: str) -> dict[str, Any] | None:
        async with semaphore:
            try:
                response = await _json_get(client, api_url)
                payload = response.json()
            except httpx.HTTPError:
                return None
        if not isinstance(payload, dict) or not payload.get("id"):
            return None
        return payload

    payloads = await asyncio.gather(*(fetch(url) for url in api_urls))
    discovered: list[dict[str, Any]] = []
    for payload in payloads:
        if payload is None:
            continue
        file_id = int(payload["id"])
        if file_id in seen_ids:
            continue
        seen_ids.add(file_id)
        discovered.append(
            _normalize_file_record(payload, source="assignments", module_name=assignment["name"])
        )
    return discovered


async def _preview_download_url(client: httpx.AsyncClient, record: dict[str, Any]) -> str | None:
    file_id = record.get("id")
    if not file_id:
        return None

    preview_url = str(record.get("preview_url") or "").strip()
    filename = str(record.get("filename") or record.get("display_name") or "")
    suffix = Path(filename).suffix.lower()
    content_type = str(record.get("content_type") or "").lower()
    if not suffix and content_type == "application/pdf":
        suffix = ".pdf"
    if not suffix:
        return None

    if preview_url:
        viewer_url = preview_url
        if viewer_url.startswith("/"):
            viewer_url = f"{CANVAS_BASE_URL.rstrip('/')}{viewer_url}"
        try:
            viewer_response = await client.get(viewer_url, headers=HTML_HEADERS)
            viewer_response.raise_for_status()
            match = VIEWER_PREVIEW_SRC_RE.search(viewer_response.text)
            if match:
                return f"{CANVAS_BASE_URL.rstrip('/')}/{match.group(1)}"
        except httpx.HTTPError:
            pass

        preview_path = urlparse(preview_url).path
        match = re.search(r"/files/(\d+)/file_preview$", preview_path)
        if match:
            file_id = match.group(1)

    return f"{CANVAS_BASE_URL.rstrip('/')}/preview/{file_id}{suffix}"


async def _warm_preview(client: httpx.AsyncClient, record: dict[str, Any], attempts: int = 4, wait_seconds: float = 2.0) -> None:
    file_id = record.get("id")
    if not file_id:
        return

    preview_page_url = str(record.get("preview_url") or "").strip()
    if preview_page_url:
        if preview_page_url.startswith("/"):
            preview_page_url = f"{CANVAS_BASE_URL.rstrip('/')}{preview_page_url}"
        try:
            await client.get(preview_page_url, headers=HTML_HEADERS)
        except httpx.HTTPError:
            pass

    state_url = f"{CANVAS_BASE_URL.rstrip('/')}/viewer/{file_id}/state"
    for _ in range(attempts):
        try:
            response = await client.get(state_url, headers=JSON_HEADERS)
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError):
            await asyncio.sleep(wait_seconds)
            continue

        if str(payload.get("state")) == "1":
            return
        await asyncio.sleep(wait_seconds)


async def _preview_state(client: httpx.AsyncClient, file_id: Any) -> str | None:
    try:
        response = await client.get(
            f"{CANVAS_BASE_URL.rstrip('/')}/viewer/{file_id}/state",
            headers=JSON_HEADERS,
        )
        response.raise_for_status()
        payload = response.json()
    except (httpx.HTTPError, ValueError):
        return None
    state = payload.get("state")
    return None if state is None else str(state)


async def download_file(
    client: httpx.AsyncClient,
    file_record: dict[str, Any],
    target_dir: Path,
    prev_updated_at: str | None = None,
) -> dict[str, Any]:
    ensure_directory(target_dir)
    filename = _local_filename(file_record)
    target_path = target_dir / filename
    expected_size = file_record.get("size")
    if isinstance(expected_size, str) and expected_size.isdigit():
        expected_size = int(expected_size)

    current_updated_at = file_record.get("updated_at")
    file_updated = current_updated_at != prev_updated_at

    if target_path.exists():
        # Size matches but file was updated on server → re-download
        if expected_size is not None and target_path.stat().st_size == expected_size and not file_updated:
            return {"status": "skipped", "path": str(target_path), "reason": "already_exists"}
        # No size info and no update detected → skip
        if expected_size is None and not file_updated:
            return {"status": "skipped", "path": str(target_path), "reason": "already_exists_unknown_size"}

    candidates: list[tuple[str, str]] = []
    download_url = str(file_record.get("url") or "").strip()
    if download_url:
        candidates.append(("direct", download_url))

    preview_url = await _preview_download_url(client, file_record)
    if preview_url:
        candidates.append(("preview", preview_url))

    if not candidates:
        lock_explanation = file_record.get("lock_explanation") or ""
        if file_record.get("locked_for_user") or lock_explanation:
            return {"status": "skipped", "path": str(target_path), "reason": lock_explanation or "locked_for_user"}
        return {"status": "failed", "path": str(target_path), "reason": "missing_download_url"}

    last_error: Exception | None = None
    for name, url in candidates:
        max_attempts = 6 if name == "preview" else 3
        for attempt in range(max_attempts):
            try:
                if name == "preview":
                    await _warm_preview(client, file_record)
                async with client.stream("GET", url, headers=FILE_HEADERS, timeout=httpx.Timeout(30.0, read=300.0)) as response:
                    response.raise_for_status()
                    async with aiofiles.open(target_path, "wb") as f:
                        async for chunk in response.aiter_bytes(chunk_size=1024 * 128):
                            await f.write(chunk)
                break
            except httpx.HTTPError as exc:
                last_error = exc
                if target_path.exists():
                    target_path.unlink()
                if attempt == max_attempts - 1 and name == candidates[-1][0]:
                    raise
                pstate = None
                if name == "preview":
                    pstate = await _preview_state(client, file_record.get("id"))
                wait = 5.0 * (attempt + 1) if name == "preview" and pstate == "0" else 2.0 * (attempt + 1)
                await asyncio.sleep(wait)
        else:
            continue
        break
    else:
        if last_error is not None:
            raise last_error

    if expected_size is not None and target_path.stat().st_size != expected_size:
        actual_size = target_path.stat().st_size
        print(f"  [WARN] Size mismatch for {filename}: expected {expected_size}, got {actual_size}")
        return {"status": "downloaded", "path": str(target_path), "size": actual_size, "size_mismatch": True}

    return {"status": "downloaded", "path": str(target_path), "size": target_path.stat().st_size}


async def download(
    client: httpx.AsyncClient,
    course: dict[str, Any],
    download_dir: Path,
    file_concurrency: int = CANVAS_FILE_CONCURRENCY,
    module_concurrency: int = CANVAS_MODULE_CONCURRENCY,
) -> dict[str, Any]:
    base_dir = course_directory(download_dir, course)
    records = await load_materials(client, course, concurrency=module_concurrency)
    assignments = await _course_assignments(client, course["id"])

    # Read previous download report to detect updates
    prev_report_path = base_dir / "_download_report.json"
    prev_report = await asyncio.to_thread(read_json, prev_report_path, None)
    prev_updated_at_map: dict[Any, str | None] = {}
    if isinstance(prev_report, dict):
        for record in prev_report.get("discovered", []):
            file_id = record.get("id")
            if file_id is not None:
                prev_updated_at_map[file_id] = record.get("updated_at")
        for record in prev_report.get("assignment_attachments", []):
            file_id = record.get("id")
            if file_id is not None:
                prev_updated_at_map[file_id] = record.get("updated_at")

    semaphore = asyncio.Semaphore(file_concurrency)
    downloads: list[dict[str, Any]] = []
    assignment_attachments: list[dict[str, Any]] = []

    async def download_one(record: dict[str, Any]) -> dict[str, Any]:
        target_dir = _target_dir_for_record(base_dir, record)
        file_id = record.get("id")
        prev_updated_at = prev_updated_at_map.get(file_id) if file_id is not None else None
        async with semaphore:
            try:
                result = await download_file(client, record, target_dir, prev_updated_at)
            except Exception as exc:
                result = {
                    "status": "failed",
                    "path": str(target_dir / _local_filename(record)),
                    "reason": str(exc),
                }
        return {
            "file": record["display_name"],
            "source": record["source"],
            "module_name": record.get("module_name"),
            **result,
        }

    file_results = await asyncio.gather(*(download_one(r) for r in records))
    downloads.extend(file_results)

    async def download_attachment(
        record: dict[str, Any],
        attachments_dir: Path,
        assignment_name: str,
    ) -> dict[str, Any]:
        file_id = record.get("id")
        prev_updated_at = prev_updated_at_map.get(file_id) if file_id is not None else None
        async with semaphore:
            try:
                result = await download_file(client, record, attachments_dir, prev_updated_at)
            except Exception as exc:
                result = {
                    "status": "failed",
                    "path": str(attachments_dir / _local_filename(record)),
                    "reason": str(exc),
                }
        return {
            "file": record["display_name"],
            "source": "assignment_attachment",
            "assignment_name": assignment_name,
            **result,
        }

    used_names: set[str] = set()
    for assignment in assignments:
        assignment_dir = _assignment_directory(base_dir, assignment, used_names)
        attachment_records = await _assignment_linked_files(client, course["id"], assignment, concurrency=module_concurrency)
        assignment_attachments.extend(attachment_records)

        page_result = await _write_text_if_changed(
            assignment_dir / "assignment.html",
            _render_assignment_html(course, assignment),
        )
        downloads.append({
            "file": "assignment.html",
            "source": "assignment_page",
            "assignment_name": assignment["name"],
            **page_result,
        })

        if attachment_records:
            attachments_dir = ensure_directory(assignment_dir / "attachments")
            att_results = await asyncio.gather(
                *(download_attachment(r, attachments_dir, assignment["name"]) for r in attachment_records)
            )
            downloads.extend(att_results)

    metadata = {
        "course": {
            "id": course["id"],
            "name": course["name"],
            "course_code": course.get("course_code"),
            "subject": course.get("subject"),
            "term": course.get("term"),
        },
        "discovered": records,
        "assignments": assignments,
        "assignment_attachments": assignment_attachments,
        "downloads": downloads,
    }
    await asyncio.to_thread(write_json, base_dir / "_download_report.json", metadata)
    return metadata
