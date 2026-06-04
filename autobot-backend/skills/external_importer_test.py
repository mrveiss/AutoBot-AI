# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss
"""Tests for SSRF guards in ExternalSkillImporter (MVA-1307)."""

import pytest

from skills.external_importer import _parse_git_remote, _validate_git_ref, _validate_git_url

# ---------------------------------------------------------------------------
# _parse_git_remote — pure URL parsing, no network
# ---------------------------------------------------------------------------


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://github.com/user/repo", ("https", "github.com")),
        ("ssh://github.com/user/repo", ("ssh", "github.com")),
        ("git+ssh://github.com/user/repo", ("git+ssh", "github.com")),
        ("git@github.com:user/repo.git", ("ssh", "github.com")),
        ("user@bitbucket.org:team/repo.git", ("ssh", "bitbucket.org")),
    ],
)
def test_parse_git_remote_allowed(url, expected):
    assert _parse_git_remote(url) == expected


@pytest.mark.parametrize(
    "url",
    [
        "file:///etc/passwd",
        "file://localhost/etc/shadow",
        "http://169.254.169.254/latest/meta-data/",
        "http://10.0.0.1/internal",
        "git://github.com/user/repo",
    ],
)
def test_parse_git_remote_blocked_scheme(url):
    with pytest.raises(ValueError, match="Disallowed git URL scheme"):
        _parse_git_remote(url)


# ---------------------------------------------------------------------------
# _validate_git_ref — pure validation, no network
# ---------------------------------------------------------------------------


@pytest.mark.parametrize("ref", ["main", "v1.2.3", "feature/my-branch", "abc123def", "release-2026"])
def test_validate_git_ref_allowed(ref):
    _validate_git_ref(ref)  # must not raise


@pytest.mark.parametrize(
    "ref",
    [
        "--upload-pack=evil",
        "-v",
        "",
        "../../../etc/passwd",
        "ref\x00null",
        "ref with spaces",
    ],
)
def test_validate_git_ref_blocked(ref):
    with pytest.raises(RuntimeError, match="Invalid git ref"):
        _validate_git_ref(ref)


# ---------------------------------------------------------------------------
# _validate_git_url — async, mocked network
# ---------------------------------------------------------------------------


@pytest.fixture
def anyio_backend():
    return "asyncio"


@pytest.mark.anyio
async def test_validate_git_url_https_public(monkeypatch):
    """Public HTTPS git URLs must pass the SSRF guard."""
    import autobot_shared.url_safety as _us

    monkeypatch.setattr(_us, "is_public_url", lambda url: True)
    # No exception expected
    await _validate_git_url("https://github.com/user/repo")


@pytest.mark.anyio
async def test_validate_git_url_https_private_blocked(monkeypatch):
    """HTTPS URLs resolving to private IPs must be blocked."""
    import autobot_shared.url_safety as _us

    monkeypatch.setattr(_us, "is_public_url", lambda url: False)
    with pytest.raises(RuntimeError, match="SSRF guard"):
        await _validate_git_url("https://internal.corp/secret/repo")


@pytest.mark.anyio
async def test_validate_git_url_file_blocked():
    """file:// git URLs must always be blocked (scheme allowlist)."""
    with pytest.raises(RuntimeError, match="Git URL rejected"):
        await _validate_git_url("file:///etc/passwd")


@pytest.mark.anyio
async def test_validate_git_url_http_blocked():
    """Plain http:// git URLs must always be blocked (scheme allowlist)."""
    with pytest.raises(RuntimeError, match="Git URL rejected"):
        await _validate_git_url("http://169.254.169.254/latest/meta-data/")


@pytest.mark.anyio
async def test_validate_git_url_ssh_private_blocked(monkeypatch):
    """SSH URLs resolving to private/internal IPs must be blocked."""
    import autobot_shared.url_safety as _us

    async def _bad_resolve(host, *, timeout=2.0):
        raise ValueError(f"Host '{host}' resolves to a non-public address: 10.0.0.1")

    monkeypatch.setattr(_us, "resolve_safe_ip_async", _bad_resolve)
    with pytest.raises(RuntimeError, match="SSRF guard"):
        await _validate_git_url("git@internal-host.corp:repo.git")


@pytest.mark.anyio
async def test_validate_git_url_scp_public(monkeypatch):
    """SCP-style git@host:path URLs for public hosts must pass."""
    import autobot_shared.url_safety as _us

    async def _good_resolve(host, *, timeout=2.0):
        return "140.82.121.4"

    monkeypatch.setattr(_us, "resolve_safe_ip_async", _good_resolve)
    await _validate_git_url("git@github.com:user/repo.git")  # must not raise
