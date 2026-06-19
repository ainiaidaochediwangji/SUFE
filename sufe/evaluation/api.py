from __future__ import annotations

import json
from html import unescape
from re import findall, search
from typing import Any
from urllib.parse import quote

import httpx

from sufe.evaluation.config import (
    EVA_QUERY_ACTIVITY_BIZ,
    EVA_QUERY_ACTIVITY_URL,
    EVA_QUERY_DETAIL_BIZ,
    EVA_QUERY_DETAIL_URL,
    EVA_QUERY_SORT_STATUS_BIZ,
    EVA_SAVE_BIZ,
    EVA_SAVE_SORT_BIZ,
    LEVEL_OPTIONS,
)


def option_values(count: int, level: str) -> list[str]:
    opt = LEVEL_OPTIONS.get(level)
    if opt is None:
        raise ValueError(f"unknown level: {level!r}, choose from {list(LEVEL_OPTIONS)}")
    return [opt] * count


async def query_activities(client: httpx.AsyncClient) -> list[dict[str, Any]]:
    await client.get(EVA_QUERY_ACTIVITY_URL)
    payload = {"isQ": "0", "pageIndex": 0, "pageSize": 30, "page": {"begin": 0, "length": 30}}
    resp = await client.post(EVA_QUERY_ACTIVITY_BIZ, json=payload)
    resp.raise_for_status()
    return resp.json().get("rtndata", [])


async def query_detail_courses(client: httpx.AsyncClient, act_id: str) -> list[dict[str, Any]]:
    await client.get(EVA_QUERY_DETAIL_URL, params={"actId": act_id, "isSort": "1", "isHis": "0", "actdesc": ""})
    payload = {"actId": act_id, "pageIndex": 0, "pageSize": 30, "page": {"begin": 0, "length": 30}}
    resp = await client.post(EVA_QUERY_DETAIL_BIZ, json=payload)
    resp.raise_for_status()
    return resp.json().get("data", [])


async def fetch_questionnaire_html(client: httpx.AsyncClient, course: dict[str, Any], act_id: str) -> str:
    vdata = quote(json.dumps(course, ensure_ascii=False), safe="")
    url = (
        "/tch/cn.edu.sufe.tch.evaluationmgr.studentEvaluationInfo.flow"
        f"?vdata={vdata}&actId={act_id}"
        "&url=/evaluationmgr/studentEvaluationMgr/studentEvaluation.jsp"
    )
    resp = await client.get(f"https://eams.sufe.edu.cn{url}")
    resp.raise_for_status()
    return resp.text


def parse_questionnaire(html: str) -> dict[str, Any]:
    m = search(r'id="questionnaireId1"\s+value="([^"]+)"', html)
    questionnaire_id = m.group(1) if m else ""
    m = search(r'id="actId1"\s+value="([^"]+)"', html)
    act_id = m.group(1) if m else ""
    m = search(r'id="vdata1"\s+value="([^"]+)"', html)
    vdata = unescape(m.group(1)) if m else ""
    question_ids = findall(r'<input\s+type="hidden"\s+name="questionId1"\s+value="([^"]+)"', html)
    return {"questionnaire_id": questionnaire_id, "act_id": act_id, "vdata": vdata, "question_ids": question_ids}


async def save_evaluation(client: httpx.AsyncClient, tedata: dict[str, Any]) -> bool:
    resp = await client.post(EVA_SAVE_BIZ, json={"tedata": tedata})
    resp.raise_for_status()
    return resp.json().get("rtn") == "0"


# ── 排序打分 ──


async def query_sort_status(client: httpx.AsyncClient, act_id: str) -> bool:
    resp = await client.post(EVA_QUERY_SORT_STATUS_BIZ, json={"actId": act_id})
    resp.raise_for_status()
    data = resp.json()
    return data.get("isFinish") == "1"


async def save_sort_values(
    client: httpx.AsyncClient,
    courses: list[dict[str, Any]],
    act_id: str,
) -> bool:
    sorted_courses = sorted(courses, key=lambda c: float(c.get("SCORE", 0) or 0), reverse=True)
    sort_values = [str(i + 1) for i in range(len(sorted_courses))]
    sort_ids = [c["SORTID"] for c in sorted_courses]

    tedata = {
        "vdata": sorted_courses,
        "sortId0": sort_ids[0],
        "sortvalues": ",".join(sort_values),
    }
    resp = await client.post(EVA_SAVE_SORT_BIZ, json=tedata)
    resp.raise_for_status()
    result = resp.json()
    return result.get("rtn") in ("0", "2")


__all__ = [
    "option_values",
    "query_activities",
    "query_detail_courses",
    "fetch_questionnaire_html",
    "parse_questionnaire",
    "save_evaluation",
    "query_sort_status",
    "save_sort_values",
]
