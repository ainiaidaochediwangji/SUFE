from __future__ import annotations

import asyncio
from typing import Any

from tqdm.asyncio import tqdm

from sufe.auth import create_session, load_credentials, login_service, login_sso
from sufe.evaluation.api import (
    fetch_questionnaire_html,
    option_values,
    parse_questionnaire,
    query_activities,
    query_detail_courses,
    query_sort_status,
    save_evaluation,
    save_sort_values,
)
from sufe.user_config import _load_yaml

_EVA_SERVICE_URL = "https://eams.sufe.edu.cn/tch/evaluationmgr/studentEvaluationMgr/queryActivityByStuEva.jsp"


async def _eval_one(client, course: dict[str, Any], act_id: str, level: str) -> dict[str, str]:
    name = course.get("TCONAME", "")
    teacher = course.get("CTENAME", "")
    tle = course["TLEID"]

    if course.get("IS_EVA_FINISH") == "1":
        return {"id": tle, "course": name, "teacher": teacher, "status": "skipped"}

    try:
        html = await fetch_questionnaire_html(client, course, act_id)
        parsed = parse_questionnaire(html)
        opts = option_values(len(parsed["question_ids"]), level)

        tedata = {
            "actId": parsed["act_id"],
            "questionnaireId": parsed["questionnaire_id"],
            "questionIdArrText": ",".join(parsed["question_ids"]),
            "optionIdArrText": ",".join(opts),
            "vdata": parsed["vdata"],
        }
        ok = await save_evaluation(client, tedata)
        status = "ok" if ok else "fail"
    except Exception as e:
        status = f"fail: {e}"

    return {"id": tle, "course": name, "teacher": teacher, "status": status}


async def run() -> list[dict[str, str]]:
    username, password = await load_credentials()
    cfg = _load_yaml().get("evaluation", {})
    level = cfg.get("level", "excellent")
    concurrency = cfg.get("concurrency", 4)

    async with create_session() as client:
        print("[1/4] Logging into SUFE SSO...")
        await login_sso(client, username, password)

        print("[2/4] Establishing EAMS session...")
        await login_service(client, _EVA_SERVICE_URL)

        print("[3/4] Fetching evaluation activities...")
        activities = await query_activities(client)
        if not activities:
            print("  No evaluation activities found.")
            return []

        act = activities[0]
        act_id: str = act["ID"]
        is_sort: str = act.get("IS_SORT", "0")
        print(f"  Activity: {act.get('ACT_NAME', '')} ({act_id})")
        print(f"  Requires sorting: {is_sort == '1'}")

        courses = await query_detail_courses(client, act_id)
        print(f"  Courses to process: {len(courses)}")

        if is_sort == "1":
            sort_status = await query_sort_status(client, act_id)
            if sort_status:
                print("  [sort] Already completed, skip")
            else:
                print("  [sort] Submitting course ranking...")
                ok = await save_sort_values(client, courses, act_id)
                print(f"  [sort] {'done' if ok else 'failed'}")

        semaphore = asyncio.Semaphore(concurrency)

        async def guarded(course):
            async with semaphore:
                return await _eval_one(client, course, act_id, level)

        results = await tqdm.gather(*(guarded(c) for c in courses), desc="evaluating", unit="course", ascii=False)

    done = sum(1 for r in results if r["status"] == "ok")
    skipped = sum(1 for r in results if r["status"] == "skipped")
    failed = sum(1 for r in results if r["status"].startswith("fail"))
    print(f"Done: {done}, Skipped: {skipped}, Failed: {failed}")
    for r in results:
        if r["status"].startswith("fail"):
            print(f"  FAIL: {r['course']} - {r['teacher']}: {r['status']}")

    return results
