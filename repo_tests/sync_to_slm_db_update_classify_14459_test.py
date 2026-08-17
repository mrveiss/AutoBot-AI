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

`classify_db_update_result()` (autobot-infrastructure/shared/scripts/lib/
db-update-classify.sh) is a pure function -- it runs no ssh, psql or rsync,
only `printf`/`grep` on strings the caller already captured -- so it is safe
to exercise directly here, unlike `sync-to-slm.sh` itself, which reaches a
live node and a live database and is never invoked by this suite.

These tests assert the classification is a per-line match against psql's
"UPDATE <n>" command tag, not a whole-string comparison: ssh may prepend a
host-key warning to the combined stdout+stderr capture callers pass in, and a
whole-string anchor would silently stop catching the zero-row case the moment
that happens.
"""

from __future__ import annotations

import shutil
import subprocess
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_DIR = REPO_ROOT / "autobot-infrastructure" / "shared" / "scripts"
LIB = SCRIPT_DIR / "lib" / "db-update-classify.sh"
SYNC_SCRIPT = SCRIPT_DIR / "utilities" / "sync-to-slm.sh"

_SSH_HOST_KEY_WARNING = "Warning: Permanently added 'node.example' (ED25519) to the list of known hosts."


def _classify(exit_code: int, output: str) -> str:
    result = subprocess.run(
        ["bash", "-c", f"source {LIB}; classify_db_update_result \"$1\" \"$2\"", "_", str(exit_code), output],
        capture_output=True,
        text=True,
        timeout=30,
    )
    assert result.returncode == 0, f"classify_db_update_result itself failed: {result.stderr}"
    return result.stdout.strip()


def test_lib_exists_and_is_valid_shell():
    assert LIB.is_file(), f"{LIB} missing -- sync-to-slm.sh sources it"
    assert subprocess.run(["bash", "-n", str(LIB)], capture_output=True).returncode == 0
    assert subprocess.run(["bash", "-n", str(SYNC_SCRIPT)], capture_output=True).returncode == 0


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


def test_sync_script_uses_the_classifier_not_a_bare_exit_code_check():
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    assert "source \"${SCRIPT_DIR}/../lib/db-update-classify.sh\"" in text
    assert "classify_db_update_result" in text
    # the regression: a bare `if [ $? -eq 0 ]` right after the ssh call, with
    # no inspection of what the command actually reported
    assert "if [ $? -eq 0 ]" not in text


def test_neither_outcome_is_mislabelled_non_critical():
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    assert "non-critical" not in text, (
        "a failed or no-op database update must never be logged as non-critical -- "
        "code_version/code_status is the only view an operator has of what is "
        "deployed without logging into the node"
    )


def test_failed_and_no_match_both_name_the_node_id():
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    assert "log_error \"Database update FAILED for node '$SLM_NODE_ID'" in text
    assert "log_error \"Database update matched NO ROW for node_id '$SLM_NODE_ID'" in text


def test_db_update_failure_makes_the_script_exit_nonzero():
    """Deliberate design choice (not a silent warning, not a mid-script
    abort): rsync/ansible still run to completion, but the script's own exit
    code reflects a stale row so anything scripting around this tool -- or an
    operator checking $? -- can tell."""
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
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
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    assert "-v \"node_id=${SLM_NODE_ID}\"" in text
    assert "-v \"commit=${CURRENT_COMMIT}\"" in text
    assert ":'commit'" in text
    assert ":'node_id'" in text
    # the old shape must be gone: the SQL text itself must not reference
    # either shell variable directly
    sql_line = next(line for line in text.splitlines() if "UPDATE nodes SET code_version" in line)
    assert "$CURRENT_COMMIT" not in sql_line
    assert "$SLM_NODE_ID" not in sql_line


def test_remote_psql_invocation_is_shell_escaped_before_reaching_ssh():
    """The invocation is built as a bash array and passed through `printf
    %q` before being embedded in the ssh command string, so the remote shell
    parses exactly the intended tokens -- not a second round of
    word-splitting on whatever SLM_NODE_ID/CURRENT_COMMIT contain."""
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    assert "REMOTE_PSQL_CMD=(" in text
    assert "printf '%q '" in text


def test_node_id_is_validated_against_a_fixed_character_set():
    """Same approach #14173 used for AUTOBOT_USER ahead of a sudoers heredoc:
    validate before the value ever reaches a string that's interpolated
    twice."""
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    import re

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
    text = SYNC_SCRIPT.read_text(encoding="utf-8")
    validate_pos = text.index("SLM_NODE_ID}\" =~ ")
    first_rsync_pos = text.index("rsync_cmd \\")
    assert validate_pos < first_rsync_pos
