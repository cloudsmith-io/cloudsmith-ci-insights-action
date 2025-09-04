import json
from typing import Any, Dict

import pytest
from click.testing import CliRunner

import importlib
from package_insights.package_insights import package_insights  # click Command object

# Retrieve the real module object (the package's __init__ exports a symbol with same name)
package_insights_module = importlib.import_module("package_insights.package_insights")


class _MockResponse:
    def __init__(self, payload: Any, status_code: int = 200, headers: Dict[str, str] | None = None):
        self._payload = payload
        self.status_code = status_code
        self.headers = headers or {}
        # Provide a text attribute similar to requests.Response
        try:
            self.text = json.dumps(payload)
        except Exception:  # pragma: no cover - extremely unlikely for our test payloads
            self.text = str(payload)

    def json(self):  # noqa: D401 - simple helper
        return self._payload


def _build_package(display_name: str, version: str, quarantined: bool, status_reason: str = "No reason") -> Dict[str, Any]:
    return {
        "display_name": display_name,
        "version": version,
        "is_quarantined": quarantined,
        "status_str": "QUARANTINED" if quarantined else "BLOCKED",
        "status_reason": status_reason,
    }


@pytest.fixture
def runner():
    return CliRunner()


@pytest.fixture(autouse=True)
def set_cloudsmith_api_key(monkeypatch):
    monkeypatch.setenv("CLOUDSMITH_API_KEY", "dummy")


def test_cli_non_403_log_exits_gracefully(runner, monkeypatch):

    def fake_get(url, headers=None):  # pragma: no cover - shouldn't be called
        raise AssertionError("No HTTP calls expected for non-403 log")

    # Not strictly needed; no HTTP calls expected. Kept for consistency.
    monkeypatch.setattr(package_insights_module.requests, "get", fake_get)

    # No 403 => early informational return, exit code 0
    result = runner.invoke(package_insights, ["log with no forbidden status"])
    assert result.exit_code == 0
    assert "No 403 errors detected" in result.output


def test_cli_parse_error_exit_code_2(runner, monkeypatch):

    # Includes 403 and python but malformed so regex doesn't match
    log_text = "403 some python content but no package artifact filename"

    def fake_get(url, headers=None):  # pragma: no cover - shouldn't be reached due to parse failure
        raise AssertionError("Should not perform HTTP requests when parse fails")

    monkeypatch.setattr(package_insights_module.requests, "get", fake_get)
    result = runner.invoke(package_insights, [log_text])
    assert result.exit_code == 2
    assert "Unable to parse package details" in result.output


def test_cli_package_not_found_exit_code_5(runner, monkeypatch):

    # Valid artifact URL pattern
    log_text = "403 https://dl.cloudsmith.io/public/ns/repo/python/mypkg-1.0.0.tar.gz"

    def fake_get(url, headers=None):
        assert "packages/ns/repo/" in url
        # Return page with unrelated package so 'mypkg' isn't found
        payload = [_build_package("other", "9.9.9", False)]
        return _MockResponse(payload, headers={"x-pagination-pagetotal": "1"})

    monkeypatch.setattr(package_insights_module.requests, "get", fake_get)
    result = runner.invoke(package_insights, [log_text])
    assert result.exit_code == 5
    assert "Package not found: mypkg==1.0.0" in result.output


def test_cli_blocked_package_success(runner, monkeypatch):
    log_text = "403 https://dl.cloudsmith.io/public/acme/tools/python/samplepkg-2.1.0.whl"

    package_payload = [_build_package("samplepkg", "2.1.0", quarantined=False, status_reason=None)]

    def fake_get(url, headers=None):
        # First call: packages listing
        if "packages/acme/tools" in url:
            return _MockResponse(package_payload, headers={"x-pagination-pagetotal": "1"})
        # Policy listing invoked (action slug not found -> still queried)
        if "/workspaces/acme/policies/" in url and "/actions/" not in url:
            return _MockResponse({"results": []}, headers={"x-pagination-pagetotal": "1"})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(package_insights_module.requests, "get", fake_get)
    result = runner.invoke(package_insights, [log_text, "--follow-up", "Investigate policies"])
    assert result.exit_code == 0
    assert "Likely Blocked" in result.output
    assert "samplepkg==2.1.0" in result.output
    assert "Investigate policies" in result.output


def test_cli_quarantined_package_exit_code_1(runner, monkeypatch):
    log_text = "403 https://dl.cloudsmith.io/public/acme/tools/python/infectedpkg-3.0.0.tar.gz"

    # Action slug that will be extracted
    action_slug = "ACT123"
    status_reason = "Package quarantined by action slug_perm 'ACT123' due to policy evaluation"

    package_payload = [_build_package("infectedpkg", "3.0.0", quarantined=True, status_reason=status_reason)]

    policies = [
        {
            "slug_perm": "policy-1",
            "name": "Quarantine Policy",
            "description": "Blocks vulnerable packages",
        }
    ]
    actions = {"results": [{"slug_perm": action_slug, "effect": "QUARANTINE"}]}

    def fake_get(url, headers=None):
        if "packages/acme/tools" in url:
            return _MockResponse(package_payload, headers={"x-pagination-pagetotal": "1"})
        if url.startswith("https://api.cloudsmith.io/v2/workspaces/acme/policies/") and "/actions/" not in url:
            # policies listing
            return _MockResponse({"results": policies}, headers={"x-pagination-pagetotal": "1"})
        if url.startswith("https://api.cloudsmith.io/v2/workspaces/acme/policies/policy-1/actions/"):
            return _MockResponse(actions, headers={"x-pagination-pagetotal": "1"})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(package_insights_module.requests, "get", fake_get)
    result = runner.invoke(package_insights, [log_text])
    assert result.exit_code == 1
    assert "PACKAGE QUARANTINED" in result.output
    assert "Quarantine Policy" in result.output
    assert action_slug in result.output


def test_cli_quarantined_package_no_policy_match(runner, monkeypatch):
    """Quarantined package where action slug doesn't resolve to a policy action."""
    log_text = "403 https://dl.cloudsmith.io/public/acme/tools/python/quarpkg-9.9.tar.gz"
    status_reason = "Quarantined by slug_perm 'NO_MATCH'"
    package_payload = [_build_package("quarpkg", "9.9", quarantined=True, status_reason=status_reason)]

    def fake_get(url, headers=None):
        if "packages/acme/tools" in url:
            return _MockResponse(package_payload, headers={"x-pagination-pagetotal": "1"})
        if url.startswith("https://api.cloudsmith.io/v2/workspaces/acme/policies/") and "/actions/" not in url:
            return _MockResponse({"results": []}, headers={"x-pagination-pagetotal": "1"})
        raise AssertionError(f"Unexpected URL {url}")

    monkeypatch.setattr(package_insights_module.requests, "get", fake_get)
    result = runner.invoke(package_insights, [log_text])
    assert result.exit_code == 1
    assert "PACKAGE QUARANTINED" in result.output
    # No policy details section should appear
    assert "No associated policy found" in result.output
