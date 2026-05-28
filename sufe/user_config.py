from __future__ import annotations

from pathlib import Path
from typing import Any

import yaml

from sufe.config import (
    CANVAS_COURSE_CONCURRENCY,
    CANVAS_FILE_CONCURRENCY,
    CANVAS_MODULE_CONCURRENCY,
    CAREER_CONCURRENCY,
    CAREER_DIR,
    CAREER_MAX_ITEMS,
    CAREER_PAGE_CONCURRENCY,
    DOWNLOAD_DIR,
    GRADE_DIR,
    ROOT_DIR,
)

CONFIG_FILE = ROOT_DIR / "sufe.yaml"

_yaml_cache: dict[str, Any] | None = None


def _load_yaml() -> dict[str, Any]:
    global _yaml_cache
    if _yaml_cache is not None:
        return _yaml_cache
    if not CONFIG_FILE.exists():
        _yaml_cache = {}
    else:
        with open(CONFIG_FILE, "r", encoding="utf-8") as f:
            _yaml_cache = yaml.safe_load(f) or {}
    return _yaml_cache


def _resolve_path(path_str: str | None, default: Path) -> Path:
    if not path_str:
        return default
    path = Path(path_str)
    if not path.is_absolute():
        path = ROOT_DIR / path
    return path


def _first(cli: Any, cfg: Any, default: Any) -> Any:
    if cli is not None:
        return cli
    if cfg is not None:
        return cfg
    return default


def get_canvas_config(cli_args: dict[str, Any]) -> dict[str, Any]:
    cfg = _load_yaml().get("canvas", {})
    return {
        "output_dir": _first(
            cli_args.get("output_dir"),
            _resolve_path(cfg.get("output_dir"), DOWNLOAD_DIR) if cfg.get("output_dir") else None,
            DOWNLOAD_DIR,
        ),
        "concurrency": _first(cli_args.get("concurrency"), cfg.get("concurrency"), CANVAS_COURSE_CONCURRENCY),
        "file_concurrency": _first(cli_args.get("file_concurrency"), cfg.get("file_concurrency"), CANVAS_FILE_CONCURRENCY),
        "module_concurrency": _first(cli_args.get("module_concurrency"), cfg.get("module_concurrency"), CANVAS_MODULE_CONCURRENCY),
    }


def get_career_config(cli_args: dict[str, Any]) -> dict[str, Any]:
    cfg = _load_yaml().get("career", {})
    return {
        "output_dir": _first(
            cli_args.get("output_dir"),
            _resolve_path(cfg.get("output_dir"), CAREER_DIR) if cfg.get("output_dir") else None,
            CAREER_DIR,
        ),
        "concurrency": _first(cli_args.get("concurrency"), cfg.get("concurrency"), CAREER_CONCURRENCY),
        "page_concurrency": _first(cli_args.get("page_concurrency"), cfg.get("page_concurrency"), CAREER_PAGE_CONCURRENCY),
        "max_items": _first(cli_args.get("max_items"), cfg.get("max_items"), CAREER_MAX_ITEMS),
    }


def get_grade_config(cli_args: dict[str, Any]) -> dict[str, Any]:
    cfg = _load_yaml().get("grade", {})
    return {
        "output_dir": _first(
            cli_args.get("output_dir"),
            _resolve_path(cfg.get("output_dir"), GRADE_DIR) if cfg.get("output_dir") else None,
            GRADE_DIR,
        ),
        "export_formats": _first(cli_args.get("export_formats"), cfg.get("export_formats"), ["json", "csv"]),
        "generate_report": _first(cli_args.get("generate_report"), cfg.get("generate_report"), True),
    }
