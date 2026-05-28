from __future__ import annotations

import csv
from pathlib import Path
from typing import Any


def _group_stats(courses: list[dict[str, Any]]) -> dict[str, Any]:
    if not courses:
        return {"count": 0, "avg_grade": 0.0, "avg_gpa": 0.0, "total_credits": 0.0}

    total_credits = sum(c["credits"] for c in courses)
    return {
        "count": len(courses),
        "avg_grade": round(sum(c["grade"] for c in courses) / len(courses), 2),
        "avg_gpa": round(sum(c["gpa"] * c["credits"] for c in courses) / total_credits, 2) if total_credits else 0.0,
        "total_credits": total_credits,
    }


def analyze_grades(data: dict[str, Any]) -> dict[str, Any]:
    all_grades = data.get("all_grades", [])
    if not all_grades:
        return {}

    total_courses = len(all_grades)
    total_credits = sum(g["credits"] for g in all_grades)
    avg_grade = round(sum(g["grade"] for g in all_grades) / total_courses, 2) if total_courses else 0
    avg_gpa = round(sum(g["gpa"] * g["credits"] for g in all_grades) / total_credits, 2) if total_credits else 0

    semesters: dict[str, list[dict]] = {}
    for g in all_grades:
        sem = g.get("semester", "Unknown")
        semesters.setdefault(sem, []).append(g)

    semester_details = {}
    for sem, courses in sorted(semesters.items()):
        semester_details[sem] = {
            "stats": _group_stats(courses),
            "courses": sorted(courses, key=lambda c: c["grade"], reverse=True),
        }

    return {
        "total_courses": total_courses,
        "total_credits": total_credits,
        "avg_grade": avg_grade,
        "avg_gpa": avg_gpa,
        "semester_details": semester_details,
    }


def export_csv(data: dict[str, Any], output_dir: Path) -> None:
    all_grades = data.get("all_grades", [])
    if not all_grades:
        return

    output_dir.mkdir(parents=True, exist_ok=True)
    csv_path = output_dir / "grades.csv"

    with open(csv_path, "w", newline="", encoding="utf-8-sig") as f:
        writer = csv.DictWriter(f, fieldnames=[
            "semester", "course_code", "course_seq", "course_name",
            "course_type", "credits", "grade", "final_grade", "gpa"
        ])
        writer.writeheader()
        writer.writerows(all_grades)


def print_analysis(analysis: dict[str, Any]) -> None:
    if not analysis:
        print("No data to analyze.")
        return

    print("\n" + "=" * 70)
    print("GRADE ANALYSIS REPORT")
    print("=" * 70)

    print(f"\n[Overall Summary]")
    print(f"  Total Courses: {analysis['total_courses']}")
    print(f"  Total Credits: {analysis['total_credits']}")
    print(f"  Average Grade: {analysis['avg_grade']:.2f}")
    print(f"  Weighted GPA: {analysis['avg_gpa']:.2f}")

    for sem, details in analysis["semester_details"].items():
        stats = details["stats"]
        courses = details["courses"]

        print(f"\n{'=' * 70}")
        print(f"[{sem}]")
        print(f"  Courses: {stats['count']} | Credits: {stats['total_credits']}")
        print(f"  Average: {stats['avg_grade']:.2f} | GPA: {stats['avg_gpa']:.2f}")
        print(f"{'=' * 70}")

        for course in courses:
            name = course["course_name"]
            ctype = course.get("course_type", "N/A")
            credits = course["credits"]
            grade = course["grade"]
            gpa = course["gpa"]

            print(f"\n  {name}")
            print(f"    Type: {ctype} | Credits: {credits:.1f} | Grade: {grade:.1f} | GPA: {gpa:.2f}")

    print("\n" + "=" * 70)
