"""Platform policy loading for resource-aware CTF automation."""

from __future__ import annotations

from dataclasses import asdict, dataclass, field
from pathlib import Path
import os
from typing import Any

from .paths import repo_root, resolve_path


DEFAULT_PLATFORM_CONFIG = repo_root() / "config" / "platforms.example.yaml"


def _scalar(value: str) -> object:
    text = value.strip()
    if not text:
        return ""
    if (text.startswith('"') and text.endswith('"')) or (text.startswith("'") and text.endswith("'")):
        return text[1:-1]
    lowered = text.lower()
    if lowered in {"true", "yes", "on"}:
        return True
    if lowered in {"false", "no", "off"}:
        return False
    if lowered in {"null", "none", "~"}:
        return None
    try:
        if "." not in text:
            return int(text)
        return float(text)
    except ValueError:
        return text


def _strip_comment(line: str) -> str:
    quote: str | None = None
    for index, char in enumerate(line):
        if char in {"'", '"'}:
            quote = None if quote == char else char
        if char == "#" and quote is None:
            return line[:index]
    return line


def _simple_yaml_load(text: str) -> object:
    """Parse the small YAML subset used by the platform config template.

    PyYAML is used when installed. This fallback intentionally supports only
    mappings, lists, and scalar values so the scaffold has no hard dependency
    beyond the Python standard library.
    """

    lines: list[tuple[int, str]] = []
    for raw in text.splitlines():
        cleaned = _strip_comment(raw).rstrip()
        if not cleaned.strip():
            continue
        indent = len(cleaned) - len(cleaned.lstrip(" "))
        lines.append((indent, cleaned.strip()))

    def parse_block(index: int, indent: int) -> tuple[object, int]:
        if index >= len(lines):
            return {}, index
        current_indent, current_text = lines[index]
        if current_indent < indent:
            return {}, index
        if current_text.startswith("- "):
            items: list[object] = []
            while index < len(lines):
                line_indent, text = lines[index]
                if line_indent != current_indent or not text.startswith("- "):
                    break
                item_text = text[2:].strip()
                index += 1
                if not item_text:
                    item, index = parse_block(index, current_indent + 2)
                    items.append(item)
                    continue
                if ":" in item_text:
                    key, raw_value = item_text.split(":", 1)
                    item: dict[str, object] = {}
                    if raw_value.strip():
                        item[key.strip()] = _scalar(raw_value)
                    else:
                        value, index = parse_block(index, current_indent + 2)
                        item[key.strip()] = value
                    if index < len(lines) and lines[index][0] > current_indent:
                        extra, index = parse_block(index, current_indent + 2)
                        if isinstance(extra, dict):
                            item.update(extra)
                    items.append(item)
                else:
                    items.append(_scalar(item_text))
            return items, index

        mapping: dict[str, object] = {}
        while index < len(lines):
            line_indent, text = lines[index]
            if line_indent < indent or line_indent != current_indent or text.startswith("- "):
                break
            if ":" not in text:
                raise ValueError(f"unsupported YAML line: {text}")
            key, raw_value = text.split(":", 1)
            index += 1
            if raw_value.strip():
                mapping[key.strip()] = _scalar(raw_value)
            else:
                value, index = parse_block(index, current_indent + 2)
                mapping[key.strip()] = value
        return mapping, index

    if not lines:
        return {}
    parsed, final_index = parse_block(0, lines[0][0])
    if final_index != len(lines):
        raise ValueError("could not parse complete YAML document")
    return parsed


def load_yaml(path: Path) -> object:
    text = path.read_text(encoding="utf-8")
    try:
        import yaml  # type: ignore
    except Exception:
        return _simple_yaml_load(text)
    loaded = yaml.safe_load(text)
    return loaded if loaded is not None else {}


@dataclass(frozen=True)
class AuthPolicy:
    mode: str = "manual"
    session_profile: str = "placeholder"


@dataclass(frozen=True)
class SharingPolicy:
    allowed: bool = False
    max_workers: int = 1
    mode: str = "exclusive"
    destructive_actions_require_primary: bool = True


@dataclass(frozen=True)
class RemoteServerPolicy:
    provisioning: bool = True
    max_active_leases: int = 1
    lease_scope: str = "event"
    release_required_before_next: bool = True
    sharing: SharingPolicy = field(default_factory=SharingPolicy)


@dataclass(frozen=True)
class ResourcePolicy:
    remote_server: RemoteServerPolicy = field(default_factory=RemoteServerPolicy)


@dataclass(frozen=True)
class AutomationPolicy:
    allow_problem_discovery: bool | str = False
    allow_file_download: bool | str = False
    allow_server_create: bool | str = "ask"
    allow_submission: bool | str = "ask"


@dataclass(frozen=True)
class PlatformPolicy:
    platform: str
    event: str = "unknown"
    base_url: str = ""
    adapter: str = ""
    auth: AuthPolicy = field(default_factory=AuthPolicy)
    resources: ResourcePolicy = field(default_factory=ResourcePolicy)
    automation: AutomationPolicy = field(default_factory=AutomationPolicy)
    source_path: str = ""

    def to_dict(self) -> dict[str, object]:
        return asdict(self)


def _dict(value: object) -> dict[str, object]:
    return value if isinstance(value, dict) else {}


def _bool(value: object, default: bool) -> bool:
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        lowered = value.strip().lower()
        if lowered in {"true", "yes", "on", "1"}:
            return True
        if lowered in {"false", "no", "off", "0"}:
            return False
    return default


def _int(value: object, default: int) -> int:
    try:
        return int(value)  # type: ignore[arg-type]
    except (TypeError, ValueError):
        return default


def _policy_from_dict(raw: dict[str, object], source_path: Path) -> PlatformPolicy:
    auth = _dict(raw.get("auth"))
    resources = _dict(raw.get("resources"))
    remote = _dict(resources.get("remote_server"))
    sharing = _dict(remote.get("sharing"))
    automation = _dict(raw.get("automation"))

    sharing_policy = SharingPolicy(
        allowed=_bool(sharing.get("allowed"), False),
        max_workers=max(1, _int(sharing.get("max_workers"), 1)),
        mode=str(sharing.get("mode") or "exclusive"),
        destructive_actions_require_primary=_bool(
            sharing.get("destructive_actions_require_primary"),
            True,
        ),
    )
    remote_policy = RemoteServerPolicy(
        provisioning=_bool(remote.get("provisioning"), True),
        max_active_leases=max(0, _int(remote.get("max_active_leases"), 1)),
        lease_scope=str(remote.get("lease_scope") or "event"),
        release_required_before_next=_bool(remote.get("release_required_before_next"), True),
        sharing=sharing_policy,
    )
    return PlatformPolicy(
        platform=str(raw.get("platform") or "unknown"),
        event=str(raw.get("event") or "unknown"),
        base_url=str(raw.get("base_url") or ""),
        adapter=str(raw.get("adapter") or ""),
        auth=AuthPolicy(
            mode=str(auth.get("mode") or "manual"),
            session_profile=str(auth.get("session_profile") or "placeholder"),
        ),
        resources=ResourcePolicy(remote_server=remote_policy),
        automation=AutomationPolicy(
            allow_problem_discovery=automation.get("allow_problem_discovery", False),
            allow_file_download=automation.get("allow_file_download", False),
            allow_server_create=automation.get("allow_server_create", "ask"),
            allow_submission=automation.get("allow_submission", "ask"),
        ),
        source_path=str(source_path),
    )


def platform_config_path(path: str | Path | None = None) -> Path:
    if path:
        return resolve_path(path)
    raw = os.environ.get("CTF_PLATFORM_CONFIG")
    if raw:
        return resolve_path(raw)
    return DEFAULT_PLATFORM_CONFIG


def load_platform_policies(path: str | Path | None = None) -> list[PlatformPolicy]:
    config_path = platform_config_path(path)
    if not config_path.is_file():
        return []
    data = load_yaml(config_path)
    raw_platforms: object
    if isinstance(data, dict) and "platforms" in data:
        raw_platforms = data["platforms"]
    else:
        raw_platforms = data

    entries: list[dict[str, object]] = []
    if isinstance(raw_platforms, list):
        entries = [item for item in raw_platforms if isinstance(item, dict)]
    elif isinstance(raw_platforms, dict):
        for key, value in raw_platforms.items():
            if not isinstance(value, dict):
                continue
            entry = dict(value)
            entry.setdefault("platform", str(key))
            entries.append(entry)
    return [_policy_from_dict(entry, config_path) for entry in entries]


def default_policy(platform: str, event: str = "unknown") -> PlatformPolicy:
    return PlatformPolicy(platform=platform, event=event)


def get_platform_policy(
    platform: str,
    event: str = "unknown",
    path: str | Path | None = None,
) -> PlatformPolicy:
    policies = load_platform_policies(path)
    exact = [item for item in policies if item.platform == platform and item.event == event]
    if exact:
        return exact[0]
    platform_default = [
        item for item in policies if item.platform == platform and item.event in {"*", "default", "unknown"}
    ]
    if platform_default:
        selected = platform_default[0]
        return _policy_from_dict({**selected.to_dict(), "event": event}, Path(selected.source_path))
    generic = [item for item in policies if item.platform in {"generic", "ctf"} and item.event in {event, "*"}]
    if generic:
        selected = generic[0]
        return _policy_from_dict(
            {**selected.to_dict(), "platform": platform, "event": event},
            Path(selected.source_path),
        )
    return default_policy(platform, event)


def validate_platform_config(path: str | Path | None = None) -> list[str]:
    errors: list[str] = []
    config_path = platform_config_path(path)
    if not config_path.is_file():
        errors.append(f"platform config not found: {config_path}")
        return errors
    try:
        policies = load_platform_policies(config_path)
    except Exception as exc:
        errors.append(f"platform config parse failed: {exc}")
        return errors
    if not policies:
        errors.append("platform config contains no platform policies")
    for policy in policies:
        if not policy.platform:
            errors.append("platform policy missing platform")
        if policy.resources.remote_server.lease_scope not in {
            "event",
            "platform",
            "platform_event",
            "user_session",
            "challenge",
            "run",
        }:
            errors.append(
                f"{policy.platform}/{policy.event}: unsupported remote_server.lease_scope "
                f"{policy.resources.remote_server.lease_scope!r}"
            )
        if policy.resources.remote_server.max_active_leases < 0:
            errors.append(f"{policy.platform}/{policy.event}: max_active_leases must be >= 0")
    return errors
