from __future__ import annotations

import base64
from dataclasses import dataclass
from typing import Any
from urllib.parse import quote

import httpx
from Crypto.Cipher import PKCS1_v1_5
from Crypto.PublicKey import RSA

from sufe.config import (
    SSO_DO_LOGIN_URL,
    SSO_LOGIN_PAGE_URL,
    SSO_QUERY_ALL_VALID_URL,
    SSO_QUERY_USER_VALID_URL,
    SSO_SERVICE_LOGIN_URL,
    SSO_SLIDER_CHECK_URL,
    SSO_SLIDER_INIT_URL,
)


@dataclass
class SliderInit:
    token: str
    y: int


async def load_policy(client: httpx.AsyncClient) -> dict[str, Any]:
    await client.get(SSO_LOGIN_PAGE_URL)
    response = await client.get(SSO_QUERY_ALL_VALID_URL)
    response.raise_for_status()
    payload = response.json()
    data = payload.get("data")
    param = data.get("param") if isinstance(data, dict) else None
    if not isinstance(param, dict):
        raise RuntimeError(f"queryAllValid returned no param block: {payload}")
    if not param.get("publicKey") or not param.get("publicKeyId"):
        raise RuntimeError(f"queryAllValid returned no RSA policy: {payload}")
    return payload


async def load_auth_mode(client: httpx.AsyncClient, username: str) -> dict[str, Any]:
    response = await client.get(
        SSO_QUERY_USER_VALID_URL,
        params={"username": username, "authType": "webLocalAuth"},
    )
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "0":
        raise RuntimeError(f"queryUserValid failed: {payload}")
    return payload


async def _init_slider(client: httpx.AsyncClient) -> SliderInit:
    response = await client.post(SSO_SLIDER_INIT_URL, json={})
    response.raise_for_status()
    payload = response.json()
    if payload.get("code") != "0":
        raise RuntimeError(f"slider init failed: {payload}")
    data = payload.get("data")
    if not isinstance(data, dict):
        raise RuntimeError(f"slider init returned unexpected payload: {payload}")
    return SliderInit(token=str(data["token"]), y=int(data["Y"]))


async def solve_slider(client: httpx.AsyncClient, max_x: int = 500, attempts: int = 2) -> str:
    for _ in range(attempts):
        slider = await _init_slider(client)
        for x in range(max_x):
            try:
                response = await client.get(
                    SSO_SLIDER_CHECK_URL,
                    params={"token": slider.token, "X": x, "Y": slider.y},
                )
                response.raise_for_status()
                payload = response.json()
            except httpx.HTTPError:
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

    raise RuntimeError(f"slider check never succeeded after {attempts} attempts within X range 0..{max_x - 1}")


async def login_sso(client: httpx.AsyncClient, username: str, password: str) -> dict[str, Any]:
    policy = await load_policy(client)
    await load_auth_mode(client, username)
    vcode = await solve_slider(client)

    param = policy["data"]["param"]
    public_key = RSA.import_key(base64.b64decode(param["publicKey"]))
    cipher = PKCS1_v1_5.new(public_key)
    encrypted = base64.b64encode(cipher.encrypt(password.encode("utf-8"))).decode("ascii")

    payload = {
        "authType": "webLocalAuth",
        "dataField": {
            "username": username,
            "password": encrypted,
            "vcode": vcode,
            "publicKeyId": param["publicKeyId"],
        },
        "redirectUri": "",
    }
    response = await client.post(SSO_DO_LOGIN_URL, json=payload)
    response.raise_for_status()
    result = response.json()
    if result.get("code") != "0":
        raise RuntimeError(f"doLogin failed: {result}")
    return result


async def login_service(client: httpx.AsyncClient, service_url: str) -> httpx.Response:
    ticket_url = f"{SSO_SERVICE_LOGIN_URL}?service={quote(service_url, safe='')}"
    return await client.get(ticket_url)
