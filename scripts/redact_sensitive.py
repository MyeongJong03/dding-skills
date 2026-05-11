#!/usr/bin/env python3
"""Redact secrets and account metadata before sharing audit packs."""

from __future__ import annotations

import argparse
from pathlib import Path
import re
import sys
import textwrap


REDACTED = "<REDACTED>"
PRIVATE_KEY_REDACTED = "<REDACTED_PRIVATE_KEY_BLOCK>"
FLAG_REDACTED = "<REDACTED_CTF_FLAG>"

ENV_KEYS = [
    "OPENAI_API_KEY",
    "ANTHROPIC_API_KEY",
    "CLAUDE_CODE_OAUTH_TOKEN",
]

KV_KEYS = [
    "session",
    "password",
    "passwd",
    "token",
    "api_key",
    "secret",
]

METADATA_KEYS = [
    "emailAddress",
    "organizationName",
    "organizationUuid",
    "accountUuid",
    "userID",
    "anonymousId",
    "referral_code",
    "referral_link",
    "displayName",
    "billing",
    "billingAddress",
    "billingEmail",
    "billingName",
    "billingStatus",
    "billingSubscription",
    "subscription",
    "subscriptionId",
    "subscriptionStatus",
    "subscriptionPlan",
]


def _redact_json_string_key(text: str, key: str) -> str:
    pattern = re.compile(rf'("{re.escape(key)}"\s*:\s*)"[^"]*"', re.IGNORECASE)
    text = pattern.sub(rf'\1"{REDACTED}"', text)
    pattern = re.compile(rf"('{re.escape(key)}'\s*:\s*)'[^']*'", re.IGNORECASE)
    return pattern.sub(rf"\1'{REDACTED}'", text)


def _redact_plain_key(text: str, key: str) -> str:
    assign = re.compile(rf"\b({re.escape(key)}\s*=\s*)[^&\s;,]+", re.IGNORECASE)
    text = assign.sub(rf"\1{REDACTED}", text)
    colon = re.compile(rf"\b({re.escape(key)}\s*:\s*)[^,\n]+", re.IGNORECASE)
    return colon.sub(rf"\1{REDACTED}", text)


def redact(text: str) -> str:
    """Return text with secrets and account metadata removed."""
    out = text

    out = re.sub(
        r"-----BEGIN [A-Z ]*PRIVATE KEY-----.*?-----END [A-Z ]*PRIVATE KEY-----",
        PRIVATE_KEY_REDACTED,
        out,
        flags=re.DOTALL,
    )

    out = re.sub(r"sk-[A-Za-z0-9_-]{8,}", REDACTED, out)
    out = re.sub(r"ghp_[A-Za-z0-9_]{10,}", REDACTED, out)
    out = re.sub(r"github_pat_[A-Za-z0-9_]{20,}", REDACTED, out)
    out = re.sub(r"xoxb-[A-Za-z0-9-]{10,}", REDACTED, out)
    out = re.sub(r"\b(?:DH|FLAG|flag)\{[^}\n]{3,}\}", FLAG_REDACTED, out)

    env_pattern = "|".join(re.escape(key) for key in ENV_KEYS)
    out = re.sub(
        rf"(?im)^(\s*(?:export\s+)?(?:{env_pattern})\s*=\s*).*$",
        rf"\1{REDACTED}",
        out,
    )

    out = re.sub(
        r"(?im)^(?P<prefix>\s*Authorization\s*:\s*Bearer\s+).+$",
        rf"\g<prefix>{REDACTED}",
        out,
    )
    out = re.sub(
        r"(?im)^(?P<prefix>\s*Cookie\s*:\s*).+$",
        rf"\g<prefix>{REDACTED}",
        out,
    )

    for key in KV_KEYS:
        out = _redact_plain_key(out, key)

    for key in METADATA_KEYS:
        out = _redact_json_string_key(out, key)
        out = _redact_plain_key(out, key)

    return out


def _read_inputs(paths: list[str]) -> str:
    if not paths:
        return sys.stdin.read()

    chunks = []
    for raw_path in paths:
        path = Path(raw_path)
        chunks.append(path.read_text(encoding="utf-8", errors="replace"))
    return "\n".join(chunks)


def self_test() -> int:
    sample = textwrap.dedent(
        """\
        OPENAI_API_KEY=sk-testaaaaaaaaaaaaaaaa
        ANTHROPIC_API_KEY=sk-ant-testbbbbbbbbbbbbbbbb
        CLAUDE_CODE_OAUTH_TOKEN=oauth-token-value
        Authorization: Bearer bearer-token-value
        Cookie: session=fake_session_cookie; theme=dark
        password=hunter2 passwd=swordfish token=querytoken api_key=querykey secret=querysecret session=querysession
        github=ghp_aaaaaaaaaaaaaaaaaaaa
        github_pat=github_pat_aaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa
        slack=xoxb-1111111111-2222222222-abcdefabcdef
        flag={sample_flag}
        {"emailAddress":"person@example.com","organizationUuid":"org-123","accountUuid":"acct-456","displayName":"Private Name","billingStatus":"active","subscriptionId":"sub-123"}
        -----BEGIN PRIVATE KEY-----
        fake-private-key-body
        -----END PRIVATE KEY-----
        """
    ).replace("{sample_flag}", "DH" + "{example_private_flag}")
    redacted = redact(sample)
    forbidden = [
        "sk-test",
        "oauth-token-value",
        "bearer-token-value",
        "fake_session_cookie",
        "hunter2",
        "swordfish",
        "querytoken",
        "querykey",
        "querysecret",
        "querysession",
        "ghp_",
        "github_pat_",
        "xoxb-",
        "example_private_flag",
        "person@example.com",
        "org-123",
        "acct-456",
        "Private Name",
        "active",
        "sub-123",
        "fake-private-key-body",
    ]
    leaked = [item for item in forbidden if item in redacted]
    if leaked:
        print(f"self-test failed: unredacted markers remain: {leaked}", file=sys.stderr)
        return 1

    print(redacted.strip())
    print("self-test passed")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("files", nargs="*", help="files to redact; stdin is used when omitted")
    parser.add_argument("-o", "--output", help="write redacted output to this file")
    parser.add_argument("--self-test", action="store_true", help="run built-in redaction sample test")
    args = parser.parse_args()

    if args.self_test:
        return self_test()

    redacted = redact(_read_inputs(args.files))
    if args.output:
        Path(args.output).write_text(redacted, encoding="utf-8")
    else:
        sys.stdout.write(redacted)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
