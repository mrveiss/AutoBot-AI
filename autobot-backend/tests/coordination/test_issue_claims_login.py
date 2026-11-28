# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``issue_claims login`` / ``logout`` (#18811): getpass in, kernel keyring out, nothing on disk."""

from __future__ import annotations

import getpass
import inspect
import json

import httpx
import pytest

from autobot_shared.coordination import issue_claims, issue_claims_api, issue_claims_login
from tests.coordination._issue_claims_cli_harness import CREDENTIAL, URL, store

PASSWORD = "pw-SECRET-do-not-echo"  # pragma: allowlist secret -- a test fixture, not a credential
JWT = "jwt-SECRET-login-token"


def _backend(minted_status: int = 201, login_status: int = 200):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.url.path == issue_claims_login.LOGIN_PATH:
            return httpx.Response(login_status, json={"success": login_status == 200, "token": JWT})
        body = {"credential": CREDENTIAL, "secret_id": CREDENTIAL.partition(".")[0], "username": "alice"}
        return httpx.Response(minted_status, json=body)

    return handler


@pytest.fixture
def prompts(monkeypatch):
    """Answer getpass: the username, then the password; records each prompt text."""
    asked: list[str] = []
    answers = iter(["alice", PASSWORD])

    def _getpass(prompt: str = "Password: ", stream=None) -> str:
        asked.append(prompt)
        return next(answers)

    monkeypatch.setattr(getpass, "getpass", _getpass)
    monkeypatch.setattr(issue_claims_login, "run_login", _bound_to(issue_claims_login.run_login, _getpass))
    return asked


def _bound_to(run_login, prompt):
    async def _run():
        return await run_login(prompt)

    return _run


def test_login_prompts_with_getpass_by_default():
    assert inspect.signature(issue_claims_login.run_login).parameters["prompt"].default is getpass.getpass


def test_login_signs_in_mints_and_keeps_the_credential_in_the_user_keyring_only(
    cli, prompts, capsys, caplog, no_file_writes
):
    cli.handler = _backend()
    assert issue_claims.main(["login"]) == 0
    login, minted = cli.seen
    assert json.loads(login.content) == {"username": "alice", "password": PASSWORD}
    assert minted.url.path == issue_claims_api.CREDENTIALS_PATH and minted.headers["authorization"] == f"Bearer {JWT}"
    assert cli.sys.keys[issue_claims_api.keyring_description(URL).encode()][1] == CREDENTIAL.encode()
    out = capsys.readouterr()
    for value in (PASSWORD, JWT, CREDENTIAL.partition(".")[2]):
        assert value not in out.out + out.err + caplog.text
    assert json.loads(out.out)["logged_in"] is True and prompts == ["AutoBot username: ", "AutoBot password: "]
    assert not no_file_writes


@pytest.mark.parametrize("login_status,minted_status", [(401, 201), (200, 403)])
def test_a_refused_login_or_mint_stores_nothing_and_exits_3(cli, prompts, login_status, minted_status):
    cli.handler = _backend(minted_status, login_status)
    code, body = issue_claims.run_claims_command(["login"])
    assert code == 3 and body["error"] == "login-refused" and not cli.sys.keys


def test_login_over_plain_http_to_a_remote_host_sends_nothing(cli, prompts, monkeypatch):
    monkeypatch.setenv(issue_claims_api.API_URL_ENV, "http://claims.example")
    code, body = issue_claims.run_claims_command(["login"])
    assert code == 3 and body["error_class"] == "InsecureApiUrl" and not cli.seen and not cli.sys.keys


def test_logout_revokes_in_the_secrets_manager_then_removes_the_key(cli, no_file_writes):
    store(cli)
    cli.handler = lambda req: httpx.Response(200, json={"revoked": True, "secret_id": "x"})
    assert issue_claims.run_claims_command(["logout"]) == (0, {"logged_out": True, "revoked": True})
    (revoke,) = cli.seen
    assert (revoke.method, revoke.url.path) == ("DELETE", issue_claims_api.CREDENTIALS_PATH)
    assert revoke.headers[issue_claims_api.CREDENTIAL_HEADER] == CREDENTIAL and not cli.sys.keys
    assert not no_file_writes


def test_logout_of_an_already_revoked_credential_still_removes_the_key(cli):
    store(cli)
    cli.handler = lambda req: httpx.Response(401, json={"detail": "x"})
    assert issue_claims.run_claims_command(["logout"]) == (0, {"logged_out": True, "revoked": False})
    assert not cli.sys.keys


def test_a_failed_revoke_keeps_the_key_so_it_can_be_retried(cli):
    store(cli)
    cli.handler = lambda req: httpx.Response(503, text="down")
    code, body = issue_claims.run_claims_command(["logout"])
    assert code == 3 and body["error"] == "revoke-failed" and cli.sys.keys


def test_logout_with_nothing_stored_is_a_clean_no_op(cli):
    code, body = issue_claims.run_claims_command(["logout"])
    assert code == 0 and body["revoked"] is False and not cli.seen


def test_the_write_trap_catches_a_write(tmp_path, no_file_writes):
    """The trap the no-file-write assertions rely on does fire."""
    with pytest.raises(AssertionError):
        open(tmp_path / "x", "w", encoding="utf-8")  # noqa: SIM115
    assert no_file_writes == [tmp_path / "x"]
