from __future__ import annotations

import asyncio

from sufe.config import load_env


async def load_credentials() -> tuple[str, str]:
    env = await asyncio.to_thread(load_env)
    username = env.get("user", "").strip()
    password = env.get("pwd", "")
    if not username or not password:
        raise RuntimeError("Missing user or pwd in .env")
    return username, password
