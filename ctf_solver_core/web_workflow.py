"""Web exploit workflow scaffold tying browser, callback, payloads, and evidence."""

from __future__ import annotations

from pathlib import Path
import json
import re
from typing import Any
import uuid

from .browser_actions import redact_url
from .browser_client import (
    browser_click,
    browser_close,
    browser_console,
    browser_eval,
    browser_fill,
    browser_goto,
    browser_list,
    browser_network,
    browser_screenshot,
    browser_start,
    browser_upload,
)
from .callback_client import callback_close, callback_hits, callback_start, callback_wait
from .callbacks import redact_sensitive_text
from .paths import display_path, is_inside_repo, local_run_root, web_workflow_root
from .schemas import atomic_write_json, atomic_write_text, iso_now, read_json, utc_now
from .sessions import REDACTED, bounded_text
from .web_payloads import PAYLOAD_TYPES, generate_web_payloads


WORKFLOW_STATUSES = (
    "initialized",
    "probing",
    "evidence_collected",
    "verified",
    "closed",
    "failed",
)
SENSITIVE_KEY_RE = re.compile(r"(token|session|cookie|password|passwd|secret|key|auth|flag)", re.IGNORECASE)
DEFAULT_WAIT_TIMEOUT_SEC = 15.0


class WebWorkflowError(RuntimeError):
    """Raised when a web workflow operation cannot proceed safely."""


def ensure_private_dir(path: Path) -> None:
    path.mkdir(parents=True, exist_ok=True)
    try:
        path.chmod(0o700)
    except OSError:
        pass


def write_private_json(path: Path, data: object) -> None:
    ensure_private_dir(path.parent)
    atomic_write_json(path, data)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def write_private_text(path: Path, text: str) -> None:
    ensure_private_dir(path.parent)
    atomic_write_text(path, text)
    try:
        path.chmod(0o600)
    except OSError:
        pass


def validate_web_workflow_root() -> None:
    if is_inside_repo(web_workflow_root()):
        raise WebWorkflowError("web_workflow_root_inside_repo")


def make_workflow_id() -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def workflow_dir(workflow_id: str) -> Path:
    if not workflow_id or "/" in workflow_id or "\\" in workflow_id or ".." in workflow_id:
        raise WebWorkflowError("invalid workflow_id")
    return web_workflow_root() / workflow_id


def workflow_metadata_path(workflow_id: str) -> Path:
    return workflow_dir(workflow_id) / "workflow.json"


def workflow_evidence_path(workflow_id: str) -> Path:
    return workflow_dir(workflow_id) / "evidence.json"


def workflow_summary_path(workflow_id: str) -> Path:
    return workflow_dir(workflow_id) / "summary.md"


def _now_touch(metadata: dict[str, object]) -> None:
    metadata["updated_at"] = iso_now()


def _save_workflow(metadata: dict[str, object]) -> None:
    workflow_id = str(metadata.get("workflow_id") or "")
    if not workflow_id:
        raise WebWorkflowError("workflow_id is required")
    _now_touch(metadata)
    write_private_json(workflow_metadata_path(workflow_id), metadata)


def load_workflow(workflow_id: str) -> dict[str, object]:
    data = read_json(workflow_metadata_path(workflow_id), default={})
    if not isinstance(data, dict) or not data.get("workflow_id"):
        raise WebWorkflowError(f"unknown workflow_id: {workflow_id}")
    return data


def _redact_value(value: Any, key: str = "") -> Any:
    if key in {"workflow_id", "run_id", "challenge_id", "worker_id", "browser_session_id", "callback_listener_id"}:
        return bounded_text(str(value), max_bytes=256)
    if SENSITIVE_KEY_RE.search(key):
        return REDACTED
    if isinstance(value, dict):
        if isinstance(value.get("public_safe_summary"), dict):
            return _redact_value(value["public_safe_summary"])
        return {str(item_key): _redact_value(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_value(item, key) for item in value[:20]]
    if isinstance(value, str):
        if key in {"url", "target_url", "current_url", "callback_url", "external_callback_url", "local_callback_url"}:
            return bounded_text(redact_url(value), max_bytes=1000)
        return bounded_text(redact_sensitive_text(value), max_bytes=2000)
    return value


def _result_summary(result: dict[str, object]) -> dict[str, object]:
    return _redact_value(result)


def _public_workflow(metadata: dict[str, object]) -> dict[str, object]:
    item = _redact_value(metadata)
    if not isinstance(item, dict):
        return {}
    workflow_id = str(metadata.get("workflow_id") or "")
    if workflow_id:
        item["display_workflow_dir"] = display_path(workflow_dir(workflow_id))
        if workflow_evidence_path(workflow_id).is_file():
            item["display_evidence_path"] = display_path(workflow_evidence_path(workflow_id))
        if workflow_summary_path(workflow_id).is_file():
            item["display_summary_path"] = display_path(workflow_summary_path(workflow_id))
    return item


def _append_event(metadata: dict[str, object], event_type: str, payload: dict[str, object]) -> None:
    events = metadata.setdefault("events", [])
    if isinstance(events, list):
        events.append(
            {
                "timestamp": iso_now(),
                "type": event_type,
                "summary": _result_summary(payload),
            }
        )
        del events[:-50]


def _callback_url_from_start(started: dict[str, object]) -> tuple[str, str]:
    local = str(started.get("local_url") or "")
    external = str(started.get("external_url") or "")
    return local, external


def _listener_url_from_workflow(metadata: dict[str, object], explicit: str | None = None) -> str:
    if explicit:
        return explicit
    external = str(metadata.get("external_callback_url") or "")
    local = str(metadata.get("local_callback_url") or "")
    if external:
        return external
    if local:
        return local
    raise WebWorkflowError("callback_url is required; start a callback listener or pass --callback-url")


def _browser_session_id_from_result(result: dict[str, object]) -> str:
    session = result.get("session")
    if isinstance(session, dict):
        return str(session.get("browser_session_id") or "")
    return ""


def init_workflow(
    *,
    run_id: str | None = None,
    challenge_id: str | None = None,
    worker_id: str | None = None,
    target_url: str | None = None,
    start_browser: bool = False,
    start_callback: bool = False,
    browser_profile: str | None = None,
    external_base_url: str | None = None,
) -> dict[str, object]:
    validate_web_workflow_root()
    workflow_id = make_workflow_id()
    now = iso_now()
    metadata: dict[str, object] = {
        "schema_version": 1,
        "workflow_id": workflow_id,
        "run_id": run_id or "",
        "challenge_id": challenge_id or "",
        "worker_id": worker_id or "",
        "browser_session_id": "",
        "callback_listener_id": "",
        "target_url": redact_url(str(target_url or "")) if target_url else "",
        "external_callback_url": "",
        "local_callback_url": "",
        "payloads": [],
        "payload_count": 0,
        "browser_action_count": 0,
        "callback_probe_success": False,
        "evidence_summaries": [],
        "status": "initialized",
        "created_at": now,
        "updated_at": now,
        "closed_at": "",
        "close_reason": "",
        "events": [],
    }
    ensure_private_dir(workflow_dir(workflow_id))

    if start_browser:
        result = browser_start(
            run_id=run_id,
            challenge_id=challenge_id,
            worker_id=worker_id,
            profile=browser_profile,
        )
        session_id = _browser_session_id_from_result(result)
        if session_id and result.get("ok"):
            metadata["browser_session_id"] = session_id
        else:
            metadata["browser_start_error"] = str(result.get("reason") or result.get("error") or "browser_start_failed")
        _append_event(metadata, "browser_start", result)

    if start_callback:
        result = callback_start(
            run_id=run_id,
            challenge_id=challenge_id,
            worker_id=worker_id,
            external_base_url=external_base_url,
        )
        listener_id = str(result.get("listener_id") or "")
        local_url, external_url = _callback_url_from_start(result)
        metadata["callback_listener_id"] = listener_id
        metadata["local_callback_url"] = local_url
        metadata["external_callback_url"] = external_url
        _append_event(metadata, "callback_start", result)

    _save_workflow(metadata)
    return {"ok": True, "workflow": _public_workflow(metadata)}


def generate_payloads_for_workflow(
    *,
    workflow_id: str | None = None,
    callback_url: str | None = None,
    types: list[str] | None = None,
    target_param: str | None = None,
    encode: str | None = None,
) -> dict[str, object]:
    metadata = load_workflow(workflow_id) if workflow_id else None
    target_url = str(metadata.get("target_url") or "") if metadata else ""
    url = _listener_url_from_workflow(metadata or {}, callback_url)
    result = generate_web_payloads(
        callback_url=url,
        types=types or list(PAYLOAD_TYPES),
        target_param=target_param,
        encode=encode,
        target_url=target_url,
    )
    if metadata is not None:
        summaries = [
            {
                "type": item.get("type"),
                "helper": True,
                "encoding": item.get("encoding") or "",
                "snippet_preview": item.get("snippet_preview") or "",
            }
            for item in result.get("payloads", [])
            if isinstance(item, dict)
        ]
        payloads = metadata.setdefault("payloads", [])
        if isinstance(payloads, list):
            payloads.extend(summaries)
            del payloads[:-200]
        metadata["payload_count"] = int(metadata.get("payload_count") or 0) + int(result.get("count") or 0)
        _append_event(metadata, "payload_generate", {"count": int(result.get("count") or 0), "types": types or []})
        _save_workflow(metadata)
        result["workflow_id"] = str(metadata.get("workflow_id") or "")
    return result


def browser_probe(
    *,
    workflow_id: str,
    action: str,
    url: str | None = None,
    selector: str | None = None,
    value: str | None = None,
    file: str | None = None,
    expression: str | None = None,
    timeout_ms: int | None = None,
) -> dict[str, object]:
    metadata = load_workflow(workflow_id)
    browser_session_id = str(metadata.get("browser_session_id") or "")
    if not browser_session_id:
        result = {"ok": False, "reason": "no_browser_session_id", "workflow_id": workflow_id}
        _append_event(metadata, "browser_probe", result)
        _save_workflow(metadata)
        return result

    timeout = max(1, int(timeout_ms or 10_000))
    if action == "goto":
        target = url or str(metadata.get("target_url") or "")
        result = browser_goto(browser_session_id, url=target, timeout_ms=timeout)
    elif action == "fill":
        result = browser_fill(browser_session_id, selector=str(selector or ""), value=str(value or ""), timeout_ms=timeout)
    elif action == "click":
        result = browser_click(browser_session_id, selector=str(selector or ""), timeout_ms=timeout)
    elif action == "upload":
        result = browser_upload(browser_session_id, selector=str(selector or ""), files=[str(file or "")], timeout_ms=timeout)
    elif action == "eval":
        result = browser_eval(browser_session_id, expression=str(expression or ""), timeout_ms=timeout)
    elif action == "screenshot":
        result = browser_screenshot(browser_session_id, name=value or "web-workflow")
    else:
        raise WebWorkflowError(f"unsupported browser action: {action}")

    metadata["status"] = "probing"
    metadata["browser_action_count"] = int(metadata.get("browser_action_count") or 0) + 1
    _append_event(metadata, f"browser_{action}", result)
    _save_workflow(metadata)
    return {"workflow_id": workflow_id, "result": _result_summary(result), "ok": bool(result.get("ok"))}


def _hit_summaries(hits: list[dict[str, object]], limit: int = 5) -> list[dict[str, object]]:
    summaries: list[dict[str, object]] = []
    for hit in hits[-max(0, limit) :]:
        if not isinstance(hit, dict):
            continue
        summary = hit.get("public_safe_summary")
        if isinstance(summary, dict):
            summaries.append(_redact_value(summary))
    return summaries


def callback_probe(
    *,
    workflow_id: str,
    wait_timeout_sec: float = DEFAULT_WAIT_TIMEOUT_SEC,
    pattern: str | None = None,
    min_hits: int = 1,
) -> dict[str, object]:
    metadata = load_workflow(workflow_id)
    listener_id = str(metadata.get("callback_listener_id") or "")
    if not listener_id:
        result = {"ok": False, "reason": "no_callback_listener_id", "workflow_id": workflow_id}
        _append_event(metadata, "callback_probe", result)
        _save_workflow(metadata)
        return result

    result = callback_wait(
        listener_id,
        timeout_sec=max(0.0, float(wait_timeout_sec)),
        pattern=pattern,
        min_hits=max(1, int(min_hits)),
    )
    hits = [item for item in (result.get("hits") or []) if isinstance(item, dict)]
    evidence = {
        "type": "callback",
        "listener_id": listener_id,
        "ok": bool(result.get("ok")),
        "timed_out": bool(result.get("timed_out")),
        "matched_count": int(result.get("count") or 0),
        "min_hits": max(1, int(min_hits)),
        "pattern_configured": bool(pattern),
        "duration_sec": result.get("duration_sec") if isinstance(result.get("duration_sec"), (int, float)) else 0,
        "hit_summaries": _hit_summaries(hits),
        "timestamp": iso_now(),
    }
    evidence_summaries = metadata.setdefault("evidence_summaries", [])
    if isinstance(evidence_summaries, list):
        evidence_summaries.append(evidence)
        del evidence_summaries[:-50]
    metadata["callback_probe_success"] = bool(result.get("ok"))
    metadata["status"] = "evidence_collected" if result.get("ok") else "probing"
    _append_event(metadata, "callback_probe", evidence)
    _save_workflow(metadata)
    return {"ok": bool(result.get("ok")), "workflow_id": workflow_id, "evidence": evidence}


def _discover_run_dir(run_id: str, challenge_id: str | None = None) -> Path | None:
    if not run_id:
        return None
    if challenge_id:
        candidate = local_run_root() / challenge_id / run_id
        if (candidate / "challenge.json").is_file():
            return candidate
    root = local_run_root()
    for path in sorted(root.glob(f"*/{run_id}/challenge.json")) if root.is_dir() else []:
        return path.parent
    return None


def _callback_summary(metadata: dict[str, object]) -> dict[str, object]:
    listener_id = str(metadata.get("callback_listener_id") or "")
    if not listener_id:
        return {"configured": False, "listener_id": "", "hit_count": 0, "hit_summaries": []}
    try:
        result = callback_hits(listener_id, limit=20)
        hits = [item for item in (result.get("hits") or []) if isinstance(item, dict)]
        return {
            "configured": True,
            "listener_id": listener_id,
            "hit_count": int(result.get("count") or len(hits)),
            "hit_summaries": _hit_summaries(hits),
        }
    except Exception as exc:
        return {"configured": True, "listener_id": listener_id, "hit_count": 0, "error": str(exc), "hit_summaries": []}


def _browser_summary(metadata: dict[str, object]) -> dict[str, object]:
    browser_session_id = str(metadata.get("browser_session_id") or "")
    summary: dict[str, object] = {
        "configured": bool(browser_session_id),
        "browser_session_id": browser_session_id,
        "action_count": int(metadata.get("browser_action_count") or 0),
    }
    if not browser_session_id:
        return summary
    try:
        listed = browser_list(
            run_id=str(metadata.get("run_id") or "") or None,
            challenge_id=str(metadata.get("challenge_id") or "") or None,
            include_closed=True,
        )
        for item in listed.get("sessions") or []:
            if isinstance(item, dict) and item.get("browser_session_id") == browser_session_id:
                summary["session"] = _redact_value(item)
                break
    except Exception as exc:
        summary["list_error"] = str(exc)
    try:
        summary["console"] = _result_summary(browser_console(browser_session_id, limit=5))
    except Exception as exc:
        summary["console_error"] = str(exc)
    try:
        summary["network"] = _result_summary(browser_network(browser_session_id, limit=5))
    except Exception as exc:
        summary["network_error"] = str(exc)
    return summary


def _verifier_summary(run_dir: Path | None) -> dict[str, object]:
    if not run_dir:
        return {}
    from .verifier import load_verifier_result, verifier_summary

    return verifier_summary(load_verifier_result(run_dir), include_preview=True)


def _render_summary(evidence: dict[str, object]) -> str:
    lines = [
        f"# Web Workflow Evidence: {evidence.get('workflow_id')}",
        "",
        f"- Status: `{evidence.get('status')}`",
        f"- Run ID: `{evidence.get('run_id') or '-'}`",
        f"- Challenge ID: `{evidence.get('challenge_id') or '-'}`",
        f"- Payload count: `{evidence.get('payload_count')}`",
        f"- Browser action count: `{evidence.get('browser_action_count')}`",
        f"- Callback probe success: `{bool(evidence.get('callback_probe_success'))}`",
        f"- Callback hit count: `{evidence.get('callback_hit_count')}`",
        f"- Generated at: `{evidence.get('generated_at')}`",
        "",
        "## Callback",
        "",
    ]
    callback = evidence.get("callback_summary") if isinstance(evidence.get("callback_summary"), dict) else {}
    lines.append(f"- Listener configured: `{bool(callback.get('configured'))}`")
    lines.append(f"- Hit count: `{callback.get('hit_count') or 0}`")
    for item in callback.get("hit_summaries") or []:
        if isinstance(item, dict):
            lines.append(
                f"- `{item.get('method')}` `{item.get('path')}` size `{item.get('size')}` "
                f"matched_token `{item.get('matched_token')}`"
            )
    lines.extend(["", "## Browser", ""])
    browser = evidence.get("browser_summary") if isinstance(evidence.get("browser_summary"), dict) else {}
    lines.append(f"- Browser configured: `{bool(browser.get('configured'))}`")
    lines.append(f"- Action count: `{browser.get('action_count') or 0}`")
    verifier = evidence.get("verifier_summary") if isinstance(evidence.get("verifier_summary"), dict) else {}
    if verifier:
        lines.extend(
            [
                "",
                "## Verifier",
                "",
                f"- Success: `{bool(verifier.get('success'))}`",
                f"- Mode: `{verifier.get('mode')}`",
                f"- Target: `{verifier.get('target')}`",
            ]
        )
    lines.append("")
    return "\n".join(lines)


def collect_evidence(
    *,
    workflow_id: str,
    include_browser_summary: bool = False,
    include_callback_summary: bool = False,
    include_verifier_summary: bool = False,
) -> dict[str, object]:
    validate_web_workflow_root()
    metadata = load_workflow(workflow_id)
    run_id = str(metadata.get("run_id") or "")
    challenge_id = str(metadata.get("challenge_id") or "")
    run_dir = _discover_run_dir(run_id, challenge_id)
    callback_summary = _callback_summary(metadata) if include_callback_summary else {}
    browser_summary = _browser_summary(metadata) if include_browser_summary else {}
    verifier = _verifier_summary(run_dir) if include_verifier_summary else {}

    evidence: dict[str, object] = {
        "schema_version": 1,
        "workflow_id": workflow_id,
        "run_id": run_id,
        "challenge_id": challenge_id,
        "status": metadata.get("status"),
        "target_url": redact_url(str(metadata.get("target_url") or "")),
        "payload_count": int(metadata.get("payload_count") or 0),
        "browser_action_count": int(metadata.get("browser_action_count") or 0),
        "callback_probe_success": bool(metadata.get("callback_probe_success")),
        "callback_hit_count": int(callback_summary.get("hit_count") or 0) if callback_summary else 0,
        "generated_at": iso_now(),
        "callback_summary": callback_summary,
        "browser_summary": browser_summary,
        "verifier_summary": verifier,
        "evidence_summaries": _redact_value(metadata.get("evidence_summaries") or []),
    }
    write_private_json(workflow_evidence_path(workflow_id), evidence)
    summary_text = _render_summary(evidence)
    write_private_text(workflow_summary_path(workflow_id), summary_text)
    copied_to_run_dir = False
    if run_dir:
        copy_path = run_dir / "logs" / "web-evidence-summary.md"
        write_private_text(copy_path, summary_text)
        copied_to_run_dir = True
    metadata["status"] = "evidence_collected" if metadata.get("status") != "closed" else "closed"
    _append_event(metadata, "evidence_collect", {"callback_hit_count": evidence["callback_hit_count"]})
    _save_workflow(metadata)
    return {
        "ok": True,
        "workflow_id": workflow_id,
        "display_evidence_path": display_path(workflow_evidence_path(workflow_id)),
        "display_summary_path": display_path(workflow_summary_path(workflow_id)),
        "copied_summary_to_run_dir": copied_to_run_dir,
        "evidence": {
            "payload_count": evidence["payload_count"],
            "browser_action_count": evidence["browser_action_count"],
            "callback_probe_success": evidence["callback_probe_success"],
            "callback_hit_count": evidence["callback_hit_count"],
        },
    }


def close_workflow(
    *,
    workflow_id: str,
    close_browser: bool = True,
    close_callback: bool = True,
    reason: str = "closed",
) -> dict[str, object]:
    metadata = load_workflow(workflow_id)
    results: dict[str, object] = {}
    errors: list[str] = []
    warnings: list[str] = []
    browser_session_id = str(metadata.get("browser_session_id") or "")
    listener_id = str(metadata.get("callback_listener_id") or "")
    if close_browser and browser_session_id:
        try:
            results["browser"] = _result_summary(browser_close(browser_session_id, reason=reason))
        except Exception as exc:
            text = str(exc)
            if "unknown or inactive browser session" in text or "browser session is not running" in text:
                warnings.append(f"browser:{text}")
            else:
                errors.append(f"browser:{text}")
    if close_callback and listener_id:
        try:
            results["callback"] = _result_summary(callback_close(listener_id, reason=reason))
        except Exception as exc:
            text = str(exc)
            if "unknown listener_id" in text:
                warnings.append(f"callback:{text}")
            else:
                errors.append(f"callback:{text}")
    already_closed = metadata.get("status") == "closed"
    metadata["status"] = "closed"
    metadata["closed_at"] = metadata.get("closed_at") or iso_now()
    metadata["close_reason"] = reason
    _append_event(metadata, "workflow_close", {"already_closed": already_closed, "errors": errors})
    _save_workflow(metadata)
    return {
        "ok": not errors,
        "workflow_id": workflow_id,
        "status": "closed",
        "already_closed": already_closed,
        "results": results,
        "errors": errors,
        "warnings": warnings,
    }


def list_workflows(
    *,
    run_id: str | None = None,
    challenge_id: str | None = None,
    include_closed: bool = False,
) -> dict[str, object]:
    records: list[dict[str, object]] = []
    root = web_workflow_root()
    for path in sorted(root.glob("*/workflow.json")) if root.is_dir() else []:
        data = read_json(path, default={})
        if not isinstance(data, dict) or not data.get("workflow_id"):
            continue
        if run_id and data.get("run_id") != run_id:
            continue
        if challenge_id and data.get("challenge_id") != challenge_id:
            continue
        if not include_closed and data.get("status") == "closed":
            continue
        records.append(_public_workflow(data))
    records.sort(key=lambda item: str(item.get("created_at") or ""))
    return {"ok": True, "workflows": records, "count": len(records)}


def active_web_workflow_count() -> int:
    return int(list_workflows(include_closed=False).get("count") or 0)


def close_web_workflows_for_run(run_id: str, *, reason: str = "challenge_finalized") -> dict[str, object]:
    if not run_id:
        raise WebWorkflowError("run_id is required")
    workflows = list_workflows(run_id=run_id, include_closed=False).get("workflows") or []
    closed = 0
    evidence_count = 0
    payload_count = 0
    browser_actions = 0
    callback_probe_success = False
    errors: list[str] = []
    for item in workflows:
        if not isinstance(item, dict):
            continue
        workflow_id = str(item.get("workflow_id") or "")
        try:
            collected = collect_evidence(
                workflow_id=workflow_id,
                include_browser_summary=True,
                include_callback_summary=True,
                include_verifier_summary=True,
            )
            if collected.get("ok"):
                evidence_count += 1
        except Exception as exc:
            errors.append(f"{workflow_id}:evidence:{exc}")
        try:
            metadata = load_workflow(workflow_id)
            payload_count += int(metadata.get("payload_count") or 0)
            browser_actions += int(metadata.get("browser_action_count") or 0)
            callback_probe_success = callback_probe_success or bool(metadata.get("callback_probe_success"))
            result = close_workflow(workflow_id=workflow_id, close_browser=True, close_callback=True, reason=reason)
            if result.get("status") == "closed":
                closed += 1
            if result.get("errors"):
                errors.extend(str(error) for error in result.get("errors") or [])
        except Exception as exc:
            errors.append(f"{workflow_id}:close:{exc}")
    return {
        "ok": not errors,
        "web_workflow_count": len(workflows),
        "closed_web_workflow_count": closed,
        "web_evidence_count": evidence_count,
        "web_payload_count": payload_count,
        "web_browser_action_count": browser_actions,
        "web_callback_probe_success": callback_probe_success,
        "web_evidence_collected": evidence_count > 0,
        "errors": errors,
    }


def collect_web_evidence_for_run(run_id: str) -> dict[str, object]:
    if not run_id:
        raise WebWorkflowError("run_id is required")
    workflows = list_workflows(run_id=run_id, include_closed=False).get("workflows") or []
    evidence_count = 0
    errors: list[str] = []
    for item in workflows:
        if not isinstance(item, dict):
            continue
        workflow_id = str(item.get("workflow_id") or "")
        try:
            result = collect_evidence(
                workflow_id=workflow_id,
                include_browser_summary=True,
                include_callback_summary=True,
                include_verifier_summary=True,
            )
            if result.get("ok"):
                evidence_count += 1
        except Exception as exc:
            errors.append(f"{workflow_id}:evidence:{exc}")
    return {
        "ok": not errors,
        "web_workflow_count": len(workflows),
        "web_evidence_count": evidence_count,
        "errors": errors,
    }


def workflow_verifier_evidence(workflow_id: str) -> dict[str, object]:
    metadata = load_workflow(workflow_id)
    evidence_path = workflow_evidence_path(workflow_id)
    evidence = read_json(evidence_path, default={}) if evidence_path.is_file() else {}
    if not isinstance(evidence, dict):
        evidence = {}
    callback = evidence.get("callback_summary") if isinstance(evidence.get("callback_summary"), dict) else {}
    text = json.dumps(
        {
            "workflow_id": workflow_id,
            "status": metadata.get("status"),
            "payload_count": metadata.get("payload_count") or 0,
            "browser_action_count": metadata.get("browser_action_count") or 0,
            "callback_probe_success": bool(metadata.get("callback_probe_success")),
            "callback_hit_count": callback.get("hit_count") or 0,
            "evidence_collected": evidence_path.is_file(),
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return {
        "workflow_id": workflow_id,
        "callback_listener_id": str(metadata.get("callback_listener_id") or ""),
        "evidence_text": bounded_text(redact_sensitive_text(text), max_bytes=4000),
    }


def mark_workflow_verified(workflow_id: str, verifier: dict[str, object]) -> None:
    metadata = load_workflow(workflow_id)
    metadata["status"] = "verified"
    _append_event(
        metadata,
        "workflow_verified",
        {
            "verifier_id": verifier.get("verifier_id"),
            "success": bool(verifier.get("success")),
            "target": verifier.get("target"),
            "mode": verifier.get("mode"),
        },
    )
    _save_workflow(metadata)


def web_evidence_summaries_for_run(run_id: str) -> dict[str, object]:
    if not run_id:
        return {"workflow_count": 0, "evidence_count": 0, "workflows": []}
    workflows = list_workflows(run_id=run_id, include_closed=True).get("workflows") or []
    summaries: list[dict[str, object]] = []
    evidence_count = 0
    for item in workflows:
        if not isinstance(item, dict):
            continue
        workflow_id = str(item.get("workflow_id") or "")
        evidence = read_json(workflow_evidence_path(workflow_id), default={})
        if isinstance(evidence, dict) and evidence:
            evidence_count += 1
        callback = evidence.get("callback_summary") if isinstance(evidence.get("callback_summary"), dict) else {}
        summaries.append(
            {
                "workflow_id": workflow_id,
                "status": item.get("status"),
                "payload_count": int(item.get("payload_count") or 0),
                "browser_action_count": int(item.get("browser_action_count") or 0),
                "callback_probe_success": bool(item.get("callback_probe_success")),
                "callback_hit_count": int(callback.get("hit_count") or 0) if callback else 0,
                "evidence_collected": bool(evidence),
            }
        )
    return {
        "workflow_count": len(summaries),
        "evidence_count": evidence_count,
        "workflows": summaries,
    }
