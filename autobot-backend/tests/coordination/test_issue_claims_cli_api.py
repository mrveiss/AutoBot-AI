# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The issue-claims CLI's API transport: exit mapping, keyring credential, https-or-loopback (#18811)."""

from __future__ import annotations

import json

import httpx
import pytest

from autobot_shared.coordination import issue_claims, issue_claims_api
from tests.coordination._issue_claims_cli_harness import CREDENTIAL, store

HOLDER = {"agent_id": "alice/s1", "scope": "issue:7"}


@pytest.mark.parametrize(
    "response,code,field",
    [
        (httpx.Response(200, json={"held": True, "granted": True}), issue_claims.EXIT_OK, None),
        (httpx.Response(409, json={"detail": {"held": True, "granted": False, "holder": HOLDER}}), 1, None),
        (httpx.Response(400, json={"detail": "owner must not be empty"}), issue_claims.EXIT_USAGE, None),
        (httpx.Response(422, json={"detail": []}), issue_claims.EXIT_USAGE, None),
        (httpx.Response(401, json={"detail": "x"}), issue_claims.EXIT_UNREADABLE, "AuthRefused"),
        (httpx.Response(403, json={"detail": "x"}), issue_claims.EXIT_UNREADABLE, "AuthRefused"),
        (httpx.Response(500, text="boom"), issue_claims.EXIT_UNREADABLE, "HTTP500"),
        (httpx.Response(409, text="not json"), issue_claims.EXIT_UNREADABLE, "HTTP409"),
    ],
)
def test_status_maps_to_exit_code(cli, response, code, field):
    store(cli)
    cli.handler = lambda req: response
    got, body = issue_claims.run_claims_command(["claim", "7", "--owner", "s1"])
    assert got == code
    if field:
        assert body["error_class"] == field and body["granted"] is False
    if got == 1:
        assert body["holder"] == HOLDER


def test_connection_error_fails_closed(cli):
    store(cli)

    def boom(req):
        raise httpx.ConnectError("refused")

    cli.handler = boom
    code, body = issue_claims.run_claims_command(["who", "7"])
    assert code == issue_claims.EXIT_UNREADABLE and body["error_class"] == "ConnectError"


def test_each_subcommand_hits_its_endpoint(cli):
    store(cli)
    cli.handler = lambda req: httpx.Response(200, json={"held": False, "claims": []})
    for argv in (
        ["claim", "7", "--owner", "s1", "--ttl-s", "120"],
        ["release", "7", "--owner", "s1"],
        ["who", "7"],
        ["list"],
    ):
        assert issue_claims.run_claims_command(argv)[0] == 0
    assert [(r.method, r.url.path) for r in cli.seen] == [
        ("POST", "/api/coordination/issue-claims/7"),
        ("DELETE", "/api/coordination/issue-claims/7"),
        ("GET", "/api/coordination/issue-claims/7"),
        ("GET", "/api/coordination/issue-claims"),
    ]
    assert json.loads(cli.seen[0].content) == {"owner": "s1", "note": "", "ttl_s": 120}
    assert cli.seen[1].url.params["owner"] == "s1"


def test_the_credential_comes_from_the_keyring_in_its_own_header_and_is_never_printed(
    cli, capsys, caplog, no_file_writes
):
    store(cli)
    argv = ["who", "7"]
    assert issue_claims.main(argv) == 0
    sent = cli.seen[0].headers
    assert sent[issue_claims_api.CREDENTIAL_HEADER] == CREDENTIAL and "authorization" not in sent
    out = capsys.readouterr()
    assert CREDENTIAL not in " ".join(argv) + out.out + out.err + caplog.text
    assert not no_file_writes


def test_no_credential_in_the_keyring_says_run_login_first_and_exits_3(cli):
    code, body = issue_claims.run_claims_command(["claim", "7", "--owner", "s1"])
    assert code == issue_claims.EXIT_UNREADABLE == 3
    assert body["error"] == "not-logged-in" and "login" in body["message"] and "reboot" in body["message"]
    assert not cli.seen


def test_a_credential_for_another_backend_is_not_sent(cli, monkeypatch):
    store(cli, url="https://other.test")
    assert issue_claims.run_claims_command(["who", "7"])[1]["error"] == "not-logged-in"
    assert not cli.seen


@pytest.mark.parametrize(
    "url", ["http://claims.test:8443", "http://claims.example", "ftp://claims.test", "claims.test"]
)
def test_a_non_https_non_loopback_url_is_refused_before_the_keyring_is_read(cli, monkeypatch, url):
    store(cli)
    monkeypatch.setenv(issue_claims_api.API_URL_ENV, url)
    calls_before = len(cli.sys.calls)
    code, body = issue_claims.run_claims_command(["who", "7"])
    assert code == issue_claims.EXIT_UNREADABLE and body["error_class"] == "InsecureApiUrl"
    assert not cli.seen and len(cli.sys.calls) == calls_before


@pytest.mark.parametrize("url", ["http://127.0.0.1:8443", "http://127.8.9.10", "http://[::1]:8443", "http://localhost"])
def test_plain_http_to_a_loopback_host_is_allowed(cli, monkeypatch, url):
    monkeypatch.setenv(issue_claims_api.API_URL_ENV, url)
    store(cli, url=url)
    assert issue_claims.run_claims_command(["who", "7"])[0] == 0
    assert cli.seen[0].headers[issue_claims_api.CREDENTIAL_HEADER] == CREDENTIAL


@pytest.mark.parametrize(
    "url,normalised",
    [
        ("https://Claims.Test/", "https://claims.test:443"),
        ("https://claims.test:8443/base/", "https://claims.test:8443/base"),
        ("http://[::1]:9", "http://[::1]:9"),
    ],
)
def test_the_keyring_description_carries_the_normalised_url(url, normalised):
    assert issue_claims_api.keyring_description(url) == f"autobot:issue-claims:{normalised}"


def test_bad_request_is_refused_before_any_request(cli):
    store(cli)
    assert issue_claims.run_claims_command(["claim", "0", "--owner", "s1"])[0] == issue_claims.EXIT_USAGE
    assert not cli.seen


def test_metadata_address_url_is_refused_by_the_egress_policy(cli, monkeypatch):
    monkeypatch.setenv(issue_claims_api.API_URL_ENV, "https://169.254.169.254")
    store(cli, url="https://169.254.169.254")
    code, _ = issue_claims.run_claims_command(["who", "7"])
    assert code == issue_claims.EXIT_UNREADABLE and not cli.seen


def test_env_unset_uses_the_redis_path(monkeypatch):
    monkeypatch.delenv(issue_claims_api.API_URL_ENV, raising=False)
    called = []

    async def fake_dispatch(args):
        called.append(args.cmd)
        return 0, {"held": False}

    monkeypatch.setattr(issue_claims, "_dispatch", fake_dispatch)
    assert issue_claims.run_claims_command(["who", "7"]) == (0, {"held": False})
    assert called == ["who"]


def test_the_help_says_a_reboot_needs_a_new_login(capsys):
    with pytest.raises(SystemExit):
        issue_claims.main(["--help"])
    assert "reboot" in capsys.readouterr().out
