"""Shared CLI helpers for GDB session scripts."""

from __future__ import annotations

import argparse
from pathlib import Path
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.gdb_session import DEFAULT_MAX_BYTES, DEFAULT_TIMEOUT_MS
from ctf_solver_core.schemas import json_dumps


def add_common_io_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--timeout-ms", type=int, default=DEFAULT_TIMEOUT_MS)
    parser.add_argument("--max-bytes", type=int, default=DEFAULT_MAX_BYTES)
    parser.add_argument("--json", action="store_true")


def emit(result: dict[str, object], *, json_output: bool, text_key: str = "output") -> None:
    if json_output:
        print(json_dumps(result), end="")
    else:
        value = result.get(text_key)
        if value is None:
            print(json_dumps(result), end="")
        else:
            print(str(value), end="")
