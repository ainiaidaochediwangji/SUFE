from __future__ import annotations

import json
import re
from pathlib import Path

INVALID_CHARS = re.compile(r'[<>:"/\\|?*\x00-\x1f]')
WHITESPACE = re.compile(r"\s+")
WINDOWS_RESERVED_NAMES = {
    "CON",
    "PRN",
    "AUX",
    "NUL",
    *(f"COM{index}" for index in range(1, 10)),
    *(f"LPT{index}" for index in range(1, 10)),
}


def sanitize_name(name: str, fallback: str = "unnamed") -> str:
    cleaned = INVALID_CHARS.sub("_", str(name)).strip().rstrip(".")
    cleaned = WHITESPACE.sub(" ", cleaned)
    if cleaned.upper() in WINDOWS_RESERVED_NAMES:
        cleaned = f"_{cleaned}"
    return cleaned or fallback


def ensure_directory(path: Path) -> Path:
    path.mkdir(parents=True, exist_ok=True)
    return path


def course_directory(download_root: Path, course: dict) -> Path:
    subject = sanitize_name(course.get("subject") or course.get("course_code") or course["name"])
    course_name = sanitize_name(course["name"])
    if subject == course_name:
        return ensure_directory(download_root / course_name)
    return ensure_directory(download_root / subject / course_name)


def unique_target_path(path: Path) -> Path:
    if not path.exists():
        return path
    stem = path.stem
    suffix = path.suffix
    counter = 1
    while True:
        candidate = path.with_name(f"{stem} ({counter}){suffix}")
        if not candidate.exists():
            return candidate
        counter += 1


def write_json(path: Path, payload: dict) -> None:
    ensure_directory(path.parent)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
