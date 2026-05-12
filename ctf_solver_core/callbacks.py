"""Local-only web callback listener metadata, redaction, and payload helpers."""

from __future__ import annotations

import hashlib
import html
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import parse_qsl, quote, urlencode, urlsplit, urlunsplit
import uuid

from .paths import callback_root, callbackd_root, display_path, is_inside_repo
from .schemas import atomic_write_json, iso_now, read_json, read_jsonl, utc_now
from .sessions import REDACTED, bounded_text, redact_text


CALLBACK_STATUSES = ("starting", "running", "closed", "failed")
CONTROL_PREFIX = "/__ctf_solver_callback__"
DEFAULT_BODY_PREVIEW_BYTES = 4096
MAX_REQUEST_BODY_BYTES = 65536
DEFAULT_HIT_LIMIT = 20
MAX_HIT_LIMIT = 200
SENSITIVE_KEY_RE = re.compile(r"(token|session|cookie|password|passwd|secret|key|auth|flag)", re.IGNORECASE)
SENSITIVE_HEADER_RE = re.compile(
    r"^(authorization|cookie|set-cookie|proxy-authorization|x-api-key|x-csrf-token|x-auth-token|x-xsrf-token)$",
    re.IGNORECASE,
)
FLAG_LIKE_RE = re.compile(r"\b(?:DH|FLAG|flag)\{[^}\r\n]{3,512}\}", re.IGNORECASE)
ESCAPED_FLAG_LIKE_RE = re.compile(r"\b(?:DH|FLAG|flag)\\\{[^}\r\n]{3,512}\\\}", re.IGNORECASE)


class CallbackError(RuntimeError):
    """Raised when callback listener operations cannot proceed safely."""


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


def validate_local_only_root(path: Path, *, label: str) -> None:
    if is_inside_repo(path):
        raise CallbackError(f"{label}_inside_repo")


def validate_callback_roots() -> None:
    validate_local_only_root(callback_root(), label="callback_root")
    validate_local_only_root(callbackd_root(), label="callbackd_root")


def callbackd_status_path() -> Path:
    return callbackd_root() / "callbackd.json"


def make_listener_id() -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def make_hit_id() -> str:
    stamp = utc_now().strftime("%Y%m%dT%H%M%SZ")
    return f"{stamp}-{uuid.uuid4().hex[:8]}"


def listener_dir(listener_id: str) -> Path:
    return callback_root() / listener_id


def listener_metadata_path(listener_id: str) -> Path:
    return listener_dir(listener_id) / "listener.json"


def listener_hits_path(listener_id: str) -> Path:
    return listener_dir(listener_id) / "hits.jsonl"


def normalize_bind_host(host: str | None, *, allow_public_bind: bool = False) -> str:
    value = (host or "127.0.0.1").strip() or "127.0.0.1"
    if value == "localhost":
        return "127.0.0.1"
    if value in {"127.0.0.1", "::1"}:
        return value
    if value in {"0.0.0.0", "::"} and allow_public_bind:
        return value
    raise CallbackError("public bind requires --allow-public-bind")


def normalize_port(port: int | str | None) -> int:
    if port is None or str(port).strip() == "":
        return 0
    try:
        value = int(port)
    except (TypeError, ValueError) as exc:
        raise CallbackError("port must be an integer") from exc
    if value < 0 or value > 65535:
        raise CallbackError("port must be between 0 and 65535")
    return value


def normalize_external_base_url(value: str | None) -> str:
    if not value:
        return ""
    text = str(value).strip().rstrip("/")
    parsed = urlsplit(text)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise CallbackError("external_base_url must be an http(s) URL")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path.rstrip("/"), "", ""))


def normalize_token_path(value: str | None) -> str:
    if not value:
        return ""
    token = str(value).strip().strip("/")
    if not token:
        return ""
    if any(char in token for char in "?#"):
        raise CallbackError("token_path must not contain query or fragment characters")
    if ".." in token.split("/"):
        raise CallbackError("token_path must not contain path traversal")
    return token


def redact_sensitive_text(text: str) -> str:
    out = redact_text(str(text))
    out = FLAG_LIKE_RE.sub("<FLAG_REDACTED>", out)
    return ESCAPED_FLAG_LIKE_RE.sub("<FLAG_REDACTED>", out)


def _redact_structured(value: Any, key: str = "") -> Any:
    if SENSITIVE_KEY_RE.search(key):
        return REDACTED
    if isinstance(value, dict):
        return {str(item_key): _redact_structured(item_value, str(item_key)) for item_key, item_value in value.items()}
    if isinstance(value, list):
        return [_redact_structured(item, key) for item in value]
    if isinstance(value, str):
        return bounded_text(redact_sensitive_text(value), max_bytes=1024)
    return value


def redact_query(query: str) -> list[dict[str, str]]:
    pairs: list[dict[str, str]] = []
    for key, value in parse_qsl(query or "", keep_blank_values=True):
        safe_value = REDACTED if SENSITIVE_KEY_RE.search(key) else bounded_text(redact_sensitive_text(value), max_bytes=512)
        pairs.append({"key": bounded_text(key, max_bytes=128), "value": safe_value})
    return pairs


def redact_headers(headers: dict[str, Any] | None) -> dict[str, str]:
    redacted: dict[str, str] = {}
    for key, value in (headers or {}).items():
        key_text = str(key)
        if SENSITIVE_HEADER_RE.search(key_text):
            redacted[key_text] = REDACTED
        else:
            redacted[key_text] = bounded_text(redact_sensitive_text(str(value)), max_bytes=512)
    return redacted


def redact_path(path: str) -> str:
    return quote(redact_sensitive_text(path), safe="/:@")


def redact_body_preview(raw: bytes, content_type: str, *, max_bytes: int = DEFAULT_BODY_PREVIEW_BYTES) -> str:
    clipped = raw[: max(0, max_bytes)]
    text = clipped.decode("utf-8", errors="replace")
    lowered = content_type.lower()
    if "application/json" in lowered:
        try:
            parsed = json.loads(raw.decode("utf-8", errors="replace"))
            rendered = json.dumps(_redact_structured(parsed), ensure_ascii=False, sort_keys=True)
            return bounded_text(redact_sensitive_text(rendered), max_bytes=max_bytes)
        except Exception:
            return bounded_text(redact_sensitive_text(text), max_bytes=max_bytes)
    if "application/x-www-form-urlencoded" in lowered:
        pairs = []
        for key, value in parse_qsl(text, keep_blank_values=True):
            safe = REDACTED if SENSITIVE_KEY_RE.search(key) else redact_sensitive_text(value)
            pairs.append((key, safe))
        return bounded_text(urlencode(pairs), max_bytes=max_bytes)
    return bounded_text(redact_sensitive_text(text), max_bytes=max_bytes)


def new_listener_metadata(
    *,
    listener_id: str,
    run_id: str | None,
    challenge_id: str | None,
    worker_id: str | None,
    bind_host: str,
    port: int,
    external_base_url: str | None = None,
    token_path: str | None = None,
    status: str = "running",
) -> dict[str, object]:
    now = iso_now()
    root = listener_dir(listener_id)
    local_url = build_callback_url(
        {
            "listener_id": listener_id,
            "bind_host": bind_host,
            "port": port,
            "external_base_url": normalize_external_base_url(external_base_url),
            "token_path": normalize_token_path(token_path),
        }
    )
    external_url = ""
    if external_base_url:
        external_url = build_callback_url(
            {
                "listener_id": listener_id,
                "bind_host": bind_host,
                "port": port,
                "external_base_url": normalize_external_base_url(external_base_url),
                "token_path": normalize_token_path(token_path),
            },
            external=True,
        )
    return {
        "schema_version": 1,
        "listener_id": listener_id,
        "run_id": run_id or "",
        "challenge_id": challenge_id or "",
        "worker_id": worker_id or "",
        "bind_host": bind_host,
        "port": int(port),
        "external_base_url": normalize_external_base_url(external_base_url),
        "token_path": normalize_token_path(token_path),
        "status": status,
        "created_at": now,
        "updated_at": now,
        "closed_at": None,
        "close_reason": "",
        "hit_count": 0,
        "bytes_received": 0,
        "artifact_root": str(root),
        "hits_path": str(listener_hits_path(listener_id)),
        "local_url": local_url,
        "external_url": external_url,
        "last_hit_at": "",
        "last_error": "",
    }


def public_listener_metadata(metadata: dict[str, object]) -> dict[str, object]:
    item = dict(metadata)
    for key in ("artifact_root", "hits_path"):
        value = str(item.get(key) or "")
        if value:
            item[key] = display_path(Path(value))
    item.pop("control_token", None)
    return item


def build_callback_url(metadata: dict[str, object], *, external: bool = False, path: str | None = None) -> str:
    listener_id = str(metadata.get("listener_id") or "")
    if not listener_id:
        raise CallbackError("listener_id is required")
    token_path = normalize_token_path(str(metadata.get("token_path") or ""))
    extra_path = str(path or "").strip().strip("/")
    segments = [quote(listener_id, safe="")]
    if token_path:
        segments.extend(quote(part, safe="") for part in token_path.split("/") if part)
    if extra_path:
        segments.extend(quote(part, safe="") for part in extra_path.split("/") if part)
    route = "/" + "/".join(segments)
    if external:
        base = normalize_external_base_url(str(metadata.get("external_base_url") or ""))
        if not base:
            raise CallbackError("external_base_url is not configured")
        return f"{base}{route}"
    host = str(metadata.get("bind_host") or "127.0.0.1")
    if host in {"0.0.0.0", "::"}:
        host = "127.0.0.1"
    port = int(metadata.get("port") or 0)
    if port <= 0:
        raise CallbackError("listener port is not available")
    host_part = f"[{host}]" if ":" in host and not host.startswith("[") else host
    return f"http://{host_part}:{port}{route}"


def load_listener_metadata(listener_id: str) -> dict[str, object] | None:
    data = read_json(listener_metadata_path(listener_id), default={})
    return data if isinstance(data, dict) and data.get("listener_id") else None


def save_listener_metadata(metadata: dict[str, object]) -> None:
    listener_id = str(metadata.get("listener_id") or "")
    if not listener_id:
        raise CallbackError("listener_id is required")
    write_private_json(listener_metadata_path(listener_id), metadata)


def append_hit(listener_id: str, hit: dict[str, object]) -> None:
    path = listener_hits_path(listener_id)
    ensure_private_dir(path.parent)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(hit, ensure_ascii=False, sort_keys=True) + "\n")
    try:
        path.chmod(0o600)
    except OSError:
        pass


def make_hit(
    *,
    listener_id: str,
    method: str,
    path: str,
    query: str,
    headers: dict[str, Any],
    body: bytes,
    content_type: str,
    matched_token: bool | None,
) -> dict[str, object]:
    hit_id = make_hit_id()
    body_preview = redact_body_preview(body, content_type)
    size = len(body)
    redacted_query = redact_query(query)
    public_safe_summary = {
        "hit_id": hit_id,
        "method": str(method).upper(),
        "path": redact_path(path),
        "query_keys": [item["key"] for item in redacted_query],
        "content_type": bounded_text(content_type, max_bytes=128),
        "size": size,
        "matched_token": bool(matched_token) if matched_token is not None else None,
    }
    return {
        "schema_version": 1,
        "hit_id": hit_id,
        "timestamp": iso_now(),
        "listener_id": listener_id,
        "method": str(method).upper(),
        "path": redact_path(path),
        "query": redacted_query,
        "headers": redact_headers(headers),
        "body_preview": body_preview,
        "body_sha256": hashlib.sha256(body).hexdigest() if body else "",
        "content_type": bounded_text(content_type, max_bytes=128),
        "size": size,
        "matched_token": bool(matched_token) if matched_token is not None else None,
        "public_safe_summary": public_safe_summary,
    }


def read_hits(
    listener_id: str,
    *,
    since_hit_id: str | None = None,
    limit: int = DEFAULT_HIT_LIMIT,
) -> list[dict[str, object]]:
    records = read_jsonl(listener_hits_path(listener_id))
    if since_hit_id:
        for index, item in enumerate(records):
            if item.get("hit_id") == since_hit_id:
                records = records[index + 1 :]
                break
    capped = max(0, min(int(limit), MAX_HIT_LIMIT))
    return records[-capped:] if capped else []


def all_hits(listener_id: str) -> list[dict[str, object]]:
    return read_jsonl(listener_hits_path(listener_id))


def list_listener_metadata(
    *,
    run_id: str | None = None,
    challenge_id: str | None = None,
    include_closed: bool = False,
) -> list[dict[str, object]]:
    root = callback_root()
    records: list[dict[str, object]] = []
    for path in sorted(root.glob("*/listener.json")) if root.is_dir() else []:
        data = read_json(path, default={})
        if not isinstance(data, dict) or not data.get("listener_id"):
            continue
        if run_id and data.get("run_id") != run_id:
            continue
        if challenge_id and data.get("challenge_id") != challenge_id:
            continue
        if not include_closed and data.get("status") not in {"starting", "running"}:
            continue
        records.append(public_listener_metadata(data))
    records.sort(key=lambda item: str(item.get("created_at") or ""))
    return records


def active_listener_count() -> int:
    return len(list_listener_metadata(include_closed=False))


def mark_orphaned_listeners_for_run(run_id: str, *, reason: str) -> dict[str, object]:
    if not run_id:
        raise CallbackError("run_id is required")
    count = 0
    hit_count = 0
    bytes_received = 0
    for item in list_listener_metadata(run_id=run_id, include_closed=False):
        listener_id = str(item.get("listener_id") or "")
        data = load_listener_metadata(listener_id)
        if not data or data.get("status") not in {"starting", "running"}:
            continue
        data["status"] = "closed"
        data["closed_at"] = data.get("closed_at") or iso_now()
        data["close_reason"] = reason
        data["updated_at"] = iso_now()
        save_listener_metadata(data)
        count += 1
        hit_count += int(data.get("hit_count") or 0)
        bytes_received += int(data.get("bytes_received") or 0)
    return {
        "listener_count": count,
        "closed_callback_listener_count": count,
        "callback_hit_count": hit_count,
        "callback_bytes_received": bytes_received,
        "errors": [reason] if count else [],
    }


def callback_summary_for_run(run_id: str) -> dict[str, object]:
    listeners = list_listener_metadata(run_id=run_id, include_closed=True)
    summaries: list[dict[str, object]] = []
    hit_count = 0
    for listener in listeners:
        listener_id = str(listener.get("listener_id") or "")
        hits = all_hits(listener_id)
        hit_count += len(hits)
        last_hit = hits[-1].get("public_safe_summary") if hits and isinstance(hits[-1], dict) else None
        summaries.append(
            {
                "listener_id": listener_id,
                "status": listener.get("status"),
                "run_id": listener.get("run_id"),
                "challenge_id": listener.get("challenge_id"),
                "hit_count": len(hits),
                "last_hit": last_hit or {},
            }
        )
    return {
        "listener_count": len(listeners),
        "callback_hit_count": hit_count,
        "listeners": summaries,
    }


def generate_payload_snippets(callback_url: str) -> dict[str, object]:
    url = str(callback_url)
    if not urlsplit(url).scheme:
        raise CallbackError("callback_url must be absolute")
    html_url = html.escape(url, quote=True)
    js_url = json.dumps(url)
    css_url = url.replace("\\", "\\\\").replace('"', '\\"')
    return {
        "callback_url": url,
        "snippets": {
            "img_src": f'<img src="{html_url}" alt="">',
            "script_fetch": f"<script>fetch({js_url},{{mode:'no-cors'}})</script>",
            "fetch_post": f"<script>fetch({js_url},{{method:'POST',mode:'no-cors',body:'callback=1'}})</script>",
            "css_url": f'body{{background-image:url("{css_url}")}}',
            "markdown_image": f"![callback]({url})",
        },
        "note": "helper snippets only; no tunnel provider or exploit solver is invoked",
    }
