from __future__ import annotations

import asyncio

from sufe.evaluation.run import run as _run


def run() -> None:
    asyncio.run(_run())
