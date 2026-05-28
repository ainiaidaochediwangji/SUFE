from __future__ import annotations

import csv
import json
import os
import re
from pathlib import Path
from typing import Any

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


def write_json(path: Path, payload: Any) -> None:
    ensure_directory(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp.json")
    temp_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    os.replace(temp_path, path)


def read_json(path: Path, fallback: Any = None) -> Any:
    if not path.exists():
        return fallback
    return json.loads(path.read_text(encoding="utf-8"))


def write_csv(path: Path, rows: list[dict[str, Any]], fields: list[str], headers: list[str]) -> None:
    ensure_directory(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp.csv")
    with temp_path.open("w", encoding="utf-8-sig", newline="") as handle:
        writer = csv.writer(handle)
        writer.writerow(headers)
        for row in rows:
            writer.writerow([row.get(field) for field in fields])
    os.replace(temp_path, path)


def write_text(path: Path, text: str) -> None:
    ensure_directory(path.parent)
    temp_path = path.with_suffix(path.suffix + ".tmp.txt")
    temp_path.write_text(text, encoding="utf-8")
    os.replace(temp_path, path)
