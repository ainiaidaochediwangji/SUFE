from __future__ import annotations

import html
import json
import re
import time
from pathlib import Path
from typing import Any, Iterator
from urllib.parse import quote, urlparse

import requests

from config import (
    CANVAS_API_ROOT,
    CANVAS_BASE_URL,
    CANVAS_CAS_LOGIN_URL,
    DOWNLOAD_DIR,
    FILE_HEADERS,
    HTML_HEADERS,
    JSON_HEADERS,
    SSO_SERVICE_LOGIN_URL,
)
from fs_utils import course_directory, ensure_directory, sanitize_name, write_json

COURSE_CODE_PATTERN = re.compile(r"^[A-Za-z]{2,}[A-Za-z0-9_-]*\d+[A-Za-z0-9_-]*$")
ENV_JSON_PATTERN = re.compile(r"ENV = (\{.*?\});", re.DOTALL)
ASSIGNMENT_API_ENDPOINT_PATTERN = re.compile(r'data-api-endpoint="([^"]*?/api/v1/(?:courses/\d+/)?files/\d+)"')
ASSIGNMENT_COURSE_FILE_PATTERN = re.compile(r"/courses/(\d+)/files/(\d+)")
ASSIGNMENT_GLOBAL_FILE_PATTERN = re.compile(r"/files/(\d+)/download")
VIEWER_PREVIEW_SRC_PATTERN = re.compile(r'src="/(preview/\d+\.[A-Za-z0-9]+)"')


def _html_get(session: requests.Session, url: str, **kwargs: Any) -> requests.Response:
    headers = {**HTML_HEADERS, **kwargs.pop("headers", {})}
    response = session.get(url, headers=headers, timeout=60, **kwargs)
    response.raise_for_status()
    return response


def _json_get(session: requests.Session, url: str, **kwargs: Any) -> requests.Response:
    headers = {**JSON_HEADERS, **kwargs.pop("headers", {})}
    response = session.get(url, headers=headers, timeout=60, **kwargs)
    response.raise_for_status()
    return response


def _canvas_service_login_url() -> str:
    return f"{SSO_SERVICE_LOGIN_URL}?service={quote(CANVAS_CAS_LOGIN_URL, safe='')}"


def _is_canvas_host(url: str) -> bool:
    return urlparse(url).netloc.lower() == "canvas.shufe.edu.cn"


def _canvas_api_ready(session: requests.Session) -> bool:
    response = session.get(
        f"{CANVAS_API_ROOT}/courses",
        params={"per_page": 1},
        headers=JSON_HEADERS,
        timeout=60,
    )
    return response.status_code == 200


def establish_canvas_session(session: requests.Session) -> str:
    initial = _html_get(session, CANVAS_BASE_URL, allow_redirects=True)
    if _is_canvas_host(initial.url) and _canvas_api_ready(session):
        return initial.url

    service_response = _html_get(session, _canvas_service_login_url(), allow_redirects=True)
    if not _is_canvas_host(service_response.url):
        raise RuntimeError(f"Canvas CAS handoff did not finish on Canvas: {service_response.url}")
    if not _canvas_api_ready(session):
        raise RuntimeError(f"Canvas page loaded but API is still unauthorized: {service_response.url}")
    return service_response.url


def _paginate(session: requests.Session, url: str, params: dict[str, Any] | None = None) -> Iterator[Any]:
    next_url = url
    next_params = params or {}
    while next_url:
        response = session.get(next_url, params=next_params, headers=JSON_HEADERS, timeout=60)
        if response.status_code == 401:
            raise RuntimeError(f"Canvas API request was unauthorized: {next_url}")
        response.raise_for_status()
        data = response.json()
        if isinstance(data, list):
            yield from data
        else:
            yield data
        next_url = response.links.get("next", {}).get("url")
        next_params = {}


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
        if COURSE_CODE_PATTERN.match(token):
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
        "raw": raw,
    }
    normalized["subject"] = _extract_subject(normalized | raw)
    term = raw.get("term")
    if isinstance(term, dict):
        normalized["term"] = term.get("name")
    elif raw.get("term"):
        normalized["term"] = raw.get("term")
    return normalized


def _courses_from_api(session: requests.Session) -> list[dict[str, Any]]:
    params = {
        "enrollment_state": ["active", "completed", "invited_or_pending_creation"],
        "include[]": ["term", "favorites", "teachers"],
        "per_page": 100,
    }
    seen: set[int] = set()
    courses: list[dict[str, Any]] = []
    for raw in _paginate(session, f"{CANVAS_API_ROOT}/courses", params=params):
        if not isinstance(raw, dict) or "id" not in raw:
            continue
        course_id = int(raw["id"])
        if course_id in seen:
            continue
        seen.add(course_id)
        courses.append(_normalize_course_record(raw))
    return courses


def _courses_from_dashboard_html(session: requests.Session) -> list[dict[str, Any]]:
    response = _html_get(session, CANVAS_BASE_URL, allow_redirects=True)
    if not _is_canvas_host(response.url):
        raise RuntimeError(f"Dashboard HTML fallback landed off Canvas: {response.url}")

    match = ENV_JSON_PATTERN.search(response.text)
    if not match:
        raise RuntimeError("Could not locate Canvas ENV payload in dashboard HTML")
    env_payload = json.loads(match.group(1))
    planner_courses = env_payload.get("STUDENT_PLANNER_COURSES") or []
    return [_normalize_course_record(course) for course in planner_courses if isinstance(course, dict) and course.get("id")]


def get_dashboard_courses(session: requests.Session) -> list[dict[str, Any]]:
    api_error: Exception | None = None
    try:
        courses = _courses_from_api(session)
        if courses:
            return courses
        api_error = RuntimeError("Canvas API returned no courses")
    except Exception as exc:
        api_error = exc

    html_courses = _courses_from_dashboard_html(session)
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
        "raw": raw,
    }


def _local_filename_for_record(record: dict[str, Any]) -> str:
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
        "raw": raw,
    }


def _course_files(session: requests.Session, course_id: int) -> list[dict[str, Any]]:
    raw_items = [
        item
        for item in _paginate(session, f"{CANVAS_API_ROOT}/courses/{course_id}/files", params={"per_page": 100})
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
        for item in _paginate(
            session,
            f"{CANVAS_API_ROOT}/folders/{folder_id}/files",
            params={
                "include[]": ["user", "usage_rights", "enhanced_preview_url", "context_asset_string"],
                "per_page": 100,
            },
        ):
            if not isinstance(item, dict) or not item.get("id"):
                continue
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


def _course_assignments(session: requests.Session, course_id: int) -> list[dict[str, Any]]:
    return [
        _normalize_assignment_record(item)
        for item in _paginate(
            session,
            f"{CANVAS_API_ROOT}/courses/{course_id}/assignments",
            params={"per_page": 100},
        )
        if isinstance(item, dict) and item.get("id")
    ]


def _module_files(session: requests.Session, course_id: int) -> list[dict[str, Any]]:
    modules = list(
        _paginate(
            session,
            f"{CANVAS_API_ROOT}/courses/{course_id}/modules",
            params={"per_page": 100},
        )
    )
    discovered: list[dict[str, Any]] = []
    for module in modules:
        if not isinstance(module, dict):
            continue
        module_id = module.get("id")
        module_name = module.get("name") or f"module-{module_id}"
        if not module_id:
            continue
        items = _paginate(
            session,
            f"{CANVAS_API_ROOT}/courses/{course_id}/modules/{module_id}/items",
            params={"per_page": 100},
        )
        for item in items:
            if not isinstance(item, dict) or item.get("type") != "File":
                continue
            content_id = item.get("content_id")
            if not content_id:
                continue
            try:
                file_payload = _json_get(session, f"{CANVAS_API_ROOT}/files/{content_id}").json()
            except requests.RequestException:
                continue
            discovered.append(_normalize_file_record(file_payload, source="modules", module_name=str(module_name)))
    return discovered


def discover_course_materials(session: requests.Session, course: dict[str, Any]) -> list[dict[str, Any]]:
    files = _course_files(session, course["id"])
    module_files = _module_files(session, course["id"])
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
    folder_name = base_name
    if folder_name in used_names:
        folder_name = sanitize_name(f"{assignment['name']} ({assignment['id']})")
    used_names.add(folder_name)
    return ensure_directory(base_dir / "assignments" / folder_name)


def _write_text_if_changed(path: Path, content: str) -> dict[str, Any]:
    ensure_directory(path.parent)
    if path.exists():
        existing = path.read_text(encoding="utf-8")
        if existing == content:
            return {"status": "skipped", "path": str(path), "reason": "already_exists"}
    path.write_text(content, encoding="utf-8")
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

    for url in ASSIGNMENT_API_ENDPOINT_PATTERN.findall(description_html):
        if url.startswith("/"):
            url = f"{CANVAS_BASE_URL.rstrip('/')}{url}"
        urls.add(url)

    for match in ASSIGNMENT_COURSE_FILE_PATTERN.finditer(description_html):
        matched_course_id, file_id = match.groups()
        urls.add(f"{CANVAS_API_ROOT}/courses/{matched_course_id}/files/{file_id}")

    for match in ASSIGNMENT_GLOBAL_FILE_PATTERN.finditer(description_html):
        file_id = match.group(1)
        urls.add(f"{CANVAS_API_ROOT}/files/{file_id}")

    # Some assignment descriptions point at wrapped file previews rather than an
    # explicit API endpoint; fall back to the current course when needed.
    if not urls and "/files/" in description_html:
        for match in re.finditer(r"/files/(\d+)", description_html):
            file_id = match.group(1)
            urls.add(f"{CANVAS_API_ROOT}/courses/{course_id}/files/{file_id}")

    return sorted(urls)


def _assignment_linked_files(
    session: requests.Session,
    course_id: int,
    assignment: dict[str, Any],
) -> list[dict[str, Any]]:
    discovered: list[dict[str, Any]] = []
    seen_ids: set[int] = set()
    for api_url in _assignment_file_api_urls(course_id, assignment.get("description") or ""):
        try:
            payload = _json_get(session, api_url).json()
        except requests.RequestException:
            continue
        if not isinstance(payload, dict) or not payload.get("id"):
            continue
        file_id = int(payload["id"])
        if file_id in seen_ids:
            continue
        seen_ids.add(file_id)
        discovered.append(
            _normalize_file_record(
                payload,
                source="assignments",
                module_name=assignment["name"],
            )
        )
    return discovered


def _download_assignment_content(
    session: requests.Session,
    course: dict[str, Any],
    assignment: dict[str, Any],
    assignment_dir: Path,
    attachment_records: list[dict[str, Any]],
) -> list[dict[str, Any]]:
    downloads: list[dict[str, Any]] = []

    page_result = _write_text_if_changed(
        assignment_dir / "assignment.html",
        _render_assignment_html(course, assignment),
    )
    downloads.append(
        {
            "file": "assignment.html",
            "source": "assignment_page",
            "assignment_name": assignment["name"],
            **page_result,
        }
    )

    attachments_dir = ensure_directory(assignment_dir / "attachments")
    for record in attachment_records:
        target_filename = _local_filename_for_record(record)
        try:
            result = download_file(session, record, attachments_dir)
        except Exception as exc:
            result = {
                "status": "failed",
                "path": str(attachments_dir / target_filename),
                "reason": str(exc),
            }
        downloads.append(
            {
                "file": record["display_name"],
                "source": "assignment_attachment",
                "assignment_name": assignment["name"],
                **result,
            }
        )

    return downloads


def _preview_download_url(session: requests.Session, record: dict[str, Any]) -> str | None:
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
            viewer_response = session.get(viewer_url, headers=HTML_HEADERS, timeout=60, allow_redirects=True)
            viewer_response.raise_for_status()
            match = VIEWER_PREVIEW_SRC_PATTERN.search(viewer_response.text)
            if match:
                return f"{CANVAS_BASE_URL.rstrip('/')}/{match.group(1)}"
        except requests.RequestException:
            pass

        preview_path = urlparse(preview_url).path
        match = re.search(r"/files/(\d+)/file_preview$", preview_path)
        if match:
            file_id = match.group(1)

    return f"{CANVAS_BASE_URL.rstrip('/')}/preview/{file_id}{suffix}"


def _warm_preview(session: requests.Session, record: dict[str, Any], attempts: int = 4, wait_seconds: float = 2.0) -> None:
    file_id = record.get("id")
    if not file_id:
        return

    preview_page_url = str(record.get("preview_url") or "").strip()
    if preview_page_url:
        if preview_page_url.startswith("/"):
            preview_page_url = f"{CANVAS_BASE_URL.rstrip('/')}{preview_page_url}"
        try:
            session.get(preview_page_url, headers=HTML_HEADERS, timeout=60, allow_redirects=True)
        except requests.RequestException:
            pass

    state_url = f"{CANVAS_BASE_URL.rstrip('/')}/viewer/{file_id}/state"
    for _ in range(attempts):
        try:
            response = session.get(state_url, headers=JSON_HEADERS, timeout=60)
            response.raise_for_status()
            payload = response.json()
        except (requests.RequestException, ValueError):
            time.sleep(wait_seconds)
            continue

        if str(payload.get("state")) == "1":
            return
        time.sleep(wait_seconds)


def _preview_state(session: requests.Session, file_id: Any) -> str | None:
    try:
        response = session.get(
            f"{CANVAS_BASE_URL.rstrip('/')}/viewer/{file_id}/state",
            headers=JSON_HEADERS,
            timeout=60,
        )
        response.raise_for_status()
        payload = response.json()
    except (requests.RequestException, ValueError):
        return None
    state = payload.get("state")
    return None if state is None else str(state)


def download_file(session: requests.Session, file_record: dict[str, Any], target_dir: Path) -> dict[str, Any]:
    ensure_directory(target_dir)
    filename = _local_filename_for_record(file_record)
    target_path = target_dir / filename
    expected_size = file_record.get("size")
    if isinstance(expected_size, str) and expected_size.isdigit():
        expected_size = int(expected_size)

    if target_path.exists():
        if expected_size is not None and target_path.stat().st_size == expected_size:
            return {"status": "skipped", "path": str(target_path), "reason": "already_exists"}
        if expected_size is None:
            return {"status": "skipped", "path": str(target_path), "reason": "already_exists_unknown_size"}

    download_candidates: list[tuple[str, str]] = []
    download_url = str(file_record.get("url") or "").strip()
    if download_url:
        download_candidates.append(("direct", download_url))

    preview_download_url = _preview_download_url(session, file_record)
    if preview_download_url:
        download_candidates.append(("preview", preview_download_url))

    if not download_candidates:
        lock_explanation = file_record.get("lock_explanation") or ""
        if file_record.get("locked_for_user") or lock_explanation:
            return {
                "status": "skipped",
                "path": str(target_path),
                "reason": lock_explanation or "locked_for_user",
            }
        return {"status": "failed", "path": str(target_path), "reason": "missing_download_url"}

    last_error: Exception | None = None
    for candidate_name, candidate_url in download_candidates:
        candidate_attempts = 6 if candidate_name == "preview" else 3
        for attempt in range(candidate_attempts):
            response: requests.Response | None = None
            try:
                if candidate_name == "preview":
                    _warm_preview(session, file_record)
                response = session.get(
                    candidate_url,
                    headers=FILE_HEADERS,
                    stream=True,
                    timeout=(30, 300),
                )
                response.raise_for_status()
                with target_path.open("wb") as handle:
                    for chunk in response.iter_content(chunk_size=1024 * 128):
                        if chunk:
                            handle.write(chunk)
                break
            except requests.RequestException as exc:
                last_error = exc
                if target_path.exists():
                    target_path.unlink()
                preview_state = None
                if candidate_name == "preview":
                    preview_state = _preview_state(session, file_record.get("id"))
                if attempt == candidate_attempts - 1:
                    if candidate_name == download_candidates[-1][0]:
                        raise
                if candidate_name == "preview" and preview_state == "0":
                    time.sleep(5.0 * (attempt + 1))
                else:
                    time.sleep(2.0 * (attempt + 1))
            finally:
                if response is not None:
                    response.close()
        else:
            continue
        break
    else:
        if last_error is not None:
            raise last_error

    if expected_size is not None and target_path.stat().st_size != expected_size:
        raise RuntimeError(f"downloaded size mismatch for {filename}: " f"expected {expected_size}, got {target_path.stat().st_size}")

    return {"status": "downloaded", "path": str(target_path), "size": target_path.stat().st_size}


def download_course_materials(session: requests.Session, course: dict[str, Any]) -> dict[str, Any]:
    base_dir = course_directory(DOWNLOAD_DIR, course)
    records = discover_course_materials(session, course)
    assignments = _course_assignments(session, course["id"])
    assignment_attachments: list[dict[str, Any]] = []
    downloads: list[dict[str, Any]] = []
    for record in records:
        target_dir = _target_dir_for_record(base_dir, record)
        target_filename = _local_filename_for_record(record)
        try:
            result = download_file(session, record, target_dir)
        except Exception as exc:
            result = {
                "status": "failed",
                "path": str(target_dir / target_filename),
                "reason": str(exc),
            }
        downloads.append(
            {
                "file": record["display_name"],
                "source": record["source"],
                "module_name": record.get("module_name"),
                **result,
            }
        )

    used_assignment_names: set[str] = set()
    for assignment in assignments:
        assignment_dir = _assignment_directory(base_dir, assignment, used_assignment_names)
        attachment_records = _assignment_linked_files(session, course["id"], assignment)
        assignment_attachments.extend(attachment_records)
        downloads.extend(
            _download_assignment_content(
                session,
                course,
                assignment,
                assignment_dir,
                attachment_records,
            )
        )

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
    write_json(base_dir / "_download_report.json", metadata)
    return metadata
