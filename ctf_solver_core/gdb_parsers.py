"""Public-safe parsers for bounded GDB and pwndbg output."""

from __future__ import annotations

from pathlib import PurePosixPath, PureWindowsPath
import re

from ctf_solver_core.sessions import bounded_text, redact_text


REGISTER_RE = re.compile(r"^\s*([a-zA-Z][a-zA-Z0-9]*)\s+(0x[0-9a-fA-F]+|-?\d+)\b(.*)$")
SIGNAL_RE = re.compile(r"(?:Program received signal|received signal|signal)\s+(SIG[A-Z0-9]+)", re.IGNORECASE)
HEX_RE = re.compile(r"0x[0-9a-fA-F]+")
FAULT_RE = re.compile(
    r"(?:fault(?:ing)? address|si_addr|Cannot access memory at address)\s*[=:]?\s*(0x[0-9a-fA-F]+)",
    re.IGNORECASE,
)
FRAME_RE = re.compile(r"^\s*#\d+\s+")
MAPPING_LINE_RE = re.compile(r"^\s*(0x[0-9a-fA-F]+)\s+(0x[0-9a-fA-F]+)\s+(.*)$")
PERMS_RE = re.compile(r"\b([r-][w-][x-][ps-]?)\b")
PRIVATE_PATH_RE = re.compile(r"(/Users/[^:\s]+|/home/[^:\s]+|[A-Za-z]:\\Users\\[^:\s]+)")


def basename_only(path: str) -> str:
    text = path.strip()
    if not text:
        return ""
    if "\\" in text:
        return PureWindowsPath(text).name
    return PurePosixPath(text).name


def redact_paths(text: str) -> str:
    def repl(match: re.Match[str]) -> str:
        return f"<path>/{basename_only(match.group(0))}"

    return PRIVATE_PATH_RE.sub(repl, redact_text(text))


def parse_registers(output: str) -> dict[str, str]:
    registers: dict[str, str] = {}
    for line in str(output).splitlines():
        match = REGISTER_RE.match(line)
        if not match:
            continue
        registers[match.group(1).lower()] = match.group(2).lower()
    return registers


def parse_crash(output: str) -> dict[str, object]:
    text = str(output)
    signal_match = SIGNAL_RE.search(text)
    registers = parse_registers(text)
    pc = registers.get("rip") or registers.get("eip") or registers.get("pc")
    if not pc:
        for line in text.splitlines():
            if " in " in line:
                hex_match = HEX_RE.search(line)
                if hex_match:
                    pc = hex_match.group(0).lower()
                    break
    fault_match = FAULT_RE.search(text)
    signal = signal_match.group(1).upper() if signal_match else ""
    summary = ""
    if signal:
        summary = signal
        if pc:
            summary += f" at {pc}"
    return {
        "crashed": bool(signal),
        "signal": signal,
        "pc": pc or "",
        "fault_addr": fault_match.group(1).lower() if fault_match else "",
        "summary": summary,
    }


def summarize_backtrace(output: str, *, max_frames: int = 20, max_bytes: int = 8000) -> dict[str, object]:
    frames: list[str] = []
    for line in redact_paths(output).splitlines():
        if FRAME_RE.match(line):
            frames.append(line.strip())
        if len(frames) >= max_frames:
            break
    return {
        "frame_count": len(frames),
        "frames": frames,
        "output_preview": bounded_text("\n".join(frames) if frames else redact_paths(output), max_bytes=max_bytes),
    }


def parse_vmmap(output: str) -> list[dict[str, str]]:
    mappings: list[dict[str, str]] = []
    for raw_line in str(output).splitlines():
        line = raw_line.strip()
        match = MAPPING_LINE_RE.match(line)
        if not match:
            continue
        rest = match.group(3).split()
        if not rest:
            continue
        perms = ""
        path = ""
        for index, token in enumerate(rest):
            if PERMS_RE.fullmatch(token):
                perms = token
                if index + 1 < len(rest):
                    candidate = rest[-1]
                    if "/" in candidate or "\\" in candidate or candidate.startswith("["):
                        path = basename_only(candidate) if not candidate.startswith("[") else candidate
                break
        if not perms:
            continue
        mappings.append(
            {
                "start": match.group(1).lower(),
                "end": match.group(2).lower(),
                "perms": perms,
                "path": path,
            }
        )
    return mappings


def summarize_telescope(output: str, *, max_bytes: int = 8000) -> dict[str, object]:
    preview = bounded_text(redact_paths(output), max_bytes=max_bytes)
    lines = [line for line in preview.splitlines() if line.strip()]
    return {
        "line_count": len(lines),
        "output_preview": preview,
    }
