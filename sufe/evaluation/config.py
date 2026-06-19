from __future__ import annotations

EAMS_TCH_BASE = "https://eams.sufe.edu.cn/tch"

EVA_QUERY_ACTIVITY_BIZ = f"{EAMS_TCH_BASE}/cn.edu.sufe.tch.evaluationmgr.StudentEvaluationMgr.queryActivityByStuEva.biz.ext"
EVA_QUERY_DETAIL_BIZ = f"{EAMS_TCH_BASE}/cn.edu.sufe.tch.evaluationmgr.StudentEvaluationMgr.queryDetailInfo.biz.ext"
EVA_SAVE_BIZ = f"{EAMS_TCH_BASE}/cn.edu.sufe.tch.evaluationmgr.StudentEvaluationMgr.saveStudentEvaluationInfo.biz.ext"
EVA_SAVE_SORT_BIZ = f"{EAMS_TCH_BASE}/cn.edu.sufe.tch.evaluationmgr.StudentEvaluationMgr.saveEvaluateSortValue.biz.ext"
EVA_QUERY_SORT_STATUS_BIZ = f"{EAMS_TCH_BASE}/mobile.mobileEvaluation.queryStdSortFinishStatus.biz.ext"

EVA_QUERY_ACTIVITY_URL = f"{EAMS_TCH_BASE}/evaluationmgr/studentEvaluationMgr/queryActivityByStuEva.jsp"
EVA_QUERY_DETAIL_URL = f"{EAMS_TCH_BASE}/evaluationmgr/studentEvaluationMgr/queryDetailStuEva.jsp"

LEVEL_OPTIONS = {
    "excellent": "8a82a3a0607898c701608b29b7ee0643",
    "good": "8a82a3a0607898c701608b29b7eb0642",
    "fair": "8a82a3a0607898c701608b29b7e90641",
    "bad": "8a82a3a0607898c701608b29b7e70640",
    "poor": "8a82a3a0607898c701608b29b7da063f",
}
