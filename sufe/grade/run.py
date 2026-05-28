from __future__ import annotations

import asyncio
from pathlib import Path
from typing import Any

from sufe.auth import create_session, load_credentials, login_service, login_sso
from sufe.config import EAMS_SERVICE_URL, GRADE_DIR
from sufe.grade.analyze import analyze_grades, export_csv, print_analysis
from sufe.grade.api import fetch_grades
from sufe.storage import write_json


async def _run(
    output_dir: Path,
    export_formats: list[str],
    generate_report: bool,
) -> dict[str, Any]:
    username, password = await load_credentials()

    async with create_session() as client:
        await login_sso(client, username, password)
        await login_service(client, EAMS_SERVICE_URL)

        data = await fetch_grades(client)

        output_dir.mkdir(parents=True, exist_ok=True)
        if "json" in export_formats:
            write_json(output_dir / "grades.json", data)
        if "csv" in export_formats:
            export_csv(data, output_dir)

        if generate_report:
            analysis = analyze_grades(data)
            print_analysis(analysis)

            summary = data.get("summary", {}).get("overall", {})
            print(f"\n=== Official Summary ===")
            print(f"Total courses: {summary.get('total_courses', 0)}")
            print(f"Total credits: {summary.get('total_credits', 0)}")
            print(f"Average grade: {summary.get('avg_grade', 0):.2f}")
            print(f"Average GPA: {summary.get('avg_gpa', 0):.2f}")

        return data


def run(
    output_dir: Path = GRADE_DIR,
    export_formats: list[str] | None = None,
    generate_report: bool = True,
) -> None:
    asyncio.run(_run(output_dir, export_formats or ["json", "csv"], generate_report))
