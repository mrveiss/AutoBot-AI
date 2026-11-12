# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The fallback apt mirror is applied only after a bounded probe, and its callers keep that contract (#21325).

An unconditional, unprobed fallback ordered a stalling mirror first and held Clean install jobs silent for
30 to 65 minutes. The behaviour is pinned on stubbed curl in ``scripts/ci/apt_fallback_mirror_test.py``; this
file pins the wiring around it: one probe-limit definition, the caller that skips only the PRIMARY probe, and
the step bound on the unconditional call in Clean install.
"""

from __future__ import annotations

import re

import yaml
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_text

_ROOT = repo_root()
_SCRIPT = _ROOT / "scripts/ci/apt_fallback_mirror.sh"
_ACTION = _ROOT / ".github/actions/setup-python-suite/action.yml"
_WORKFLOW = _ROOT / ".github/workflows/clean-install.yml"


def _script_code() -> str:
    return code_text(_SCRIPT.read_text(encoding="utf-8"), name=_SCRIPT.name)


def test_the_probe_limit_is_defined_once_and_every_request_uses_it() -> None:
    code = _script_code()
    assert len(re.findall(r"^readonly APT_PROBE_TIMEOUT_S=", code, re.M)) == 1
    assert not re.search(r"--max-time\s+\d|--connect-timeout\s+\d|timeout\s+(-k\s+\d+\s+)?\d", code), "a literal bound"
    assert code.count("--max-time") == 1 and code.count("--connect-timeout") == 1


def test_the_script_probes_both_mirrors_before_any_write() -> None:
    code = _script_code()
    assert 'probe "fallback mirror"' in code
    assert code.index('probe "fallback mirror"') < code.index("$(apply_fallback)")
    assert "apt-get" not in code, "the probe is not an apt call: the one-mechanism guard stays about the wrapper"


def test_clean_install_calls_the_script_once_under_a_short_step_timeout() -> None:
    steps = yaml.safe_load(_WORKFLOW.read_text(encoding="utf-8"))["jobs"]["install"]["steps"]
    calls = [s for s in steps if "apt_fallback_mirror.sh" in s.get("run", "")]
    assert len(calls) == 1 and calls[0]["name"] == "Use the fallback apt mirror"
    assert isinstance(calls[0]["timeout-minutes"], int) and calls[0]["timeout-minutes"] <= 5
    assert "--primary-known-bad" not in calls[0]["run"], "Clean install has not seen the primary fail"


def test_the_provisioning_retry_skips_only_the_primary_probe() -> None:
    text = _ACTION.read_text(encoding="utf-8")
    assert re.search(r'APT_FALLBACK_SCRIPT" /etc/apt "\$APT_FALLBACK_MIRROR" --primary-known-bad', text)
    assert text.count("--primary-known-bad") >= 1
    assert "--skip-fallback-probe" not in text
