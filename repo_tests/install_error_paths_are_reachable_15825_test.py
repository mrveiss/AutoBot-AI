# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""install.sh's warn-and-continue handlers must actually run (#15825).

`install.sh` sets `set -euo pipefail` at line 18. Three call sites captured a
`curl` result into a variable:

    token=$(curl -sfk ... | jq ...)
    http_code=$(curl -sfk ... -w "%{http_code}" ...)
    cs_code=$(curl -sfk ... -w "%{http_code}" ...)

A failed assignment aborts the script under `set -e`, and `-f` makes curl exit
22 on any HTTP >= 400. So every handler *below* those lines was unreachable:
the "could not authenticate, skipping node registration" warnings, the `400)`
arm meaning "already registered" (an expected outcome on any re-run), and the
catch-all warn. They read as careful error handling and could not execute.

The user experienced this as phase 6 aborting with no install marker, no
credentials file and no completion banner — after both root causes (#15822,
#15823) were fixed.

**Why these tests execute the code instead of reading it.** The handlers were
present the whole time. Any assertion of the form "the warn line exists" or
"the case has a 400 arm" passed while the defect was live — that is precisely
the assertion this file must not make. Reachability is a runtime property, so
these run the real function with `curl` stubbed and assert on its output.

**What they do not cover.** They exercise `register_local_node` only, with a
stubbed curl and jq. They say nothing about whether the API contract is right,
whether the node is actually registered, or about the phases either side. Those
need a real install against a real SLM, which is not something a unit test can
stand in for.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
import tempfile
from pathlib import Path

import pytest

_INSTALL = Path(__file__).resolve().parents[1] / "install.sh"


def _function_source(name: str) -> str:
    """The named shell function, verbatim, from install.sh."""
    text = _INSTALL.read_text(encoding="utf-8")
    match = re.search(rf"^{re.escape(name)}\(\) \{{.*?^\}}", text, re.S | re.M)
    assert match, f"{name}() not found in install.sh — this file would test nothing"
    return match.group(0)


def _curl_stub(routes: dict[str, str]) -> str:
    """A curl stub that honours `-f` the way real curl does.

    This matters more than it looks. A stub that always exits 0 cannot tell a
    `-f` call from a `-sk` one, so every `-f`-related assertion passes whatever
    the script says — which is exactly the failure being tested for, reproduced
    inside the test harness. Real curl exits 22 on HTTP >= 400 when `-f` is
    given, and this does the same.
    """
    arms = "\n".join(f"  {pat}) code={code} ;;" for pat, code in routes.items())
    return f"""#!/bin/sh
has_f=0
for a in "$@"; do
  case "$a" in -*f*) has_f=1 ;; esac
done
code=200
case "$*" in
{arms}
esac
[ "$code" -ge 400 ] && [ "$has_f" = 1 ] && exit 22
case "$*" in
  *auth/login*) echo '{{"access_token":"t"}}' ;;
  *)            printf '%s' "$code" ;;
esac
exit 0
"""


def _run(curl_stub: str, *, function: str = "register_local_node", extra: str = "") -> subprocess.CompletedProcess:
    """Run one install.sh function with `curl` stubbed, under the real flags.

    `set -euo pipefail` is reproduced exactly, because it *is* the defect: the
    handlers are reachable or not depending on it. A harness that relaxed the
    flags would pass against the broken script.
    """
    with tempfile.TemporaryDirectory() as tmp:
        bin_dir = Path(tmp) / "bin"
        bin_dir.mkdir()
        (bin_dir / "curl").write_text(curl_stub, encoding="utf-8")
        (bin_dir / "curl").chmod(0o755)
        # jq is stubbed too so the token path does not depend on it being
        # installed on the runner.
        (bin_dir / "jq").write_text("#!/bin/sh\ncat\n", encoding="utf-8")
        (bin_dir / "jq").chmod(0o755)

        script = f"""
set -euo pipefail
LOG_FILE={tmp}/install.log
CYAN=''; GREEN=''; YELLOW=''; RED=''; NC=''
info()    {{ echo "[INFO] $*" | tee -a "${{LOG_FILE}}"; }}
success() {{ echo "[OK] $*" | tee -a "${{LOG_FILE}}"; }}
warn()    {{ echo "[WARN] $*" | tee -a "${{LOG_FILE}}"; }}
phase()   {{ echo "[PHASE] $*" | tee -a "${{LOG_FILE}}"; }}
log()     {{ echo "[LOG] $*" >> "${{LOG_FILE}}"; }}
# The health poll runs before the code under test; `curl -sk ... /api/health`
# sits inside a `while !`, so the stub must succeed there or the function
# spends 60s in the wait loop and never reaches the handlers being tested.
hostname() {{ echo test-host; }}
detect_local_ip() {{ echo 10.0.0.1; }}
sleep()    {{ :; }}
ADMIN_PASSWORD=pw
SLM_NODE_ID=node-1
CODE_SOURCE=/src
GIT_BRANCH=main
{extra}
{_function_source(function)}
{function}
echo "FUNCTION_RETURNED"
"""
        env = dict(os.environ, PATH=f"{bin_dir}:{os.environ['PATH']}")
        return subprocess.run(
            [shutil.which("bash") or "bash", "-c", script],
            capture_output=True,
            text=True,
            env=env,
            timeout=60,
        )


def test_a_failed_auth_reaches_the_skip_warning() -> None:
    """Auth failure must warn and continue, not abort the installer.

    `curl -f` exits 22 on a 401. Before the fix the assignment aborted the
    script and neither warn line could run — the installer simply stopped, with
    no statement of why.
    """
    result = _run(_curl_stub({"*auth/login*": 401, "*api/nodes*": 201}))

    assert "Could not authenticate with SLM API" in result.stdout, (
        f"the auth-failure handler did not run; the script aborted at the assignment instead.\n"
        f"stdout={result.stdout!r} stderr={result.stderr!r}"
    )
    assert "FUNCTION_RETURNED" in result.stdout, (
        "the function did not return — a warn-and-continue path that does not continue is the "
        "defect this test exists for"
    )


def test_an_already_registered_node_reaches_the_400_arm() -> None:
    """400 means "already registered" and is an expected outcome on re-run.

    With `-f`, curl exits 22 on a 400 and the arm below it never ran, so a
    perfectly normal second install aborted.
    """
    result = _run(_curl_stub({"*api/nodes*": 400, "*code-source/assign*": 200}))

    assert (
        "already registered" in result.stdout
    ), f"the 400 arm did not run.\nstdout={result.stdout!r} stderr={result.stderr!r}"
    assert "FUNCTION_RETURNED" in result.stdout


def test_an_unexpected_status_reaches_the_catch_all_warning() -> None:
    """A 500 must warn and return, leaving the rest of the install to proceed."""
    result = _run(_curl_stub({"*api/nodes*": 500}))

    assert (
        "Node registration returned HTTP 500" in result.stdout
    ), f"the catch-all arm did not run.\nstdout={result.stdout!r} stderr={result.stderr!r}"
    assert "FUNCTION_RETURNED" in result.stdout


def test_a_code_source_failure_warns_without_aborting() -> None:
    """The last handler in the function, past both earlier ones."""
    result = _run(_curl_stub({"*api/nodes*": 201, "*code-source/assign*": 503}))

    assert (
        "Code source assignment returned HTTP 503" in result.stdout
    ), f"the code-source handler did not run.\nstdout={result.stdout!r} stderr={result.stderr!r}"
    assert "FUNCTION_RETURNED" in result.stdout


def test_the_happy_path_still_works() -> None:
    """The contrast case.

    Without it, a harness that never reached the function at all would satisfy
    every assertion above by printing nothing and failing them — but a harness
    that swallowed errors would satisfy them too. This proves the stub drives
    the real code rather than a permanently-failing shell.
    """
    result = _run(_curl_stub({"*api/nodes*": 201, "*code-source/assign*": 200}))

    assert "Local node registered" in result.stdout, result.stdout
    assert "Code source assigned" in result.stdout, result.stdout
    assert result.returncode == 0


@pytest.mark.parametrize("flag_site", ["nodes", "code-source"])
def test_status_capturing_curls_do_not_use_dash_f(flag_site: str) -> None:
    """`-f` and `-w "%{http_code}"` are contradictory intents.

    Asking curl for the status code while also telling it to fail on the codes
    you are branching on cannot work. This is the static half — it catches a
    reintroduction at the call site rather than waiting for the runtime symptom.
    """
    text = _INSTALL.read_text(encoding="utf-8")
    var = {"nodes": "http_code", "code-source": "cs_code"}[flag_site]
    # Anchored to the ASSIGNMENT, not searched across the file. An earlier
    # version matched from the first status-capturing curl and ran to the site
    # name, so the code-source case was reading the nodes curl's flags — it
    # reported on a call site it had never looked at, and a mutation restoring
    # -f on code-source survived it.
    block = re.search(rf"^\s*{var}=\$\(curl -s(f?)k[^\n]*$", text, re.M)
    assert block, f"could not find the {var} assignment — this test would pass having read nothing"
    assert block.group(1) != "f", (
        f"the {flag_site} curl uses -f while capturing %{{http_code}}: it will exit 22 on the very "
        "codes the case statement branches on, and the arms below become unreachable (#15825)"
    )
