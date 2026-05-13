from __future__ import annotations

import importlib.util

from conftest import REPO_ROOT


def _load_redactor():
    module_path = REPO_ROOT / "scripts" / "redact_sensitive.py"
    spec = importlib.util.spec_from_file_location("redact_sensitive", module_path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def test_claude_config_metadata_and_paths_are_redacted() -> None:
    redactor = _load_redactor()
    raw = """
    {
      "emailAddress": "dummy.user@example.invalid",
      "accountUuid": "11111111-1111-4111-8111-111111111111",
      "organizationUuid": "22222222-2222-4222-8222-222222222222",
      "displayName": "Dummy User",
      "organizationName": "Dummy Org",
      "userID": "user-dummy-private",
      "anonymousId": "anon-dummy-private",
      "lastSessionId": "33333333-3333-4333-8333-333333333333",
      "referral_link": "https://example.invalid/ref?code=dummy-private",
      "referral code": "DUMMY-PRIVATE-CODE",
      "iterm2BackupPath": "/Users/dummy/Library/Application Support/iTerm2",
      "githubRepoPaths": ["/Users/dummy/src/private-repo"],
      "projects": {
        "/Users/dummy/CTF/private-challenge": {
          "lastSessionId": "44444444-4444-4444-8444-444444444444",
          "usage": {
            "input_tokens": 1234,
            "total_cost_usd": 0.42
          }
        }
      },
      "oauthCache": {
        "55555555-5555-4555-8555-555555555555": {
          "accountUuid": "66666666-6666-4666-8666-666666666666"
        }
      }
    }
    """

    redacted = redactor.redact(raw)

    assert "emailAddress" in redacted
    assert "lastSessionId" in redacted
    assert "dummy.user@example.invalid" not in redacted
    assert "Dummy User" not in redacted
    assert "Dummy Org" not in redacted
    assert "user-dummy-private" not in redacted
    assert "anon-dummy-private" not in redacted
    assert "DUMMY-PRIVATE-CODE" not in redacted
    assert "https://example.invalid/ref" not in redacted
    assert "/Users/" not in redacted
    assert "private-repo" not in redacted
    assert "private-challenge" not in redacted
    assert "33333333-3333-4333-8333-333333333333" not in redacted
    assert "44444444-4444-4444-8444-444444444444" not in redacted
    assert "55555555-5555-4555-8555-555555555555" not in redacted
    assert "66666666-6666-4666-8666-666666666666" not in redacted
    assert "1234" in redacted
    assert "0.42" in redacted
    assert redactor.REDACTED in redacted
    assert redactor.PATH_REDACTED in redacted
    assert redactor.UUID_REDACTED in redacted
