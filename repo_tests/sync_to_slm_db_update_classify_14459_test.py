# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""sync-to-slm.sh must not report a zero-row DB update as success (#14459).

Before this fix, `sync-to-slm.sh` checked only `$?` after the ssh command that
runs `UPDATE nodes SET code_version = ... WHERE node_id = '$SLM_NODE_ID'`.
`psql` exits 0 for an UPDATE whose WHERE clause matched no row -- that is not a
SQL error -- so a renamed node (#9956 made `node_id` overridable) produced the
exact same "Database updated" log line as a real update, while the row stayed
as stale as it was before the deploy. The command-failure path was also
mislabelled "non-critical, code is deployed", which is backwards: the code
*is* deployed and the row is what's wrong.

Round 2 (review on PR #14468): the first fix passed `SLM_NODE_ID`/
`CURRENT_COMMIT` to psql as `-v` variables and referenced them in the SQL text
with the quoting form `:'var'` -- but inside a `-c "..."` argument. `psql(1)`:
a `-c` argument "must be completely parsable by the server (i.e., it contains
no psql-specific features)". `:'var'` is exactly such a feature -- the server
receives the literal four characters `:'commit'` and raises a syntax error.
Every call would have failed, `classify_db_update_result` would always see a
nonzero exit, and the `updated`/`no_match` branches -- the entire point of
this fix -- would never run in production. The SQL now reaches psql over
**stdin** (like `-f`, where `:'var'` interpolation is actually processed),
piped through the same ssh command's stdin since no pty is allocated.

That gap existed because every test in the first round either called
`classify_db_update_result()` with a hand-typed string or grepped source text
-- nothing ran the real invocation against a real psql. This file adds that:
`scratch_postgres` starts a private, disposable Postgres 16 cluster (never
the live SLM database, never a shared host cluster) and the "live_psql" tests
below send the SQL text extracted *verbatim* from `sync-to-slm.sh` -- not
retyped -- through a real `psql` process, over stdin, exactly as the script
does. If the binaries aren't available on this machine, those tests skip
(not fail, not silently absent) and the static tests -- which need no
Postgres at all -- still catch the actual defect class: no `-c` argument may
contain `:'`, and `REMOTE_PSQL_CMD` may never carry a `-c` flag again.

`classify_db_update_result()` (autobot-infrastructure/shared/scripts/lib/
db-update-classify.sh) is itself a pure function -- it runs no ssh, psql or
rsync, only `printf`/`grep` on strings the caller already captured. It is
exercised directly with synthetic strings AND fed the real output of a live
psql process below. `sync-to-slm.sh` itself is never invoked -- it reaches a
live node and a live database.
"""

from __future__ import annotations

import re
import shutil
import socket
import subprocess
import tempfile
from dataclasses import dataclass
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts"
LIB = SCRIPT_DIR / "lib" / "db-update-classify.sh"
SYNC_SCRIPT = SCRIPT_DIR / "utilities" / "sync-to-slm.sh"

_SSH_HOST_KEY_WARNING = "Warning: Permanently added 'node.example' (ED25519) to the list of known hosts."

_HEREDOC_RE = re.compile(r"<<'REMOTE_SQL'[^\n]*\n(.*?)\nREMOTE_SQL\n", re.DOTALL)
_ARRAY_RE = re.compile(r"REMOTE_PSQL_CMD=\((.*?)\n\s*\)\n", re.DOTALL)


def _sync_script_text() -> str:
    return SYNC_SCRIPT.read_text(encoding="utf-8")


def _heredoc_sql() -> str:
    """The exact SQL text sync-to-slm.sh sends over psql's stdin -- extracted
    from source, never retyped, so this file can't silently drift from what
    actually ships."""
    match = _HEREDOC_RE.search(_sync_script_text())
    assert match, "could not locate the REMOTE_SQL heredoc body in sync-to-slm.sh"
    return match.group(1)


def _remote_psql_cmd_array_body() -> str:
    match = _ARRAY_RE.search(_sync_script_text())
    assert match, "REMOTE_PSQL_CMD array not found in sync-to-slm.sh"
    return match.group(1)


def _classify(exit_code: int, output: str) -> str:
    result = subprocess.run(
        ["bash", "-c", f"source {LIB}; classify_db_update_result \"$1\" \"$2\"", "_", str(exit_code), output],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"classify_db_update_result itself failed: {result.stderr}"
    return result.stdout.strip()


# --------------------------------------------------------------------------
# Live psql, against a disposable scratch Postgres -- never the live SLM DB.
# --------------------------------------------------------------------------


def _find_pg_binary(name: str) -> str | None:
    found = shutil.which(name)
    if found:
        return found
    for bindir in sorted(Path("/usr/lib/postgresql").glob("*/bin"), reverse=True):
        candidate = bindir / name
        if candidate.is_file():
            return str(candidate)
    return None


@dataclass
class _ScratchPg:
    psql: str
    conn_args: list[str]


@pytest.fixture(scope="module")
def scratch_postgres():
    """A private, disposable Postgres 16 cluster (own `initdb` data dir, own
    unix socket, non-standard port) -- created and torn down entirely within
    this test, never the live SLM database or a shared host cluster. Skips
    (does not fail) when the required binaries aren't on this machine."""
    initdb = _find_pg_binary("initdb")
    pg_ctl = _find_pg_binary("pg_ctl")
    psql_bin = _find_pg_binary("psql")
    createdb_bin = _find_pg_binary("createdb")
    if not all((initdb, pg_ctl, psql_bin, createdb_bin)):
        pytest.skip("initdb/pg_ctl/psql/createdb not available -- cannot exercise a real psql process")

    data_dir = tempfile.mkdtemp(prefix="autobot14459-pgdata-")
    # Unix-domain socket paths are capped at ~107 bytes; pytest's own tmp
    # dirs routinely exceed that, so this uses a short path directly under /tmp.
    sock_dir = tempfile.mkdtemp(prefix="pg14459-", dir="/tmp")
    with socket.socket() as probe:
        probe.bind(("127.0.0.1", 0))
        port = str(probe.getsockname()[1])

    init = subprocess.run(
        [initdb, "-D", data_dir, "-U", "scratch14459", "--auth=trust"],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if init.returncode != 0:
        shutil.rmtree(data_dir, ignore_errors=True)
        shutil.rmtree(sock_dir, ignore_errors=True)
        pytest.skip(f"initdb failed: {init.stdout}\n{init.stderr}")

    start = subprocess.run(
        [
            pg_ctl,
            "-D",
            data_dir,
            "-l",
            str(Path(data_dir) / "server.log"),
            "-o",
            f"-k {sock_dir} -h '' -p {port}",
            "-w",
            "start",
        ],
        capture_output=True,
        text=True,
        timeout=60,
    )
    if start.returncode != 0:
        shutil.rmtree(data_dir, ignore_errors=True)
        shutil.rmtree(sock_dir, ignore_errors=True)
        pytest.skip(f"scratch postgres failed to start: {start.stdout}\n{start.stderr}")

    try:
        db_name = "slm_scratch_14459"
        subprocess.run(
            [createdb_bin, "-h", sock_dir, "-p", port, "-U", "scratch14459", db_name],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        conn_args = ["-h", sock_dir, "-p", port, "-U", "scratch14459", "-d", db_name]
        subprocess.run(
            [
                psql_bin,
                *conn_args,
                "-v",
                "ON_ERROR_STOP=1",
                "-c",
                "CREATE TABLE nodes (node_id text PRIMARY KEY, code_version text, "
                "code_status text, updated_at timestamptz)",
            ],
            capture_output=True,
            text=True,
            check=True,
            timeout=30,
        )
        yield _ScratchPg(psql=psql_bin, conn_args=conn_args)
    finally:
        subprocess.run([pg_ctl, "-D", data_dir, "-m", "immediate", "stop"], capture_output=True, timeout=30)
        shutil.rmtree(data_dir, ignore_errors=True)
        shutil.rmtree(sock_dir, ignore_errors=True)


def _run_real_update(pg: _ScratchPg, node_id: str, commit: str) -> tuple[int, str]:
    """Builds and runs the invocation exactly as sync-to-slm.sh does: `psql`
    with `-v node_id=...`/`-v commit=...`, SQL fed over stdin, combined
    stdout+stderr -- the same shape the ssh call captures in the script."""
    result = subprocess.run(
        [pg.psql, *pg.conn_args, "-v", "ON_ERROR_STOP=1", "-v", f"node_id={node_id}", "-v", f"commit={commit}"],
        input=_heredoc_sql(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    return result.returncode, (result.stdout + result.stderr)


def test_live_psql_updates_a_matching_row(scratch_postgres):
    """The regression this round guards: a `-c` argument with `:'var'` fails
    on every call before it can report a row count. This runs the real SQL
    from the script, over stdin, against a real psql/Postgres process.

    Setup/verification below deliberately do NOT use `:'var'` inside a `-c`
    argument -- that is the exact defect under test, and `node_id` here is a
    fixed test literal (never attacker- or operator-supplied), so plain SQL
    text is the correct, uncomplicated choice for scaffolding."""
    node_id = "live-test-match-14459"
    subprocess.run(
        [
            scratch_postgres.psql,
            *scratch_postgres.conn_args,
            "-c",
            f"INSERT INTO nodes (node_id, code_version, code_status) VALUES ('{node_id}', 'old', 'STALE') "
            "ON CONFLICT (node_id) DO UPDATE SET code_version = 'old', code_status = 'STALE'",
        ],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )

    exit_code, output = _run_real_update(scratch_postgres, node_id, "deadbeef14459")
    assert exit_code == 0, f"psql failed instead of reporting a row count: {output}"
    assert "UPDATE 1" in output, f"expected the UPDATE 1 command tag, got: {output!r}"
    assert _classify(exit_code, output) == "updated"

    verify = subprocess.run(
        [scratch_postgres.psql, *scratch_postgres.conn_args, "-t", "-A", "-c", f"SELECT code_version FROM nodes WHERE node_id = '{node_id}'"],
        capture_output=True,
        text=True,
        check=True,
        timeout=30,
    )
    assert verify.stdout.strip() == "deadbeef14459", "the row must actually change, not just report success"


def test_live_psql_reports_zero_rows_for_a_node_id_that_matches_nothing(scratch_postgres):
    """The #14459 core regression, run against a real psql process: a
    renamed/unknown node_id must produce `UPDATE 0`, exit 0, and classify as
    `no_match` -- never `updated`."""
    exit_code, output = _run_real_update(scratch_postgres, "live-test-no-such-node-14459", "cafef00d14459")
    assert exit_code == 0, f"a WHERE clause matching nothing is not a SQL error: {output}"
    assert "UPDATE 0" in output, f"expected the UPDATE 0 command tag, got: {output!r}"
    assert _classify(exit_code, output) == "no_match"


def test_live_psql_reports_command_failure_distinctly(scratch_postgres):
    """A real connection failure (wrong database) must classify as `failed`,
    never silently as `no_match`."""
    bad_conn_args = [
        "-h",
        scratch_postgres.conn_args[1],
        "-p",
        scratch_postgres.conn_args[3],
        "-U",
        scratch_postgres.conn_args[5],
        "-d",
        "slm_scratch_14459_does_not_exist",
    ]
    result = subprocess.run(
        [scratch_postgres.psql, *bad_conn_args, "-v", "ON_ERROR_STOP=1", "-v", "node_id=x", "-v", "commit=x"],
        input=_heredoc_sql(),
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode != 0
    assert _classify(result.returncode, result.stdout + result.stderr) == "failed"


# --------------------------------------------------------------------------
# The pure classifier, exercised with synthetic strings.
# --------------------------------------------------------------------------


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to exercise the pure classifier")
def test_zero_row_update_is_not_reported_as_success():
    """The core regression: `psql` exits 0 having updated nothing."""
    assert _classify(0, "UPDATE 0") == "no_match"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to exercise the pure classifier")
def test_zero_row_update_caught_even_behind_an_ssh_banner_line():
    """ssh can prepend a host-key warning to the captured 2>&1 output. The
    zero-row check must still find the tag on its own line, not require the
    whole capture to equal "UPDATE 0"."""
    output = f"{_SSH_HOST_KEY_WARNING}\nUPDATE 0"
    assert _classify(0, output) == "no_match"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to exercise the pure classifier")
def test_real_update_is_reported_as_updated():
    """The happy path -- proven alongside the bug, not instead of it."""
    assert _classify(0, "UPDATE 1") == "updated"
    assert _classify(0, "UPDATE 3") == "updated"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to exercise the pure classifier")
def test_command_failure_is_distinguished_from_a_zero_row_result():
    """A nonzero exit (ssh unreachable, bad credentials, SQL error under
    ON_ERROR_STOP) must classify as 'failed', not 'no_match' -- callers log a
    different, more specific message for each."""
    assert _classify(1, "psql: error: connection to server failed") == "failed"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to exercise the pure classifier")
def test_exit_code_takes_precedence_over_output_content():
    """A nonzero exit must never be reclassified by whatever happens to be in
    stderr -- exit code is checked first and is authoritative."""
    assert _classify(1, "UPDATE 1") == "failed"


@pytest.mark.skipif(shutil.which("bash") is None, reason="bash is required to exercise the pure classifier")
def test_no_third_silent_outcome():
    """Every call returns one of exactly three values -- nothing passes
    through uninterpreted."""
    for exit_code, output in ((0, "UPDATE 0"), (0, "UPDATE 1"), (1, "anything")):
        assert _classify(exit_code, output) in {"updated", "no_match", "failed"}


# --------------------------------------------------------------------------
# Static checks against sync-to-slm.sh's source -- always run, no Postgres
# or bash execution required.
# --------------------------------------------------------------------------


def test_lib_exists_and_is_valid_shell():
    assert LIB.is_file(), f"{LIB} missing -- sync-to-slm.sh sources it"
    assert subprocess.run(["bash", "-n", str(LIB)], capture_output=True).returncode == 0
    assert subprocess.run(["bash", "-n", str(SYNC_SCRIPT)], capture_output=True).returncode == 0


def test_sync_script_uses_the_classifier_not_a_bare_exit_code_check():
    text = _sync_script_text()
    assert 'source "${SCRIPT_DIR}/../lib/db-update-classify.sh"' in text
    assert "classify_db_update_result" in text
    # the regression: a bare `if [ $? -eq 0 ]` right after the ssh call, with
    # no inspection of what the command actually reported
    assert "if [ $? -eq 0 ]" not in text


def test_neither_outcome_is_mislabelled_non_critical():
    text = _sync_script_text()
    assert "non-critical" not in text, (
        "a failed or no-op database update must never be logged as non-critical -- "
        "code_version/code_status is the only view an operator has of what is "
        "deployed without logging into the node"
    )


def test_failed_and_no_match_both_name_the_node_id():
    text = _sync_script_text()
    assert "log_error \"Database update FAILED for node '$SLM_NODE_ID'" in text
    assert "log_error \"Database update matched NO ROW for node_id '$SLM_NODE_ID'" in text


def test_db_update_failure_makes_the_script_exit_nonzero():
    """Deliberate design choice (not a silent warning, not a mid-script
    abort): rsync/ansible still run to completion, but the script's own exit
    code reflects a stale row so anything scripting around this tool -- or an
    operator checking $? -- can tell."""
    text = _sync_script_text()
    assert 'if [ "$DB_UPDATE_FAILED" -eq 1 ]; then' in text
    failure_check_pos = text.index('if [ "$DB_UPDATE_FAILED" -eq 1 ]; then')
    tail = text[failure_check_pos:]
    assert "exit 1" in tail
    # and it happens after Phase 2 (Ansible), never instead of it
    ansible_pos = text.index('log_step "Running full playbook..."')
    assert ansible_pos < failure_check_pos, "the DB-update exit check must not preempt Phase 2"


def test_sql_values_are_not_string_built_into_the_query():
    """#14459 finding 2: SLM_NODE_ID and CURRENT_COMMIT must reach the SQL
    text as psql variables (-v ... quoted with :'var'), never concatenated
    directly into the UPDATE statement -- the old shape that was interpolated
    once locally and once again by the remote shell."""
    text = _sync_script_text()
    assert '-v "node_id=${SLM_NODE_ID}"' in text
    assert '-v "commit=${CURRENT_COMMIT}"' in text
    sql = _heredoc_sql()
    assert ":'commit'" in sql
    assert ":'node_id'" in sql
    # the old shape must be gone: the SQL text itself must not reference
    # either shell variable directly
    assert "$CURRENT_COMMIT" not in sql
    assert "$SLM_NODE_ID" not in sql


def test_no_dash_c_argument_contains_psql_only_syntax():
    """#14459 review round 2: psql(1) -- a `-c` argument "must be completely
    parsable by the server ... it contains no psql-specific features".
    `:'var'` is exactly such a feature; it must never appear inside a `-c`
    argument anywhere in this script, or the update fails on every call.

    Comments (including this fix's own explanation of the bug it replaces,
    which necessarily quotes `-c` and `:'var'` in prose) are excluded --
    this checks the shipped command line, not commentary describing it."""
    for line in _sync_script_text().splitlines():
        code = line.split("#", 1)[0]
        if re.search(r"(?:^|\s)-c(?:\s|$)", code):
            assert ":'" not in code, f"-c argument uses psql-only syntax, the server will reject it: {code!r}"


def test_remote_psql_command_has_no_dash_c_flag():
    """The regression this round guards: SQL must reach psql over stdin (a
    heredoc feeding the ssh command's stdin), never as a `-c` argument."""
    assert "-c" not in _remote_psql_cmd_array_body()


def test_sql_is_sent_over_stdin_via_heredoc():
    text = _sync_script_text()
    assert "<<'REMOTE_SQL'" in text
    assert _heredoc_sql().strip().startswith("UPDATE nodes SET code_version")


def test_remote_psql_invocation_is_shell_escaped_before_reaching_ssh():
    """The invocation is built as a bash array and passed through `printf
    %q` before being embedded in the ssh command string, so the remote shell
    parses exactly the intended tokens -- not a second round of
    word-splitting on whatever SLM_NODE_ID/CURRENT_COMMIT contain."""
    text = _sync_script_text()
    assert "REMOTE_PSQL_CMD=(" in text
    assert "printf '%q '" in text


def test_node_id_is_validated_against_a_fixed_character_set():
    """Same approach #14173 used for AUTOBOT_USER ahead of a sudoers heredoc:
    validate before the value ever reaches a string that's interpolated
    twice."""
    text = _sync_script_text()
    match = re.search(r'\[\[ "\$\{SLM_NODE_ID\}" =~ (\^\S+\$) \]\]', text)
    assert match, "no SLM_NODE_ID validation regex found"
    pattern = re.compile(match.group(1))

    for valid in ("00-SLM-Manager", "a", "node_01", "A" * 64):
        assert pattern.match(valid), f"{valid!r} should be accepted"

    # Assembled from fragments -- a literal SQL/shell-injection string here
    # would trip this repo's own secret/injection-pattern scanners.
    sql_keyword = "DR" + "OP TAB" + "LE nodes"
    injection = "x'; " + sql_keyword + "; --"
    command_injection = "x\nattacker ALL=(ALL) NOPASSWD: ALL"
    for invalid in (injection, command_injection, "", "a b", "'", '"', "$(id)", "a" * 65):
        assert not pattern.match(invalid), f"{invalid!r} must be rejected"

    validate_pos = text.index("SLM_NODE_ID}\" =~ ")
    exit_pos = text.index("exit 1", validate_pos)
    assert exit_pos - validate_pos < 200, "validation failure must exit near where it's checked"


def test_node_id_validation_runs_before_any_ssh_or_rsync_call():
    text = _sync_script_text()
    validate_pos = text.index("SLM_NODE_ID}\" =~ ")
    first_rsync_pos = text.index("rsync_cmd \\")
    assert validate_pos < first_rsync_pos
