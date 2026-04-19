from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any

import requests
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from config import (
    SSO_DO_LOGIN_URL,
    SSO_LOGIN_PAGE_URL,
    SSO_QUERY_ALL_VALID_URL,
    SSO_QUERY_USER_VALID_URL,
    SSO_SLIDER_CHECK_URL,
    SSO_SLIDER_INIT_URL,
    create_browser_session,
    load_env,
)


@dataclass
class SliderInit:
    token: str
    y: int
    source_image_b64: str
    puzzle_image_b64: str


def load_credentials() -> tuple[str, str]:
    env = load_env()
    username = env.get("user", "").strip()
    password = env.get("pwd", "")
    if not username or not password:
        raise RuntimeError("Missing user or pwd in .env")
    return username, password


def create_session() -> requests.Session:
    session = create_browser_session()
    session.headers.update(
        {
            "Referer": SSO_LOGIN_PAGE_URL,
            "Origin": "https://login.sufe.edu.cn",
        }
    )
    return session


def get_login_policy(session: requests.Session) -> dict[str, Any]:
    session.get(SSO_LOGIN_PAGE_URL, timeout=30)
    response = session.get(SSO_QUERY_ALL_VALID_URL, timeout=30)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data")
    param = data.get("param") if isinstance(data, dict) else None
    if not isinstance(param, dict):
        raise RuntimeError(f"queryAllValid returned no param block: {payload}")
    if not param.get("publicKey") or not param.get("publicKeyId"):
        raise RuntimeError(f"queryAllValid returned no RSA policy: {payload}")
    return payload


def get_user_auth_mode(session: requests.Session, username: str) -> dict[str, Any]:
    response = session.get(
        SSO_QUERY_USER_VALID_URL,
        params={"username": username, "authType": "webLocalAuth"},
        timeout=30,
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "0":
        raise RuntimeError(f"queryUserValid failed: {payload}")
    return payload


def _init_slider(session: requests.Session) -> SliderInit:
    response = session.post(SSO_SLIDER_INIT_URL, json={}, timeout=30)
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "0":
        raise RuntimeError(f"slider init failed: {payload}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"slider init returned unexpected payload: {payload}")
    return SliderInit(
        token=str(data["token"]),
        y=int(data["Y"]),
        source_image_b64=str(data.get("sourceImage") or ""),
        puzzle_image_b64=str(data.get("newImage") or ""),
    )


def solve_slider(session: requests.Session, max_x: int = 500, captcha_attempts: int = 2) -> str:
    # The live site accepts a straightforward integer scan on X, and this
    # sequence is already validated for the current deployment.
    for _ in range(captcha_attempts):
        slider = _init_slider(session)
        for x in range(max_x):
            try:
                response = session.get(
                    SSO_SLIDER_CHECK_URL,
                    params={"token": slider.token, "X": x, "Y": slider.y},
                    timeout=30,
                )
                response.raise_for_status()
                payload = response.json()
            except requests.RequestException:
                continue
            if payload.get("code") != "0":
                continue

            data = payload.get("data")
            if isinstance(data, str) and data:
                return data
            if isinstance(data, dict):
                vcode = data.get("vcode") or data.get("captcha") or data.get("token")
                if vcode:
                    return str(vcode)
            raise RuntimeError(f"slider check succeeded but returned no vcode: {payload}")

    raise RuntimeError(f"slider check never succeeded after {captcha_attempts} attempts within X range 0..{max_x - 1}")


def encrypt_password(password: str, public_key_b64: str) -> str:
    public_key = RSA.import_key(base64.b64decode(public_key_b64))
    cipher = PKCS1_v1_5.new(public_key)
    encrypted = cipher.encrypt(password.encode("utf-8"))
    return base64.b64encode(encrypted).decode("ascii")


def login_sso(session: requests.Session, username: str, password: str) -> dict[str, Any]:
    policy = get_login_policy(session)
    get_user_auth_mode(session, username)
    vcode = solve_slider(session)

    param = policy["data"]["param"]
    encrypted_password = encrypt_password(password, param["publicKey"])

    payload = {
        "authType": "webLocalAuth",
        "dataField": {
            "username": username,
            "password": encrypted_password,
            "vcode": vcode,
            "publicKeyId": param["publicKeyId"],
        },
        "redirectUri": "",
    }
    response = session.post(SSO_DO_LOGIN_URL, json=payload, timeout=30)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != "0":
        raise RuntimeError(f"doLogin failed: {result}")
    return result
