from __future__ import annotations

import sys
from pathlib import Path
from collections import Counter

sys.dont_write_bytecode = True
sys.path.append(str((Path(__file__).resolve().parent / "src")))

from src.canvas_client import (
    download_course_materials,
    establish_canvas_session,
    get_dashboard_courses,
)
from src.config import DOWNLOAD_DIR
from src.fs_utils import ensure_directory
from src.sso import create_session, load_credentials, login_sso


def main() -> None:
    ensure_directory(DOWNLOAD_DIR)

    username, password = load_credentials()
    session = create_session()

    print("[1/4] Logging into SUFE SSO...")
    login_sso(session, username, password)

    print("[2/4] Establishing Canvas session...")
    final_url = establish_canvas_session(session)
    print(f"Canvas authenticated at: {final_url}")

    print("[3/4] Fetching course list...")
    courses = get_dashboard_courses(session)
    print(f"Found {len(courses)} courses")

    print("[4/4] Downloading course materials...")
    summary = Counter()
    for index, course in enumerate(courses, start=1):
        print(f"[{index}/{len(courses)}] {course['name']}")
        try:
            metadata = download_course_materials(session, course)
        except Exception as exc:
            summary["failed_courses"] += 1
            print(f"  Course failed: {exc}")
            continue
        summary["discovered"] += len(metadata["discovered"]) + len(metadata.get("assignments", [])) + len(metadata.get("assignment_attachments", []))
        for item in metadata["downloads"]:
            summary[item["status"]] += 1
            if item["status"] == "skipped" and item.get("reason") not in {"already_exists", "already_exists_unknown_size"}:
                print(f"  Skipped {item['file']}: {item.get('reason')}")
            if item["status"] == "failed":
                print(f"  Failed {item['file']}: {item.get('reason')}")
    print("Done")
    print(f"Courses: {len(courses)}")
    print(f"Course failures: {summary.get('failed_courses', 0)}")
    print(f"Discovered: {summary.get('discovered', 0)}")
    print(f"Downloaded: {summary.get('downloaded', 0)}")
    print(f"Skipped: {summary.get('skipped', 0)}")
    print(f"Failed: {summary.get('failed', 0)}")


if __name__ == "__main__":
    main()
