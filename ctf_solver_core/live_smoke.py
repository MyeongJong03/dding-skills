"""Manual opt-in live platform smoke checks.

The default path is dry-run and no-network. Live mode is intentionally narrow:
it validates policy/profile metadata, never submits flags, and stores only
bounded summaries under a local-only root.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
import os
from urllib.parse import urlparse, urlunparse

from .browser_state import check_browser_profile
from .paths import display_path, is_inside_repo, live_smoke_root, resolve_path
from .platform_adapters import PlatformAdapterError, get_adapter
from .platform_automation import acquire_platform_server
from .platforms import PlatformPolicy, get_platform_policy, validate_platform_config
from .resources import REMOTE_SERVER, list_leases, public_lease_summary
from .schemas import (
    atomic_write_json,
    atomic_write_text,
    iso_now,
    make_run_id,
    validate_public_record,
)


SMOKE_MODES = (
    "dry-run",
    "discovery",
    "download",
    "server-status",
    "server-acquire",
    "full-readonly",
)
AUTH_PROFILE_MODES = {"browser_profile", "session_profile", "storage_state"}
PLACEHOLDER_PROFILES = {"", "placeholder", "local-profile-placeholder"}


class LiveSmokeError(RuntimeError):
    """Raised when smoke setup would violate local-only safety policy."""


@dataclass(frozen=True)
class LiveSmokeRequest:
    platform: str
    event: str
    adapter_name: str = "generic"
    profile: str | None = None
    policy_path: str | Path | None = None
    base_url: str | None = None
    source: str | None = None
    mode: str = "dry-run"
    live: bool = False
    no_submit: bool = True
    output: str | Path | None = None
    run_id: str | None = None
    challenge_id: str | None = None
    max_challenges: int | None = None
    allow_server_acquire: bool = False
    allow_download: bool = False


def _is_url(value: str | None) -> bool:
    if not value:
        return False
    parsed = urlparse(value)
    return parsed.scheme in {"http", "https"}


def _safe_url(value: str | None) -> str:
    if not value:
        return ""
    parsed = urlparse(value)
    if parsed.scheme not in {"http", "https"}:
        return "<local-path>"
    query = "<redacted>" if parsed.query else ""
    fragment = "<redacted>" if parsed.fragment else ""
    return urlunparse((parsed.scheme, parsed.netloc, parsed.path, "", query, fragment))


def _policy_value(value: bool | str) -> str:
    if isinstance(value, bool):
        return "true" if value else "false"
    lowered = str(value).strip().lower()
    if lowered in {"true", "yes", "on", "1", "enabled", "allow", "allowed"}:
        return "true"
    if lowered in {"ask", "confirm", "manual"}:
        return "ask"
    return "false"


def _select_adapter_name(policy: PlatformPolicy, requested: str) -> str:
    if requested in {"", "generic"} and policy.adapter:
        return policy.adapter
    return requested


def _policy_summary(policy: PlatformPolicy) -> dict[str, object]:
    remote = policy.resources.remote_server
    return {
        "platform": policy.platform,
        "event": policy.event,
        "adapter": policy.adapter or "",
        "base_url_configured": bool(policy.base_url),
        "auth_mode": policy.auth.mode,
        "session_profile_configured": bool(policy.auth.session_profile),
        "remote_server_provisioning": remote.provisioning,
        "remote_server_max_active_leases": remote.max_active_leases,
        "remote_server_lease_scope": remote.lease_scope,
        "allow_problem_discovery": _policy_value(policy.automation.allow_problem_discovery),
        "allow_file_download": _policy_value(policy.automation.allow_file_download),
        "allow_server_create": _policy_value(policy.automation.allow_server_create),
        "allow_submission": _policy_value(policy.automation.allow_submission),
    }


def _policy_gate(policy: PlatformPolicy, field: str) -> dict[str, object] | None:
    mode = _policy_value(getattr(policy.automation, field))
    if mode == "true":
        return None
    return {
        "ok": False,
        "performed": False,
        "reason": f"{field}_{'requires_confirmation' if mode == 'ask' else 'disabled'}",
        "policy": mode,
    }


def _source_value(request: LiveSmokeRequest, policy: PlatformPolicy) -> str:
    return str(request.source or request.base_url or policy.base_url or "").strip()


def _profile_name(request: LiveSmokeRequest, policy: PlatformPolicy) -> str:
    explicit = str(request.profile or "").strip()
    if explicit:
        return explicit
    return str(policy.auth.session_profile or "").strip()


def _profile_required(policy: PlatformPolicy) -> bool:
    return str(policy.auth.mode or "").strip().lower() in AUTH_PROFILE_MODES


def _profile_validation(request: LiveSmokeRequest, policy: PlatformPolicy) -> dict[str, object]:
    required = _profile_required(policy)
    profile_name = _profile_name(request, policy)
    placeholder = profile_name.strip().lower() in PLACEHOLDER_PROFILES
    if placeholder:
        profile_name = ""
    result: dict[str, object] = {
        "required": required,
        "configured": bool(profile_name),
        "profile_name": profile_name,
        "ok": True,
        "exists": False,
        "storage_state_configured": False,
        "storage_state_exists": False,
    }
    if not profile_name:
        if request.live and required:
            result["ok"] = False
            result["reason"] = "profile_required_for_live_auth"
        return result
    checked = check_browser_profile(request.platform, request.event, profile_name)
    result.update(
        {
            "ok": bool(checked.get("ok")),
            "exists": bool(checked.get("exists")),
            "storage_state_configured": bool(checked.get("storage_state_configured")),
            "storage_state_exists": bool(checked.get("storage_state_exists")),
            "profile_path": display_path(Path(str(checked.get("profile_path") or ""))),
        }
    )
    if not result["ok"]:
        result["reason"] = "profile_metadata_invalid"
    return result


def _output_dir(smoke_id: str, output: str | Path | None) -> Path:
    target = resolve_path(output) if output else live_smoke_root() / smoke_id
    if target.suffix:
        target = target.parent
    if is_inside_repo(target):
        raise LiveSmokeError("live_smoke_output_inside_repo")
    return target


def _challenge_summary(item: dict[str, object]) -> dict[str, object]:
    return {
        "challenge_id": str(item.get("challenge_id") or item.get("id") or ""),
        "category": str(item.get("category") or "unknown"),
        "remote_required": bool(item.get("remote_required", False)),
        "local_capable": bool(item.get("local_capable", True)),
        "has_files": bool(item.get("files")),
        "has_url": bool(item.get("url")),
    }


def _download_summary(result: list[dict[str, object]]) -> dict[str, object]:
    return {
        "downloaded_count": len(result),
        "downloaded_bytes": sum(int(item.get("size") or 0) for item in result),
        "files": [
            {
                "name": str(item.get("name") or ""),
                "relative_path": str(item.get("relative_path") or ""),
                "size": int(item.get("size") or 0),
                "sha256": str(item.get("sha256") or ""),
            }
            for item in result
        ],
    }


def _planned_action(mode: str) -> dict[str, object]:
    return {
        "ok": True,
        "performed": False,
        "blocked": True,
        "reason": "live_flag_absent_dry_run_only",
        "mode": mode,
    }


def _run_discovery(
    *,
    adapter_name: str,
    request: LiveSmokeRequest,
    policy: PlatformPolicy,
    source: str,
) -> dict[str, object]:
    blocked = _policy_gate(policy, "allow_problem_discovery")
    if blocked:
        return blocked
    adapter = get_adapter(adapter_name)
    limit = request.max_challenges if request.max_challenges is not None else 20
    limit = max(0, min(int(limit), 100))
    try:
        challenges = adapter.discover_challenges(platform=request.platform, event=request.event, source=source or None)
    except PlatformAdapterError as exc:
        return {"ok": False, "performed": True, "reason": str(exc), "challenge_count": 0, "adapter": adapter.name}
    summaries = [_challenge_summary(item) for item in challenges[:limit]]
    return {
        "ok": True,
        "performed": True,
        "adapter": adapter.name,
        "challenge_count": len(challenges),
        "sample_count": len(summaries),
        "challenge_summaries": summaries,
    }


def _run_download(
    *,
    adapter_name: str,
    request: LiveSmokeRequest,
    policy: PlatformPolicy,
    source: str,
    smoke_dir: Path,
) -> dict[str, object]:
    if not request.allow_download:
        return {"ok": False, "performed": False, "reason": "allow_download_flag_required"}
    blocked = _policy_gate(policy, "allow_file_download")
    if blocked:
        return blocked
    if not request.challenge_id:
        return {"ok": False, "performed": False, "reason": "challenge_id_required_for_download"}
    adapter = get_adapter(adapter_name)
    dest = smoke_dir / "downloads"
    try:
        files = adapter.download_files(
            platform=request.platform,
            event=request.event,
            challenge_id=request.challenge_id,
            dest=dest,
            source=source or None,
            url=source if _is_url(source) else None,
        )
    except PlatformAdapterError as exc:
        return {"ok": False, "performed": True, "reason": str(exc), "adapter": adapter.name}
    summary = _download_summary(files)
    return {
        "ok": True,
        "performed": True,
        "adapter": adapter.name,
        "challenge_id": request.challenge_id,
        "dest": display_path(dest),
        **summary,
    }


def _run_server_status(*, adapter_name: str, request: LiveSmokeRequest) -> dict[str, object]:
    adapter = get_adapter(adapter_name)
    try:
        status = adapter.server_status(
            platform=request.platform,
            event=request.event,
            challenge_id=request.challenge_id,
            run_id=request.run_id,
        )
    except PlatformAdapterError as exc:
        status = {"ok": False, "reason": str(exc), "server_count": 0, "servers": []}
    leases = [
        public_lease_summary(item)
        for item in list_leases(platform=request.platform, event=request.event, resource_type=REMOTE_SERVER)
        if (not request.challenge_id or item.get("challenge_id") == request.challenge_id)
        and (not request.run_id or item.get("run_id") == request.run_id)
    ]
    return {
        "ok": bool(status.get("ok", True)),
        "performed": True,
        "adapter": adapter.name,
        "server_count": int(status.get("server_count") or 0),
        "active_lease_count": len(leases),
        "reason": status.get("reason") or "",
    }


def _run_server_acquire(*, adapter_name: str, request: LiveSmokeRequest) -> dict[str, object]:
    if not request.allow_server_acquire:
        return {"ok": False, "performed": False, "reason": "allow_server_acquire_flag_required"}
    if not request.challenge_id:
        return {"ok": False, "performed": False, "reason": "challenge_id_required_for_server_acquire"}
    run_id = request.run_id or make_run_id()
    result = acquire_platform_server(
        platform=request.platform,
        event=request.event,
        challenge_id=request.challenge_id,
        run_id=run_id,
        adapter_name=adapter_name,
        policy_path=request.policy_path,
        worker_id=f"live-smoke-{os.getpid()}",
        confirmed=True,
        role="primary",
    )
    return {
        "ok": bool(result.get("ok")),
        "performed": True,
        "attempted": True,
        "server_acquired": bool(result.get("server_acquired")),
        "adapter": str(result.get("adapter") or adapter_name),
        "challenge_id": request.challenge_id,
        "run_id": run_id,
        "reason": str(result.get("reason") or ""),
    }


def public_metrics_from_result(result: dict[str, object]) -> dict[str, object]:
    actions = result.get("actions") if isinstance(result.get("actions"), dict) else {}
    discovery = actions.get("discovery") if isinstance(actions.get("discovery"), dict) else {}
    download = actions.get("download") if isinstance(actions.get("download"), dict) else {}
    acquire = actions.get("server_acquire") if isinstance(actions.get("server_acquire"), dict) else {}
    metrics = {
        "live_smoke_count": 1,
        "live_smoke_mode": str(result.get("mode") or "unknown"),
        "live_smoke_success": bool(result.get("ok")),
        "live_smoke_discovered_count": int(discovery.get("challenge_count") or 0),
        "live_smoke_downloaded_count": int(download.get("downloaded_count") or 0),
        "live_smoke_server_acquire_attempted": bool(acquire.get("attempted") or acquire.get("performed")),
    }
    errors = validate_public_record(metrics)
    if errors:
        raise LiveSmokeError("live smoke metrics are not public-safe: " + "; ".join(errors))
    return metrics


def render_summary(result: dict[str, object]) -> str:
    actions = result.get("actions") if isinstance(result.get("actions"), dict) else {}
    lines = [
        "# Live Platform Smoke Summary",
        "",
        f"- Smoke ID: `{result.get('smoke_id')}`",
        f"- Platform/event: `{result.get('platform')}/{result.get('event')}`",
        f"- Adapter: `{result.get('adapter')}`",
        f"- Mode: `{result.get('mode')}`",
        f"- Live: `{result.get('live')}`",
        f"- OK: `{result.get('ok')}`",
        f"- Submit attempted: `{False}`",
        f"- Live network performed: `{result.get('live_network_performed')}`",
        "",
        "## Actions",
        "",
    ]
    for name in ("discovery", "download", "server_status", "server_acquire"):
        action = actions.get(name) if isinstance(actions.get(name), dict) else None
        if not action:
            continue
        line = f"- `{name}`: performed=`{action.get('performed', False)}`, ok=`{action.get('ok')}`"
        if action.get("reason"):
            line += f", reason=`{action.get('reason')}`"
        if "challenge_count" in action:
            line += f", challenge_count=`{action.get('challenge_count')}`"
        if "downloaded_count" in action:
            line += f", downloaded_count=`{action.get('downloaded_count')}`"
        if "server_count" in action:
            line += f", server_count=`{action.get('server_count')}`"
        if "server_acquired" in action:
            line += f", server_acquired=`{action.get('server_acquired')}`"
        lines.append(line)
    lines.append("")
    return "\n".join(lines)


def live_smoke_result_count() -> int:
    root = live_smoke_root()
    if not root.is_dir():
        return 0
    return sum(1 for path in root.rglob("result.json") if path.is_file())


def run_live_smoke(request: LiveSmokeRequest) -> dict[str, object]:
    if request.mode not in SMOKE_MODES:
        raise LiveSmokeError(f"unsupported_live_smoke_mode:{request.mode}")
    if not request.no_submit:
        raise LiveSmokeError("live_smoke_submit_not_supported")
    if request.policy_path:
        errors = validate_platform_config(request.policy_path)
        if errors:
            raise LiveSmokeError("platform_policy_invalid: " + "; ".join(errors))

    policy = get_platform_policy(request.platform, request.event, request.policy_path)
    adapter_name = _select_adapter_name(policy, request.adapter_name)
    source = _source_value(request, policy)
    smoke_id = make_run_id()
    smoke_dir = _output_dir(smoke_id, request.output)
    profile = _profile_validation(request, policy)

    result: dict[str, object] = {
        "schema_version": 1,
        "smoke_id": smoke_id,
        "created_at": iso_now(),
        "platform": request.platform,
        "event": request.event,
        "adapter": adapter_name,
        "requested_adapter": request.adapter_name,
        "mode": request.mode,
        "live": request.live,
        "dry_run": not request.live or request.mode == "dry-run",
        "no_submit": True,
        "submission": {
            "attempted": False,
            "reason": "smoke_framework_never_submits_flags",
            "policy": _policy_value(policy.automation.allow_submission),
        },
        "source_configured": bool(source),
        "source_summary": _safe_url(source) if source else "",
        "source_is_url": _is_url(source),
        "live_network_allowed": request.live,
        "live_network_performed": False,
        "policy": _policy_summary(policy),
        "profile": profile,
        "actions": {},
        "warnings": [],
    }
    warnings = result["warnings"] if isinstance(result["warnings"], list) else []
    if not source and request.mode in {"discovery", "download", "full-readonly"}:
        warnings.append("source_or_base_url_not_configured")
    if not profile.get("ok"):
        if request.live or profile.get("configured"):
            result["ok"] = False
            result["reason"] = profile.get("reason") or "profile_validation_failed"
        else:
            warnings.append(str(profile.get("reason") or "profile_not_configured"))

    actions = result["actions"] if isinstance(result["actions"], dict) else {}
    if result.get("ok") is False:
        pass
    elif not request.live:
        if request.mode == "dry-run":
            actions["dry_run"] = {"ok": True, "performed": False, "reason": "dry_run_no_network"}
        elif request.mode == "full-readonly":
            actions["discovery"] = _planned_action("discovery")
            actions["server_status"] = _planned_action("server-status")
        else:
            key = request.mode.replace("-", "_")
            actions[key] = _planned_action(request.mode)
        result["ok"] = True
        result["reason"] = "dry_run_no_network"
    elif request.mode == "dry-run":
        actions["dry_run"] = {"ok": True, "performed": False, "reason": "dry_run_mode_selected"}
        result["ok"] = True
    else:
        try:
            if request.mode in {"discovery", "full-readonly"}:
                actions["discovery"] = _run_discovery(
                    adapter_name=adapter_name,
                    request=request,
                    policy=policy,
                    source=source,
                )
            if request.mode == "download":
                actions["download"] = _run_download(
                    adapter_name=adapter_name,
                    request=request,
                    policy=policy,
                    source=source,
                    smoke_dir=smoke_dir,
                )
            if request.mode in {"server-status", "full-readonly"}:
                actions["server_status"] = _run_server_status(adapter_name=adapter_name, request=request)
            if request.mode == "server-acquire":
                actions["server_acquire"] = _run_server_acquire(adapter_name=adapter_name, request=request)
        finally:
            result["live_network_performed"] = bool(
                request.live
                and _is_url(source)
                and adapter_name not in {"mock", "local"}
                and any(
                    isinstance(action, dict) and bool(action.get("performed")) and bool(action.get("ok"))
                    for action in actions.values()
                )
            )
        result["ok"] = all(bool(action.get("ok", True)) for action in actions.values() if isinstance(action, dict))
        failed = [action for action in actions.values() if isinstance(action, dict) and not action.get("ok", True)]
        if failed:
            result["reason"] = str(failed[0].get("reason") or "live_smoke_action_failed")

    result["public_metrics"] = public_metrics_from_result(result)
    smoke_dir.mkdir(parents=True, exist_ok=True)
    result_path = smoke_dir / "result.json"
    summary_path = smoke_dir / "summary.md"
    result["result_path"] = display_path(result_path)
    result["summary_path"] = display_path(summary_path)
    atomic_write_json(result_path, result)
    atomic_write_text(summary_path, render_summary(result))
    return result
