# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#21987: the CodeQL `py/redos` regexes in repo tests stay linear and keep their matches."""

from __future__ import annotations

import time

import pytest
from repo_tests._ansible_query_tasks import _QUERY
from repo_tests._isolated_git_detect import _SHELL_GIT
from repo_tests.apt_retry_one_mechanism_21325_test import _APT
from repo_tests.branch_sync_workflow_test import _REBASE

_BOUND_S = 2.0
_N = 50_000


def _timed(fn, text):
    start = time.perf_counter()
    fn(text)
    return time.perf_counter() - start


@pytest.mark.parametrize(
    "regex, hit, miss",
    [
        (_REBASE, "git -c x=y rebase main", "git -c x=y rebasing main"),
        (_SHELL_GIT, "git -C dir commit -m x", "git -C dir status"),
        (_QUERY, "systemctl --user is-active foo", "systemctl --user restart foo"),
        (_QUERY, "tool --version", "tool --help"),
        (_APT, "apt-get -y -o Dpkg::X=1 install curl", "apt-get -y list"),
        (_APT, "apt-get -o X install curl", "apt-get -o install"),
    ],
)
def test_matches_unchanged(regex, hit, miss):
    assert regex.search(hit)
    assert not regex.search(miss)


@pytest.mark.parametrize(
    "regex, text",
    [
        (_REBASE, "git " + "-x " * _N + "z"),
        (_REBASE, "git -" + "\x7f" * _N),
        (_SHELL_GIT, "git " + "-a " * _N + "z"),
        (_SHELL_GIT, "git " + "-!\x7f" * _N),
        (_QUERY, "systemctl " + "--a " * _N + "z"),
        (_QUERY, "systemctl\t--" + "!\x7f--" * _N),
        (_QUERY, "{{ x }}" * _N + "!"),
        (_APT, "apt-get " + "-y " * _N + "z"),
        (_APT, "apt-get " + "-c\x7f!\t-" * _N),
        (_APT, "apt-get " + "-o x " * _N + "z"),
    ],
)
def test_pathological_input_is_linear(regex, text):
    assert _timed(regex.search, text) < _BOUND_S
