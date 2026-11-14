# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The nightly Redis backup must send the client credential (#17932 review).

`roles/redis/templates/redis-stack.conf.j2` gives this role's own server a
`requirepass` directive whenever the role has a password, so an auth-enabled host is a
rendered configuration of this very role -- not a hypothetical. The backup script's
three `redis-cli` calls sent nothing: no password, no username, no environment
variable.

That is not a nit, because of how redis-cli answers a server error. Without `-e` it
PRINTS the error reply on stdout and exits 0, so `LASTSAVE` returned the literal string
`NOAUTH Authentication required.`; the wait loop then compared that string against
itself, and the run either spun to its five-minute timeout or archived a stale
`dump.rdb`. That is the same "logs a success line, produces no usable archive" failure
#17932 exists to end, arriving by a second route.

WHERE THE CREDENTIAL LIVES, AND WHY NOT IN THE SCRIPT. The script is deployed `0755`
and is re-rendered on the CODE-ONLY update path, where `redis_password` resolves from
`vault_redis_password` -- which no inventory in this repository defines. The
"DELIBERATELY EXCLUDED" ruling at the top of `roles/redis/tasks/code_only.yml` keeps
every artifact whose content depends on that variable off the update path for exactly
that reason: a code-only re-render emits it WITHOUT the credential and silently strips
authentication from the live data store. So the script carries only the credential
file's PATH, and `redis-backup.env.j2` -- `0600`, written on the provisioning path only
-- carries the value. `REDISCLI_AUTH` rather than `-a`, so it never reaches the process
list.

Split from `redis_backup_template_renders_runnable_17932_test.py` at the 600-line
ceiling (#5060); both guards drive the same harness, `repo_tests/_redis_backup_harness`.
"""

from __future__ import annotations

import re
import time
from pathlib import Path

import pytest
from repo_tests._redis_backup_harness import (
    _RUNNABLE,
    FIXTURE_PASSWORD,
    FIXTURE_USERNAME,
    MIN_RENDERED_LINES,
    TEMPLATE,
    _archives,
    _command_lines,
    _env_file,
    _run,
    render,
    render_env,
)


@pytest.fixture(scope="module")
def script() -> str:
    """The rendered script with persistence on -- the live fleet's configuration."""
    rendered = render(persistence=True)
    assert len(rendered.splitlines()) >= MIN_RENDERED_LINES, "render produced a stub, not the backup script"
    return rendered


def test_no_credential_is_substituted_into_the_backup_script() -> None:
    """The script is 0755 AND re-rendered by the updater, so it must carry no secret.

    Two rulings meet here and both forbid it. `roles/redis/tasks/code_only.yml` keeps
    every artifact whose content depends on `redis_password` off the update path,
    because a code-only re-render emits it WITHOUT the credential and silently strips
    authentication from the live store. And `mode: '0755'` in that same file means any
    local user could read a substituted value.

    Asserted against the TEMPLATE's SUBSTITUTIONS, not against its text: a render with
    the variables absent would pass by accident, which is the state the defect produces,
    while a text search would fire on the explanatory comments that name the variable in
    prose -- the exact over-broad reading this file keeps catching elsewhere.
    """
    source = TEMPLATE.read_text(encoding="utf-8")
    substitutions = re.findall(r"\{\{(.*?)\}\}", source, flags=re.S)
    assert substitutions, f"{TEMPLATE.name} substitutes nothing -- the sweep read the wrong file"
    for expression in substitutions:
        assert "password" not in expression.lower(), (
            f"{TEMPLATE.name} substitutes a credential: {{{{{expression}}}}}. The script is "
            "world-readable (0755) and is re-rendered on the code-only update path, so the "
            "value belongs in redis-backup.env.j2, which this script reads at run time (#17932)"
        )


def test_the_credential_file_carries_the_role_password() -> None:
    """The contrast: something must actually render the credential, or nothing sends it."""
    with_auth = render_env(password=FIXTURE_PASSWORD, username=FIXTURE_USERNAME)
    assert f"REDISCLI_AUTH={FIXTURE_PASSWORD}" in with_auth
    assert f"REDIS_USERNAME={FIXTURE_USERNAME}" in with_auth
    nopass = render_env()
    assert "REDISCLI_AUTH=\n" in nopass, "a nopass host must get an EMPTY value, not a missing line"
    assert FIXTURE_PASSWORD not in nopass


def _redis_cli_call_lines(script: str) -> list[str]:
    """Executable lines invoking `redis-cli`, read as LOGICAL lines, not physical ones.

    `_command_lines` splits on newlines, so a call continued across lines --
    `redis-cli\\` then its arguments -- produces no line containing `redis-cli `, and the
    detector walks straight past it. The remaining calls still clear the count floor, so
    the sweep reports a number and the miss is invisible: the guard would be measuring
    the lines it can see rather than the calls that run.

    Backslash-newline is joined first, which is what the shell itself does before
    executing. Latent today -- no call in the template is continued -- and fixed anyway,
    because the cost of the guard being wrong here is an unauthenticated call shipping
    unnoticed, which is the whole defect (#17932).
    """
    joined = re.sub(r"\\\r?\n[ \t]*", " ", script)
    return [line for line in _command_lines(joined) if "redis-cli " in line]


def test_no_redis_cli_call_is_bare(script: str) -> None:
    """Every call must carry the shared argument array, or one of them skips auth.

    The defect was three unauthenticated calls, so "the script authenticates" is only
    true if it is true of ALL of them. Counted over executable lines, because the
    explanatory comments above name `redis-cli` too.
    """
    calls = _redis_cli_call_lines(script)
    assert len(calls) >= 2, f"the sweep found {len(calls)} redis-cli calls -- it stopped reading the script"
    bare = [line for line in calls if '"${REDIS_CLI_ARGS[@]}"' not in line]
    assert not bare, f"these redis-cli calls do not carry the client arguments: {bare}"


def test_the_credential_is_never_put_on_a_command_line(script: str) -> None:
    """`-a`/`--pass` would publish the password to every local user via the process list."""
    # The ARGUMENT ASSEMBLY lines count too, not only the call sites: a flag added to
    # `REDIS_CLI_ARGS` reaches every call while appearing on no line that says
    # `redis-cli`. A detector keyed on the call sites alone misses the easiest way in.
    joined = re.sub(r"\\\r?\n[ \t]*", " ", script)
    calls = [line for line in _command_lines(joined) if "redis-cli " in line or "REDIS_CLI_ARGS" in line]
    assert calls, "no redis-cli call was found -- the sweep read nothing"
    for line in calls:
        for flag in (" -a ", " --pass ", " --askpass"):
            assert flag not in line, (
                f"{flag.strip()!r} puts the credential on the process list, where any local user "
                f"can read it; use REDISCLI_AUTH from the environment: {line}"
            )


@_RUNNABLE
def test_an_auth_enabled_host_sends_the_credential(tmp_path: Path) -> None:
    """The end-to-end property: with a credential file present, every call authenticates."""
    env_file = _env_file(tmp_path, password=FIXTURE_PASSWORD, username=FIXTURE_USERNAME)
    rc, log, backup_dir = _run(tmp_path, aof="appendonlydir", env_file=env_file)
    assert rc == 0, f"the backup exited {rc}:\n{log}"
    assert len(_archives(backup_dir)) == 1, log

    argv = (tmp_path / "bin" / "argv.log").read_text(encoding="utf-8").splitlines()
    auth = (tmp_path / "bin" / "auth.log").read_text(encoding="utf-8").splitlines()
    assert len(argv) >= 3, f"fewer calls than the script makes were recorded: {argv}"
    assert all(f"--user {FIXTURE_USERNAME}" in line for line in argv), f"a call sent no username: {argv}"
    assert all(line == FIXTURE_PASSWORD for line in auth), f"a call ran without REDISCLI_AUTH: {auth}"
    assert not any(FIXTURE_PASSWORD in line for line in argv), f"the credential reached the argv: {argv}"


@_RUNNABLE
def test_a_nopass_host_sends_no_empty_auth(tmp_path: Path) -> None:
    """The contrast. A blank-but-SET REDISCLI_AUTH makes redis-cli send an empty AUTH,
    which a nopass server rejects -- so "always export it" would break the majority case.
    """
    env_file = _env_file(tmp_path, password="", username="")
    rc, log, _ = _run(tmp_path, aof="appendonlydir", env_file=env_file)
    assert rc == 0, log
    auth = (tmp_path / "bin" / "auth.log").read_text(encoding="utf-8").splitlines()
    assert auth and all(line == "<unset>" for line in auth), f"REDISCLI_AUTH was exported blank: {auth}"
    argv = (tmp_path / "bin" / "argv.log").read_text(encoding="utf-8").splitlines()
    assert not any("--user" in line for line in argv), f"an empty username was sent as --user: {argv}"


@_RUNNABLE
def test_an_error_reply_is_not_mistaken_for_a_timestamp(tmp_path: Path) -> None:
    """The reported defect, reproduced: LASTSAVE answering with a server error string.

    Without the shape check the two identical error strings compare EQUAL, so the loop
    runs to `BGSAVE_TIMEOUT_SECONDS` and the run either sleeps for five minutes or
    archives a stale dump.rdb. The run must instead end at once, loudly, with no archive.
    """
    started = time.time()
    rc, log, backup_dir = _run(tmp_path, aof="appendonlydir", lastsave="noauth")
    elapsed = time.time() - started

    assert rc != 0, f"an unauthenticated backup exited 0:\n{log}"
    assert elapsed < 30, f"the run spun in the wait loop for {elapsed:.0f}s instead of failing at once"
    assert _archives(backup_dir) == [], "an archive was produced from an unauthenticated run"
    assert "NOAUTH" in log, f"the log does not name the reply it refused:\n{log}"
    # The discriminator between the fix and the defect, and the reason "it exited
    # non-zero" is not enough on its own: WITHOUT the shape check the run also ends
    # non-zero -- by exhausting the wait loop, five minutes later on the real default,
    # having compared an error string against itself. It must never reach the loop.
    assert (
        "Waiting for BGSAVE" not in log
    ), f"the run entered the wait loop on an error reply instead of refusing it:\n{log}"
    assert "did not return a timestamp" in log, f"the refusal did not name what was wrong:\n{log}"
    assert "FAILED" in log.splitlines()[-1], f"the final log line does not report the failure:\n{log}"
    assert "Redis Stack backup complete" not in log, "an unauthenticated run logged the completion line"


@pytest.mark.parametrize(
    ("command", "expect_bare"),
    [
        ("redis-cli PING\n", True),
        ('redis-cli "${REDIS_CLI_ARGS[@]}" PING\n', False),
        ("redis-cli\\\n    PING\n", True),
        ('redis-cli\\\n    "${REDIS_CLI_ARGS[@]}" PING\n', False),
    ],
    ids=["bare", "authenticated", "bare-continued", "authenticated-continued"],
)
def test_the_bare_call_detector_sees_a_continued_call(command: str, expect_bare: bool) -> None:
    """The contrast pair the guard above needs, including the continued forms.

    Without the two `-continued` cases this detector cannot be shown to catch anything a
    line-oriented one would miss -- and the line-oriented version it replaces passed the
    real template happily while being blind to exactly that shape. A guard whose
    discriminating case is untested is a guard with an unmeasured blind spot.
    """
    calls = _redis_cli_call_lines(command)
    assert calls, "the detector found no redis-cli call at all -- it is not reading the input"
    bare = [line for line in calls if '"${REDIS_CLI_ARGS[@]}"' not in line]
    assert bool(bare) is expect_bare
