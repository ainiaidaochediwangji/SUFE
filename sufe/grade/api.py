from __future__ import annotations

import re
from typing import Any

from bs4 import BeautifulSoup

from sufe.config import EAMS_GRADE_URL, EAMS_HISTORY_URL, EAMS_PROJECT_TYPE

WHITESPACE_RE = re.compile(r"\s+")


def _clean(text: str) -> str:
    return WHITESPACE_RE.sub(" ", text).strip()


def _parse_grade_table(html: str) -> list[dict[str, Any]]:
    soup = BeautifulSoup(html, "html.parser")
    table = soup.find("table", class_="gridtable")
    if not table:
        return []

    rows = table.find_all("tr")[1:]
    grades = []

    for row in rows:
        cells = row.find_all("td")
        if len(cells) < 9:
            continue

        grades.append({
            "semester": _clean(cells[0].get_text()),
            "course_code": _clean(cells[1].get_text()),
            "course_seq": _clean(cells[2].get_text()),
            "course_name": _clean(cells[3].get_text()),
            "course_type": _clean(cells[4].get_text()),
            "credits": float(_clean(cells[5].get_text()) or "0"),
            "grade": float(_clean(cells[6].get_text()) or "0"),
            "final_grade": float(_clean(cells[7].get_text()) or "0"),
            "gpa": float(_clean(cells[8].get_text()) or "0"),
        })

    return grades


def _parse_summary_table(html: str) -> dict[str, Any]:
    soup = BeautifulSoup(html, "html.parser")
    tables = soup.find_all("table", class_="gridtable")
    if not tables:
        return {}

    summary_table = tables[0]
    rows = summary_table.find_all("tr")[1:]

    semesters = []
    overall = {}

    for row in rows:
        cells = row.find_all(["td", "th"])
        if not cells:
            continue

        first_cell = cells[0]
        cell_text = _clean(first_cell.get_text())

        if first_cell.name == "th" and len(cells) < 6:
            if "汇总" in cell_text or "Summary" in cell_text:
                overall = {
                    "total_courses": sum(s["courses"] for s in semesters),
                    "avg_grade": float(_clean(cells[2].get_text()) or "0"),
                    "total_credits": float(_clean(cells[3].get_text()) or "0"),
                    "avg_gpa": float(_clean(cells[4].get_text()) or "0"),
                }
        elif first_cell.name == "td" and len(cells) >= 6:
            semesters.append({
                "year": _clean(cells[0].get_text()),
                "semester": _clean(cells[1].get_text()),
                "courses": int(_clean(cells[2].get_text()) or "0"),
                "avg_grade": float(_clean(cells[3].get_text()) or "0"),
                "total_credits": float(_clean(cells[4].get_text()) or "0"),
                "avg_gpa": float(_clean(cells[5].get_text()) or "0"),
            })

    return {"semesters": semesters, "overall": overall}


async def fetch_grades(client) -> dict[str, Any]:
    resp = await client.get(EAMS_GRADE_URL)
    resp.raise_for_status()
    current_grades = _parse_grade_table(resp.text)

    resp = await client.get(EAMS_HISTORY_URL, params={"projectType": EAMS_PROJECT_TYPE})
    resp.raise_for_status()

    summary = _parse_summary_table(resp.text)

    soup = BeautifulSoup(resp.text, "html.parser")
    tables = soup.find_all("table", class_="gridtable")
    all_grades = _parse_grade_table(str(tables[1])) if len(tables) > 1 else current_grades

    return {
        "current_semester": current_grades,
        "all_grades": all_grades,
        "summary": summary,
    }
