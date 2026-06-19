from __future__ import annotations

import argparse
import sys
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(
        prog="sufe",
        description="SUFE 综合工具：课程下载、就业信息、成绩查询",
    )
    sub = parser.add_subparsers(dest="command", help="子命令")

    p_canvas = sub.add_parser("canvas", help="同步 Canvas 课程材料")
    p_canvas.add_argument("--output", "-o", type=Path, dest="output_dir", help="输出目录")
    p_canvas.add_argument("--concurrency", "-c", type=int, help="并发数")

    p_career = sub.add_parser("career", help="同步就业招聘信息")
    p_career.add_argument("--output", "-o", type=Path, dest="output_dir", help="输出目录")
    p_career.add_argument("--concurrency", "-c", type=int, help="并发数")
    p_career.add_argument("--page-concurrency", type=int, help="分页并发数")
    p_career.add_argument("--max-items", type=int, help="最大条目数")

    p_grade = sub.add_parser("grade", help="同步成绩信息")
    p_grade.add_argument("--output", "-o", type=Path, dest="output_dir", help="输出目录")

    sub.add_parser("evaluate", help="自动评教")

    args = parser.parse_args()
    if not args.command:
        parser.print_help()
        sys.exit(1)

    # Extract CLI args, filter None
    cli = {k: v for k, v in vars(args).items() if k != "command" and v is not None}

    # Dispatch table
    dispatch = {
        "canvas": ("sufe.canvas.run", "get_canvas_config"),
        "career": ("sufe.career.run", "get_career_config"),
        "grade": ("sufe.grade.run", "get_grade_config"),
        "evaluate": ("sufe.evaluation", None),
    }

    run_module, config_name = dispatch[args.command]

    import importlib

    if config_name is None:
        importlib.import_module(run_module).run()
        return

    run_func = importlib.import_module(run_module).run
    config_func = getattr(importlib.import_module("sufe.user_config"), config_name)

    run_func(**config_func(cli))


if __name__ == "__main__":
    main()
