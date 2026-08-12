# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The secret-scan PreToolUse hook must block secrets and allow indirection (#12513).

Found while wiring #12513: the hook's generic credential rule was inverted in
practice. Its patterns spelled a single quote as ``\\x27``, which GNU grep does
not recognise as an escape -- the backslash collapses and ``["\\x27]`` becomes the
character class ``{", x, 2, 7}``. Measured against the shipped hook:

    double-quoted literal secret   -> ALLOWED   (should block)
    single-quoted literal secret   -> ALLOWED   (should block)
    jinja variable reference       -> BLOCKED   (should allow)

So the rule that exists to stop a committed credential let both quote styles
through, while blocking the exact pattern used to *avoid* hardcoding one -- every
Ansible task of the form ``some_token: "{{ var }}"``. A secret scanner that fails
open, silently, is worse than none: it is trusted.

These cases are pinned here because the failure is invisible by inspection. The
regex looks right; only running it reveals that it is not.

Every offending literal below is ASSEMBLED at run time rather than written out.
A test file for a secret scanner that itself trips the scanner would be unusable:
no later edit to it could pass the very hook it is testing.
"""

from __future__ import annotations

import json
import shutil
import subprocess
from pathlib import Path

import pytest

_HOOK = Path(__file__).resolve().parents[1] / ".claude" / "hooks" / "scan-secrets.sh"

_BLOCK = 2
_ALLOW = 0

#: Random-looking, not a real credential -- it exists to be rejected.
_LITERAL = "Xk3pQ9mZv" + "2Lb7Tn4Rd" + "8Ws1Ye6Uc0Ai5O"
_AWS_KEY = "AKIA" + "IOSFODNN7EXAMPLE"
_CONN = "postgresql://user:" + "hunter2hunter2" + "@db:5432/app"
#: Password-only userinfo -- what a Redis URL with AUTH actually looks like.
_CONN_NO_USER = "redis://:" + "hunter2hunter2" + "@cache:6379/0"
_DQ, _SQ = chr(34), chr(39)

CASES = [
    (_BLOCK, f"chromadb_auth_token: {_DQ}{_LITERAL}{_DQ}", "double-quoted literal"),
    (_BLOCK, f"api_key: {_SQ}{_LITERAL}{_SQ}", "single-quoted literal"),
    (_BLOCK, f"aws_key = {_AWS_KEY}", "AWS access key id"),
    (_BLOCK, _CONN, "connection string with credentials"),
    (_BLOCK, _CONN_NO_USER, "connection string, password-only userinfo"),
    (_ALLOW, "backend_chromadb_auth_token: " + _DQ + "{{ _chromadb_auth_token_read }}" + _DQ, "jinja reference"),
    (_ALLOW, "api_key: " + _DQ + "os.environ[" + _SQ + "OPENAI_KEY" + _SQ + "]" + _DQ, "os.environ reference"),
    (_ALLOW, "backend_chromadb_auth_token: " + _DQ + _DQ, "empty ansible default"),
    (_ALLOW, "# the token is read from slm-secrets.env", "prose mentioning a token"),
]


def _run(content: str) -> int:
    payload = json.dumps({"tool_name": "Edit", "tool_input": {"new_string": content}})
    result = subprocess.run(
        ["bash", str(_HOOK)],
        input=payload,
        capture_output=True,
        text=True,
        timeout=60,
    )
    return result.returncode


def test_hook_exists_and_is_valid_shell():
    assert _HOOK.is_file(), f"{_HOOK} missing -- the PreToolUse hook is configured against it"
    assert subprocess.run(["bash", "-n", str(_HOOK)], capture_output=True).returncode == 0, (
        "the hook has a shell syntax error; a hook that cannot run blocks nothing"
    )


@pytest.mark.parametrize("expected,content,label", CASES, ids=[c[2] for c in CASES])
def test_hook_decision(expected, content, label):
    if shutil.which("bash") is None or shutil.which("jq") is None:
        pytest.skip("bash and jq are required to exercise the hook")

    verb = "block" if expected == _BLOCK else "allow"
    assert _run(content) == expected, (
        f"the secret-scan hook must {verb} {label!r}. A wrong answer here is silent: "
        "a false negative ships a credential, a false positive makes every legitimate "
        "variable reference unwritable."
    )


def test_no_broken_quote_escape_survives_in_the_patterns():
    """The specific bug: GNU grep reads the hex escape for a quote as a literal ``x``.

    Pinned by inspection as well as by behaviour, because a future edit that
    reintroduces it would break the rules in a way the case list above might not
    happen to cover.
    """
    needle = chr(92) + "x27"
    text = _HOOK.read_text(encoding="utf-8")
    offending = [
        (n, line)
        for n, line in enumerate(text.splitlines(), 1)
        if needle in line and not line.lstrip().startswith("#")
    ]
    assert not offending, (
        "hook patterns still spell a single quote as a hex escape, which GNU grep "
        "collapses to a literal " + _SQ + "x" + _SQ + ":" + chr(10) + "  "
        + (chr(10) + "  ").join(f"{n}: {line.strip()}" for n, line in offending)
    )
