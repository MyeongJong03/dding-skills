"""Schema constants and serialization helpers for lifecycle automation."""

from __future__ import annotations

from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import re
import tempfile
import unicodedata
import uuid


PLATFORMS = ("dreamhack", "ctf", "unknown")
CATEGORIES = ("web", "pwn", "crypto", "rev", "forensics", "misc", "osint", "unknown")
STATUSES = (
    "solved",
    "abandoned",
    "skipped",
    "already_solved",
    "timeout",
    "budget_exhausted",
    "manual_stop",
)

PUBLIC_SENSITIVE_KEYS = {
    "flag",
    "flags",
    "raw_transcript",
    "transcript",
    "exploit_code",
    "exploit_path",
    "writeup_path",
    "artifact_path",
    "artifacts_path",
    "cookie",
    "cookies",
    "token",
    "tokens",
    "password",
    "secret",
    "private_key",
    "oauth",
    "email",
    "account_uuid",
    "organization_uuid",
}

SECRET_VALUE_RE = re.compile(
    r"(DH\{[^}\n]{3,}\}|flag\{[^}\n]{3,}\}|sk-[A-Za-z0-9_-]{8,}|"
    r"github_pat_[A-Za-z0-9_]{20,}|ghp_[A-Za-z0-9_]{10,}|xoxb-[A-Za-z0-9-]{10,}|"
    r"-----BEGIN [A-Z ]*PRIVATE KEY-----)",
    re.IGNORECASE,
)
PRIVATE_PATH_RE = re.compile(r"(/Users/[^/\s]+|/home/[^/\s]+|[A-Za-z]:\\Users\\[^\\\s]+)")


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


def iso_now() -> str:
    return utc_now().isoformat(timespec="seconds").replace("+00:00", "Z")


def parse_iso(value: str | None) -> datetime | None:
    if not value:
        return None
    try:
        return datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        return None


def slugify(value: str, *, fallback: str = "item", max_length: int = 72) -> str:
    normalized = unicodedata.normalize("NFKD", str(value))
    ascii_text = normalized.encode("ascii", "ignore").decode("ascii")
    slug = re.sub(r"[^a-zA-Z0-9]+", "-", ascii_text).strip("-").lower()
    slug = re.sub(r"-{2,}", "-", slug)
    if not slug:
        slug = fallback
    return slug[:max_length].strip("-") or fallback


def make_challenge_id(platform: str, event: str, challenge_name: str, category: str) -> str:
    source = "|".join([platform, event, category, challenge_name])
    digest = hashlib.sha1(source.encode("utf-8")).hexdigest()[:8]
    parts = [
        slugify(platform, fallback="unknown", max_length=24),
        slugify(event, fallback="event", max_length=32),
        slugify(category, fallback="unknown", max_length=16),
        slugify(challenge_name, fallback="challenge", max_length=48),
    ]
    base = "-".join(part for part in parts if part)
    return f"{base}-{digest}"


def make_run_id() -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def json_dumps(data: object) -> str:
    return json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True) + "\n"


def atomic_write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.NamedTemporaryFile(
        "w",
        encoding="utf-8",
        dir=str(path.parent),
        prefix=f".{path.name}.",
        suffix=".tmp",
        delete=False,
    ) as handle:
        handle.write(text)
        tmp = Path(handle.name)
    tmp.replace(path)


def atomic_write_json(path: Path, data: object) -> None:
    atomic_write_text(path, json_dumps(data))


def read_json(path: Path, default: object | None = None) -> object:
    if not path.is_file():
        return {} if default is None else default
    return json.loads(path.read_text(encoding="utf-8"))


def read_jsonl(path: Path) -> list[dict[str, object]]:
    if not path.is_file():
        return []
    records: list[dict[str, object]] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        item = json.loads(line)
        if isinstance(item, dict):
            records.append(item)
    return records


def atomic_write_jsonl(path: Path, records: list[dict[str, object]]) -> None:
    text = "".join(json.dumps(record, ensure_ascii=False, sort_keys=True) + "\n" for record in records)
    atomic_write_text(path, text)


def _walk_public_record(node: object, prefix: str = "") -> list[str]:
    errors: list[str] = []
    if isinstance(node, dict):
        for key, value in node.items():
            key_text = str(key)
            lowered = key_text.lower()
            path = f"{prefix}.{key_text}" if prefix else key_text
            if lowered in PUBLIC_SENSITIVE_KEYS:
                errors.append(f"disallowed public key: {path}")
            errors.extend(_walk_public_record(value, path))
    elif isinstance(node, list):
        for index, value in enumerate(node):
            errors.extend(_walk_public_record(value, f"{prefix}[{index}]"))
    elif isinstance(node, str):
        if SECRET_VALUE_RE.search(node):
            errors.append(f"sensitive-looking value at {prefix or '<root>'}")
        if PRIVATE_PATH_RE.search(node):
            errors.append(f"private absolute path at {prefix or '<root>'}")
        home = str(Path.home().resolve())
        if home and home in node:
            errors.append(f"current home path at {prefix or '<root>'}")
    return errors


def validate_public_record(record: dict[str, object]) -> list[str]:
    return _walk_public_record(record)

