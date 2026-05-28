from __future__ import annotations

import asyncio
from collections import Counter
from pathlib import Path

from tqdm.asyncio import tqdm

from sufe.auth import create_session, load_credentials, login_sso
from sufe.canvas.api import download, load_courses, login
from sufe.config import (
    CANVAS_COURSE_CONCURRENCY,
    CANVAS_FILE_CONCURRENCY,
    CANVAS_MODULE_CONCURRENCY,
    DOWNLOAD_DIR,
)
from sufe.storage import ensure_directory


def run(
    output_dir: Path = DOWNLOAD_DIR,
    concurrency: int = CANVAS_COURSE_CONCURRENCY,
    file_concurrency: int = CANVAS_FILE_CONCURRENCY,
    module_concurrency: int = CANVAS_MODULE_CONCURRENCY,
) -> None:
    ensure_directory(output_dir)
    asyncio.run(_run(output_dir, concurrency, file_concurrency, module_concurrency))


async def _run(
    output_dir: Path,
    concurrency: int,
    file_concurrency: int,
    module_concurrency: int,
) -> None:
    username, password = await load_credentials()
    async with create_session() as client:
        print("[1/4] Logging into SUFE SSO...")
        await login_sso(client, username, password)

        print("[2/4] Establishing Canvas session...")
        final_url = await login(client)
        print(f"Canvas authenticated at: {final_url}")

        print("[3/4] Fetching course list...")
        courses = await load_courses(client)
        print(f"Found {len(courses)} courses")

        print("[4/4] Downloading course materials...")
        summary = Counter()
        semaphore = asyncio.Semaphore(concurrency)

        async def process_course(course: dict) -> tuple[str, dict | None, Exception | None]:
            async with semaphore:
                try:
                    metadata = await download(
                        client, course, output_dir, file_concurrency, module_concurrency
                    )
                    return course["name"], metadata, None
                except Exception as exc:
                    return course["name"], None, exc

        results = await tqdm.gather(
            *(process_course(c) for c in courses),
            desc="courses",
            unit="course",
            ascii=False,
        )

        for name, metadata, exc in results:
            if exc is not None:
                summary["failed_courses"] += 1
                print(f"  [FAIL] {name}: {exc}")
                continue
            if metadata is None:
                continue
            summary["discovered"] += (
                len(metadata["discovered"])
                + len(metadata.get("assignments", []))
                + len(metadata.get("assignment_attachments", []))
            )
            for item in metadata["downloads"]:
                summary[item["status"]] += 1
                if item.get("size_mismatch"):
                    summary["size_mismatch"] += 1
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
        print(f"Size mismatch: {summary.get('size_mismatch', 0)}")
