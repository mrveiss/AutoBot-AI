# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#20935: no credential in any origin URL form reaches the remote test node (ssh argv or the node's git config)."""

from __future__ import annotations

import importlib.util
import sys

import pytest
from repo_tests._paths import repo_root

_spec = importlib.util.spec_from_file_location(
    "remote_test_node_run_url", repo_root() / "tools/remote_test_node/run.py"
)
run = importlib.util.module_from_spec(_spec)
sys.modules["remote_test_node_run_url"] = run
_spec.loader.exec_module(run)
sys.modules.pop("remote_test_node_run_url", None)  # needed only while the dataclass is built


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://user:tok@host/org/repo.git", "https://host/org/repo.git"),  # pragma: allowlist secret
        ("https://tok@host:8443/org/repo.git", "https://host:8443/org/repo.git"),
        ("https://host/org/repo.git", "https://host/org/repo.git"),
        ("git@host:org/repo.git", "git@host:org/repo.git"),
        ("git@host:x", "git@host:x"),
        ("tok@host:x", "tok@host:x"),  # scp form: no colon before the @, so no secret  # pragma: allowlist secret
        ("user:tok@host/x.git", "host/x.git"),  # pragma: allowlist secret
        ("user:tok@host:x.git", "host:x.git"),  # pragma: allowlist secret
        (
            "user:tok@host/x.git?r=http://a",
            "host/x.git",
        ),  # a "://" in the query is not a scheme  # pragma: allowlist secret
        ("user:tok@host:x?q=ssh://b", "host:x"),  # pragma: allowlist secret
        ("tok@host/x.git", "host/x.git"),  # bare token as user, a "/" after the host  # pragma: allowlist secret
        ("git@host:org/a/b.git", "git@host:org/a/b.git"),  # scp path with slashes stays
        ("host:dir/a@b", "b"),  # known limit, fails safe: an "@" in an scp path reads as userinfo
    ],
)
def test_the_origin_url_sent_to_the_node_carries_no_credential(url, expected):
    assert run._without_credentials(url) == expected


@pytest.mark.parametrize(
    "url,expected",
    [
        ("https://host/x.git?token=abc", "https://host/x.git"),  # pragma: allowlist secret
        ("https://host/x.git#frag", "https://host/x.git"),
        ("https://u:p@host/x.git?a=b#c", "https://host/x.git"),  # pragma: allowlist secret
    ],
)
def test_query_and_fragment_never_travel_to_the_node(url, expected):
    assert run._without_credentials(url) == expected


def test_an_ssh_url_loses_its_username_because_the_node_holds_no_key():
    assert run._without_credentials("ssh://git@host/org/repo.git") == "ssh://host/org/repo.git"


def test_an_unreadable_url_is_refused_without_echoing_it():
    with pytest.raises(ValueError) as exc:
        run._without_credentials("user:tok@")  # pragma: allowlist secret
    assert "tok" not in str(exc.value)
