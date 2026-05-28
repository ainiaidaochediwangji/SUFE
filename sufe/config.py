from __future__ import annotations

from pathlib import Path

from dotenv import dotenv_values

ROOT_DIR = Path(__file__).resolve().parent.parent
DOWNLOAD_DIR = ROOT_DIR / "course"
CAREER_DIR = ROOT_DIR / "career_data" / "sxzpxx"
GRADE_DIR = ROOT_DIR / "grade_data"
ENV_FILE = ROOT_DIR / ".env"

SSO_LOGIN_PAGE_URL = "https://login.sufe.edu.cn/login/"
SSO_QUERY_ALL_VALID_URL = "https://login.sufe.edu.cn/esc-sso/api/v3/auth/queryAllValid"
SSO_QUERY_USER_VALID_URL = "https://login.sufe.edu.cn/esc-sso/api/v3/auth/queryUserValid"
SSO_SLIDER_INIT_URL = "https://login.sufe.edu.cn/esc-sso/api/v3/sliderCaptcha/init"
SSO_SLIDER_CHECK_URL = "https://login.sufe.edu.cn/esc-sso/api/v3/sliderCaptcha/check"
SSO_DO_LOGIN_URL = "https://login.sufe.edu.cn/esc-sso/api/v3/auth/doLogin"
SSO_SERVICE_LOGIN_URL = "https://login.sufe.edu.cn/esc-sso/login"

CANVAS_BASE_URL = "https://canvas.shufe.edu.cn/"
CANVAS_CAS_LOGIN_URL = "https://canvas.shufe.edu.cn/login/cas"
CANVAS_API_ROOT = "https://canvas.shufe.edu.cn/api/v1"
CANVAS_COURSE_CONCURRENCY = 2
CANVAS_FILE_CONCURRENCY = 4
CANVAS_MODULE_CONCURRENCY = 8

CAREER_BASE_URL = "https://career.sufe.edu.cn/career"
CAREER_LIST_URL = f"{CAREER_BASE_URL}/zpxx/search/sxzpxx"
CAREER_DETAIL_URL = f"{CAREER_BASE_URL}/zpxx/data/zpxx"
CAREER_SERVICE_URL = "https://career.sufe.edu.cn/career/sso/shcjjy/login"
CAREER_PAGE_SIZE = 10
CAREER_MAX_ITEMS = 300
CAREER_CONCURRENCY = 8
CAREER_PAGE_CONCURRENCY = 3

EAMS_BASE_URL = "https://eams.sufe.edu.cn/eams"
EAMS_SERVICE_URL = f"{EAMS_BASE_URL}/home.action"
EAMS_GRADE_URL = f"{EAMS_BASE_URL}/teach/grade/course/person!search.action"
EAMS_HISTORY_URL = f"{EAMS_BASE_URL}/teach/grade/course/person!historyCourseGrade.action"
EAMS_PROJECT_TYPE = "MAJOR"

DEFAULT_HEADERS = {
    "User-Agent": ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) " "AppleWebKit/537.36 (KHTML, like Gecko) " "Chrome/135.0.0.0 Safari/537.36"),
    "Accept-Language": "zh-CN,zh;q=0.9,en;q=0.8",
    "Accept": "application/json, text/plain, */*",
}

HTML_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
}

JSON_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "application/json, text/plain, */*",
    "X-Requested-With": "XMLHttpRequest",
}

FILE_HEADERS = {
    **DEFAULT_HEADERS,
    "Accept": "*/*",
}


def load_env() -> dict[str, str]:
    values = dotenv_values(ENV_FILE)
    return {str(key): str(value) for key, value in values.items() if value is not None}
