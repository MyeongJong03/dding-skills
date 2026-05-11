#!/usr/bin/env python3
"""Generate a local-only CTF writeup and embed full exploit code."""

from __future__ import annotations

import argparse
from pathlib import Path
import shutil
import sys


ROOT = Path(__file__).resolve().parents[1]
if str(ROOT) not in sys.path:
    sys.path.insert(0, str(ROOT))

from ctf_solver_core.paths import display_path, resolve_path, solved_writeup_root
from ctf_solver_core.schemas import (
    CATEGORIES,
    PLATFORMS,
    atomic_write_json,
    atomic_write_text,
    iso_now,
    json_dumps,
    read_json,
)


LANG_BY_SUFFIX = {
    ".py": "python",
    ".sage": "python",
    ".js": "javascript",
    ".ts": "typescript",
    ".sh": "bash",
    ".c": "c",
    ".cpp": "cpp",
    ".rs": "rust",
    ".go": "go",
    ".php": "php",
    ".rb": "ruby",
}


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--run-dir", help="challenge run directory containing challenge.json")
    parser.add_argument("--platform", choices=PLATFORMS, default="unknown")
    parser.add_argument("--event", default="unknown")
    parser.add_argument("--challenge-name", required=False)
    parser.add_argument("--category", choices=CATEGORIES, default="unknown")
    parser.add_argument("--flag", help="optional flag to include in local-only writeup")
    parser.add_argument("--exclude-flag", action="store_true", help="do not write the flag into writeup.md")
    parser.add_argument("--exploit", action="append", default=[], help="exploit file to copy and embed")
    parser.add_argument("--workspace", help="optional challenge workspace path")
    parser.add_argument("--dry-run", action="store_true")
    return parser


def _load_metadata(run_dir: Path | None) -> dict[str, object]:
    if not run_dir:
        return {}
    data = read_json(run_dir / "challenge.json", default={})
    return data if isinstance(data, dict) else {}


def _writeup_dir(platform: str, event: str, challenge_name: str) -> Path:
    if platform == "dreamhack" and event == "dreamhackWargame":
        parent = "dreamhackWargame"
    elif event and event != "unknown":
        parent = event
    else:
        parent = "unknown"
    return solved_writeup_root() / _safe_component(parent, "unknown") / _safe_component(challenge_name, "challenge")


def _safe_component(value: str, fallback: str) -> str:
    text = "".join("_" if char in '<>:"/\\|?*' or ord(char) < 32 else char for char in str(value))
    text = " ".join(text.split()).strip(" .")
    return text[:120] or fallback


def _unique_destination(directory: Path, source: Path) -> Path:
    candidate = directory / source.name
    if not candidate.exists():
        return candidate
    stem = source.stem
    suffix = source.suffix
    index = 2
    while True:
        candidate = directory / f"{stem}_{index}{suffix}"
        if not candidate.exists():
            return candidate
        index += 1


def _read_exploit(path: Path) -> str:
    data = path.read_bytes()
    return data.decode("utf-8", errors="replace")


def _fence_for(text: str) -> str:
    longest = 0
    current = 0
    for char in text:
        if char == "`":
            current += 1
            longest = max(longest, current)
        else:
            current = 0
    return "`" * max(4, longest + 1)


def _exploit_sections(exploit_paths: list[Path], copied: list[Path]) -> tuple[list[str], list[dict[str, str]]]:
    sections: list[str] = []
    records: list[dict[str, str]] = []
    for original, copied_path in zip(exploit_paths, copied):
        text = _read_exploit(original)
        fence = _fence_for(text)
        language = LANG_BY_SUFFIX.get(original.suffix.lower(), "")
        sections.extend(
            [
                f"### {copied_path.name}",
                "",
                f"{fence}{language}",
                text.rstrip("\n"),
                fence,
                "",
            ]
        )
        records.append(
            {
                "source": str(original),
                "copied_to": str(copied_path),
                "bytes": str(original.stat().st_size),
            }
        )
    if not sections:
        sections = ["TODO: final exploit code was not provided.", ""]
    return sections, records


def generate_writeup(args: argparse.Namespace) -> dict[str, object]:
    run_dir = resolve_path(args.run_dir) if args.run_dir else None
    metadata = _load_metadata(run_dir)
    platform = str(metadata.get("platform") or args.platform)
    event = str(metadata.get("event") or args.event)
    challenge_name = str(metadata.get("challenge_name") or args.challenge_name or "unknown")
    category = str(metadata.get("category") or args.category)
    workspace = str(args.workspace or metadata.get("workspace") or "")
    exploit_paths = [resolve_path(path) for path in args.exploit]
    for path in exploit_paths:
        if not path.is_file():
            raise FileNotFoundError(f"exploit file not found: {path}")

    output_dir = _writeup_dir(platform, event, challenge_name)
    writeup_path = output_dir / "writeup.md"
    copied_paths: list[Path] = []
    if not args.dry_run:
        output_dir.mkdir(parents=True, exist_ok=True)
        for exploit in exploit_paths:
            destination = _unique_destination(output_dir, exploit)
            shutil.copy2(exploit, destination)
            copied_paths.append(destination)
    else:
        copied_paths = [_unique_destination(output_dir, exploit) for exploit in exploit_paths]

    exploit_markdown, exploit_records = _exploit_sections(exploit_paths, copied_paths)
    flag_lines = []
    if args.flag and not args.exclude_flag:
        flag_lines = [
            f"- Flag: `{args.flag}`",
            "- Flag storage policy: local-only writeup; never auto-push to GitHub.",
        ]
    else:
        flag_lines = ["- Flag: TODO or intentionally excluded."]

    lines = [
        f"# {challenge_name} Writeup",
        "",
        "> Local-only writeup. This file may contain exploit code and flags and must not be auto-pushed.",
        "",
        "## Metadata",
        f"- Platform: `{platform}`",
        f"- Event: `{event}`",
        f"- Category: `{category}`",
        f"- Generated At: `{iso_now()}`",
        f"- Workspace: `{workspace or 'TODO'}`",
        *flag_lines,
        "",
        "## TL;DR",
        "TODO: summarize the solve in 2-4 sentences.",
        "",
        "## Initial Analysis",
        "TODO: record source/binary/file triage findings.",
        "",
        "## Attack Surface",
        "TODO: list reachable inputs, trust boundaries, and useful primitives.",
        "",
        "## Hypotheses",
        "TODO: list tested vulnerability hypotheses and why the winning one worked.",
        "",
        "## Exploit Strategy",
        "TODO: explain the final strategy and required preconditions.",
        "",
        "## Detailed Exploitation Steps",
        "TODO: provide reproducible steps from clean state to flag.",
        "",
        "## Final Exploit Code",
        *exploit_markdown,
        "## Verification",
        "TODO: paste local/remote verification evidence without raw secrets beyond the local-only flag if needed.",
        "",
        "## Failed Attempts",
        "TODO: summarize useful failed attempts and backtracking reasons.",
        "",
        "## Cleanup / Artifacts",
        "TODO: list preserved challenge files, final exploit paths, and cleanup result.",
        "",
        "## Lessons Learned",
        "TODO: capture reusable technique or pitfall.",
        "",
        "## Skill / Memory Updates",
        "TODO: note whether any ctf-personal/category skill update was made.",
        "",
    ]

    writeup_meta = {
        "generated_at": iso_now(),
        "platform": platform,
        "event": event,
        "challenge_name": challenge_name,
        "category": category,
        "writeup_path": str(writeup_path),
        "exploit_files": exploit_records,
        "flag_included": bool(args.flag and not args.exclude_flag),
    }
    if not args.dry_run:
        atomic_write_text(writeup_path, "\n".join(lines))
        atomic_write_json(output_dir / "metadata.json", writeup_meta)

    return {
        "generated": not args.dry_run,
        "writeup_path": str(writeup_path),
        "display_writeup_path": display_path(writeup_path),
        "exploit_included": bool(exploit_paths),
        "copied_exploits": [str(path) for path in copied_paths],
        "flag_included": bool(args.flag and not args.exclude_flag),
        "dry_run": args.dry_run,
    }


def main() -> int:
    args = build_parser().parse_args()
    result = generate_writeup(args)
    safe = dict(result)
    safe["flag_included"] = bool(safe.get("flag_included"))
    print(json_dumps(safe), end="")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
