# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every python-suite shard runs pytest with a faulthandler_timeout (#16516).

A test that hung in one shard printed its last ``-q`` dot and then nothing
until the job hit its one-hour limit, so the log could not say which test was
stuck. ``faulthandler_timeout`` makes pytest dump every thread's traceback into
the log once a test runs past the limit.

The limit is ONE setting: the ``python-shard`` job's ``env`` entry. This test
reads the value from the workflow and checks that each shard invocation refers
to it by name. It never restates the number, so the two cannot drift apart.
"""

from __future__ import annotations

import re
import shlex

import yaml
from repo_tests._paths import repo_root

_CI = repo_root() / ".github" / "workflows" / "ci.yml"
_JOB = "python-shard"
_SETTING = "PYTEST_FAULTHANDLER_TIMEOUT_S"
_OVERRIDE_FLAGS = ("-o", "--override-ini")
_EXPECTED = f"faulthandler_timeout=${_SETTING}"

#: A pytest command line, however the interpreter is spelled.
_PYTEST_COMMAND = re.compile(r"^(?:python3?\s+-m\s+)?pytest(?:\s|$)")

#: A `faulthandler_timeout` given a number in place, anywhere in the workflow.
_RESTATED_LITERAL = re.compile(r"faulthandler_timeout\s*=\s*[\"']?\d")


def _document() -> dict:
    return yaml.safe_load(_CI.read_text(encoding="utf-8"))


def _job() -> dict:
    jobs = _document()["jobs"]
    assert _JOB in jobs, f"FIX THE SWEEP: no {_JOB} job in ci.yml"
    return jobs[_JOB]


def _pytest_commands() -> list[list[str]]:
    """Each pytest command in the shard job's steps, as argv tokens."""
    commands = []
    for step in _job()["steps"]:
        body = step.get("run", "")
        for line in body.replace("\\\n", " ").splitlines():
            stripped = line.strip()
            if _PYTEST_COMMAND.match(stripped):
                commands.append(shlex.split(stripped))
    return commands


def _faulthandler_overrides(tokens: list[str]) -> list[str]:
    """Every `-o faulthandler_timeout=...` value the command passes."""
    return [
        value
        for flag, value in zip(tokens, tokens[1:])
        if flag in _OVERRIDE_FLAGS and value.startswith("faulthandler_timeout=")
    ]


def test_the_sweep_finds_both_shard_invocations():
    """Vacuity floor: the backend and slm-backend runs are separate commands."""
    assert len(_pytest_commands()) >= 2, (
        f"FIX THE SWEEP: found {len(_pytest_commands())} pytest commands in the "
        f"{_JOB} job, expected the backend and slm-backend invocations"
    )


def test_every_shard_invocation_passes_the_setting():
    """#16516: a hang printed nothing because no shard set a faulthandler_timeout."""
    for tokens in _pytest_commands():
        overrides = _faulthandler_overrides(tokens)
        assert overrides == [_EXPECTED], (
            f"a {_JOB} pytest command passes {overrides or 'no faulthandler_timeout'}; "
            f"add `-o faulthandler_timeout=\"${_SETTING}\"` to: {' '.join(tokens[:6])} ..."
        )


def test_the_setting_is_defined_once_on_the_shard_job():
    """One place holds the value, so no copy can disagree with it."""
    job = _job()
    value = job.get("env", {}).get(_SETTING)
    assert value is not None, f"the {_JOB} job's env no longer defines {_SETTING}"
    assert float(value) > 0, f"{_SETTING} is {value!r}; faulthandler_timeout=0 disables the dump"
    assert _SETTING not in _document().get("env", {}), f"{_SETTING} is also set workflow-wide"
    for step in job["steps"]:
        assert _SETTING not in step.get("env", {}), f"step {step.get('name')!r} shadows {_SETTING}"


def test_no_timeout_literal_is_restated():
    """The number lives only in the setting, never inline on a command."""
    restated = _RESTATED_LITERAL.findall(_CI.read_text(encoding="utf-8"))
    assert not restated, f"ci.yml hardcodes a faulthandler_timeout; read {_SETTING} instead"
