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
PATH_REDACTED = "<REDACTED_PATH>"
UUID_REDACTED = "<REDACTED_UUID>"

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
    "organizationId",
    "accountUuid",
    "accountId",
    "userID",
    "userId",
    "anonymousId",
    "lastSessionId",
    "last_session_id",
    "sessionId",
    "session_id",
    "referral_code",
    "referral_link",
    "referral code",
    "referralCode",
    "displayName",
    "iterm2BackupPath",
    "githubRepoPaths",
    "oauthAccount",
    "oauthAccountId",
    "oauthAccountUuid",
    "oauth_account",
    "cachedAccountId",
    "cacheAccountId",
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

QUOTED_PRIVATE_PATH_RE = re.compile(
    r"""(?P<quote>["'])(?:/Users/)(?:\\.|(?! (?P=quote) )[^\r\n\\])*?(?P=quote)""",
    re.VERBOSE,
)
PRIVATE_PATH_RE = re.compile(r"/Users/[^\s\"'`,;)\]}]+")
ESCAPED_PRIVATE_PATH_RE = re.compile(r"\\/Users\\/(?:\\.|[^\"'\s,;)\]}])+")
UUID_RE = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[1-5][0-9a-fA-F]{3}-[89abAB][0-9a-fA-F]{3}-[0-9a-fA-F]{12}\b"
)


def _redact_json_string_key(text: str, key: str) -> str:
    json_string = r'"(?:\\.|[^"\\])*"'
    single_string = r"'(?:\\.|[^'\\])*'"
    pattern = re.compile(rf'("{re.escape(key)}"\s*:\s*){json_string}', re.IGNORECASE)
    text = pattern.sub(rf'\1"{REDACTED}"', text)
    pattern = re.compile(rf"('{re.escape(key)}'\s*:\s*){single_string}", re.IGNORECASE)
    return pattern.sub(rf"\1'{REDACTED}'", text)


def _redact_json_scalar_key(text: str, key: str) -> str:
    pattern = re.compile(
        rf'("{re.escape(key)}"\s*:\s*)(?:-?\d+(?:\.\d+)?|true|false|null)',
        re.IGNORECASE,
    )
    text = pattern.sub(rf'\1"{REDACTED}"', text)
    pattern = re.compile(
        rf"('{re.escape(key)}'\s*:\s*)(?:-?\d+(?:\.\d+)?|true|false|null)",
        re.IGNORECASE,
    )
    return pattern.sub(rf"\1'{REDACTED}'", text)


def _redact_plain_key(text: str, key: str) -> str:
    assign = re.compile(rf"\b({re.escape(key)}\s*=\s*)[^&\s;,]+", re.IGNORECASE)
    text = assign.sub(rf"\1{REDACTED}", text)
    colon = re.compile(rf"\b({re.escape(key)}\s*:\s*)[^,\n]+", re.IGNORECASE)
    return colon.sub(rf"\1{REDACTED}", text)


def _redact_private_paths(text: str) -> str:
    def quoted_repl(match: re.Match[str]) -> str:
        quote = match.group("quote")
        return f"{quote}{PATH_REDACTED}{quote}"

    text = QUOTED_PRIVATE_PATH_RE.sub(quoted_repl, text)
    text = ESCAPED_PRIVATE_PATH_RE.sub(PATH_REDACTED.replace("/", r"\/"), text)
    return PRIVATE_PATH_RE.sub(PATH_REDACTED, text)


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
        out = _redact_json_scalar_key(out, key)
        out = _redact_plain_key(out, key)

    out = _redact_private_paths(out)
    out = UUID_RE.sub(UUID_REDACTED, out)

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
        {"emailAddress":"person@example.com","organizationUuid":"11111111-1111-4111-8111-111111111111","accountUuid":"22222222-2222-4222-8222-222222222222","organizationName":"Private Org","displayName":"Private Name","userID":"user-private","anonymousId":"anon-private","lastSessionId":"33333333-3333-4333-8333-333333333333","referral_link":"https://example.invalid/ref?code=private","referral code":"PRIVATE-CODE","iterm2BackupPath":"/Users/alice/Library/Application Support/iTerm2","githubRepoPaths":["/Users/alice/src/private-repo"],"billingStatus":"active","subscriptionId":"sub-123","projects":{"/Users/alice/CTF/chall":{"lastSessionId":"44444444-4444-4444-8444-444444444444"}},"oauthCache":{"55555555-5555-4555-8555-555555555555":{"accountUuid":"66666666-6666-4666-8666-666666666666"}}}
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
        "11111111-1111-4111-8111-111111111111",
        "22222222-2222-4222-8222-222222222222",
        "Private Org",
        "Private Name",
        "user-private",
        "anon-private",
        "33333333-3333-4333-8333-333333333333",
        "https://example.invalid/ref",
        "PRIVATE-CODE",
        "/Users/",
        "private-repo",
        "44444444-4444-4444-8444-444444444444",
        "55555555-5555-4555-8555-555555555555",
        "66666666-6666-4666-8666-666666666666",
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
