#!/usr/bin/env python3
"""Scan repo-tracked files for accidentally committed secrets."""

from __future__ import annotations

import argparse
import json
from dataclasses import dataclass
from pathlib import Path
import re
import subprocess
import sys


ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Rule:
    name: str
    pattern: re.Pattern[str]


RULES = [
    Rule("openai_api_key_assignment", re.compile(r"\bOPENAI_API_KEY\s*=\s*\S{6,}", re.IGNORECASE)),
    Rule("anthropic_api_key_assignment", re.compile(r"\bANTHROPIC_API_KEY\s*=\s*\S{6,}", re.IGNORECASE)),
    Rule("claude_oauth_assignment", re.compile(r"\bCLAUDE_CODE_OAUTH_TOKEN\s*=\s*\S{6,}", re.IGNORECASE)),
    Rule("authorization_bearer", re.compile(r"\bAuthorization\s*:\s*Bearer\s+\S{6,}", re.IGNORECASE)),
    Rule("cookie_header", re.compile(r"\bCookie\s*:\s*\S.{5,}", re.IGNORECASE)),
    Rule("session_assignment", re.compile(r"\bsession=[^&\s;,]{6,}", re.IGNORECASE)),
    Rule("password_assignment", re.compile(r"\bpassword=[^&\s;,]{6,}", re.IGNORECASE)),
    Rule("token_assignment", re.compile(r"\btoken=[^&\s;,]{6,}", re.IGNORECASE)),
    Rule("api_key_assignment", re.compile(r"\bapi_key=[^&\s;,]{6,}", re.IGNORECASE)),
    Rule("secret_assignment", re.compile(r"\bsecret=[^&\s;,]{6,}", re.IGNORECASE)),
    Rule("github_pat", re.compile(r"github_pat_[A-Za-z0-9_]{20,}")),
    Rule("github_ghp", re.compile(r"ghp_[A-Za-z0-9_]{10,}")),
    Rule("slack_xoxb", re.compile(r"xoxb-[A-Za-z0-9-]{10,}")),
    Rule("anthropic_key", re.compile(r"sk-ant-[A-Za-z0-9_-]{8,}")),
    Rule("openai_style_key", re.compile(r"\bsk-[A-Za-z0-9_-]{16,}")),
    Rule("oauth_account", re.compile(r"\boauthAccount\b", re.IGNORECASE)),
    Rule("email_address_metadata", re.compile(r"\bemailAddress\b", re.IGNORECASE)),
    Rule("account_uuid_metadata", re.compile(r"\baccountUuid\b", re.IGNORECASE)),
    Rule("organization_uuid_metadata", re.compile(r"\borganizationUuid\b", re.IGNORECASE)),
    Rule("anonymous_id_metadata", re.compile(r"\banonymousId\b", re.IGNORECASE)),
    Rule("referral_link_metadata", re.compile(r"\breferral_link\b", re.IGNORECASE)),
    Rule("billing_type_metadata", re.compile(r"\bbillingType\b", re.IGNORECASE)),
    Rule("subscription_created_at_metadata", re.compile(r"\bsubscriptionCreatedAt\b", re.IGNORECASE)),
    Rule("private_key_block", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
]
PATH_RULES = [
    Rule(
        "browser_storage_state_file",
        re.compile(
            r"(^|/)(storage[-_]?state|storageState|cookies?|session[-_]?storage|browser[-_]?session)"
            r"\.(json|sqlite|db|txt)$",
            re.IGNORECASE,
        ),
    ),
    Rule("browser_auth_directory", re.compile(r"(^|/)\.auth/")),
]


ALLOWLIST_PATHS = {
    "scripts/redact_sensitive.py",
    "scripts/secret_scan.py",
    "tests/test_secret_scan.py",
}
ALLOWLIST_MARKER = "secret-scan: allow"
PLACEHOLDERS = {
    "<redacted>",
    "<redacted_private_key_block>",
    "<redacted_ctf_flag>",
    "<secret>",
    "<token>",
    "<cookie>",
    "<value>",
    "placeholder",
    "example",
    "dummy",
}


def _git_ls_files(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files failed")
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if line.strip():
            paths.append(root / line.strip())
    return paths


def _git_ls_untracked(root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--others", "--exclude-standard"],
        cwd=root,
        text=True,
        capture_output=True,
        timeout=30,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(result.stderr.strip() or "git ls-files --others failed")
    paths: list[Path] = []
    for line in result.stdout.splitlines():
        if line.strip():
            paths.append(root / line.strip())
    return paths


def _is_allowlisted(root: Path, path: Path, line: str) -> bool:
    rel = path.relative_to(root).as_posix()
    if rel in ALLOWLIST_PATHS:
        return True
    if ALLOWLIST_MARKER in line:
        return True
    return False


def _placeholder_only(match_text: str) -> bool:
    lowered = match_text.strip().strip('"').strip("'").lower()
    return any(value in lowered for value in PLACEHOLDERS)


def scan_paths(paths: list[Path], *, root: Path) -> list[dict[str, object]]:
    findings: list[dict[str, object]] = []
    for path in paths:
        if not path.is_file():
            continue
        rel = path.relative_to(root).as_posix()
        for rule in PATH_RULES:
            if rule.pattern.search(rel) and rel not in ALLOWLIST_PATHS:
                findings.append({"path": rel, "line": 1, "rule": rule.name})
        try:
            text = path.read_text(encoding="utf-8", errors="replace")
        except OSError:
            continue
        for line_number, line in enumerate(text.splitlines(), start=1):
            if _is_allowlisted(root, path, line):
                continue
            for rule in RULES:
                match = rule.pattern.search(line)
                if not match:
                    continue
                if _placeholder_only(match.group(0)):
                    continue
                findings.append(
                    {
                        "path": path.relative_to(root).as_posix(),
                        "line": line_number,
                        "rule": rule.name,
                    }
                )
    return findings


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", default=str(ROOT), help="repo root to scan")
    parser.add_argument("--strict", action="store_true", help="reserved for CI; findings are always fatal")
    parser.add_argument("--include-untracked", action="store_true", help="also scan git untracked files")
    parser.add_argument("--json", action="store_true")
    return parser


def main() -> int:
    args = build_parser().parse_args()
    root = Path(args.root).expanduser().resolve()
    try:
        paths = _git_ls_files(root)
        if args.include_untracked:
            paths.extend(_git_ls_untracked(root))
            paths = sorted(set(paths))
        findings = scan_paths(paths, root=root)
    except Exception as exc:
        result = {"ok": False, "error": str(exc), "findings": []}
        if args.json:
            print(json.dumps(result, ensure_ascii=False, indent=2, sort_keys=True))
        else:
            print(f"secret scan failed: {exc}", file=sys.stderr)
        return 2

    if args.json:
        print(json.dumps({"ok": not findings, "findings": findings}, ensure_ascii=False, indent=2, sort_keys=True))
    elif findings:
        for finding in findings:
            print(f"{finding['path']}:{finding['line']}: {finding['rule']}")
    else:
        print("OK: secret scan clean")
    return 1 if findings else 0


if __name__ == "__main__":
    raise SystemExit(main())
