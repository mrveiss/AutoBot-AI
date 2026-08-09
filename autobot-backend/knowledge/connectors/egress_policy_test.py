# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Connector egress policy is applied, and applied to the right URL class (#13625).

Rule 8 turns on one distinction: the operator-configured *instance host* may use
the private-network opt-in; anything else — a URL read out of a document, an API
response or a user request — is public-only, always. Getting that backwards is
the dangerous direction, because it looks like it works.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_CONNECTORS = Path(__file__).resolve().parent

# file -> number of outbound calls that must carry an explicit egress policy
_GUARDED = {
    "confluence.py": 1,
    "jira.py": 1,
    "nextcloud.py": 3,
    "gitlab.py": 2,  # GitLab + Gitea
    "audio_connector.py": 1,
}


@pytest.mark.parametrize("filename,expected", sorted(_GUARDED.items()))
def test_connector_outbound_calls_declare_an_egress_policy(filename, expected):
    """Every outbound call in these modules passes guard_egress explicitly."""
    src = (_CONNECTORS / filename).read_text(encoding="utf-8")
    # Count only real arguments, not the string appearing in a comment.
    code = "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())
    found = code.count("guard_egress=")
    assert found == expected, f"{filename}: expected {expected} guarded call(s), found {found}"


def test_content_urls_never_use_the_instance_host_opt_in():
    """#13625: a download URL must not inherit the instance host's exemption.

    ``_download_direct_url`` takes its URL as a parameter, so if it used
    ``instance_host_egress()`` a document could name a private address and turn
    the connector into an SSRF vector into the operator's own network.
    """
    src = (_CONNECTORS / "audio_connector.py").read_text(encoding="utf-8")
    assert "guard_egress=CONTENT_URL_EGRESS" in src
    assert "instance_host_egress" not in src, "content download must not use the instance-host opt-in"


def test_content_url_policy_is_public_only():
    from knowledge.connectors.base import CONTENT_URL_EGRESS

    assert CONTENT_URL_EGRESS is False


def test_instance_host_policy_follows_the_deployment_flag():
    from knowledge.connectors.base import instance_host_egress

    assert instance_host_egress() is False, "the private-network opt-in must default to off"


def test_no_unguarded_tracked_request_remains_in_the_named_connectors():
    """A new outbound call in these files must not silently skip the policy."""
    offenders = []
    for filename in _GUARDED:
        src = (_CONNECTORS / filename).read_text(encoding="utf-8")
        code = "\n".join(ln.split("#", 1)[0] for ln in src.splitlines())
        calls = len(re.findall(r"tracked_request\(", code))
        guarded = code.count("guard_egress=")
        if calls != guarded:
            offenders.append(f"{filename}: {calls} call(s), {guarded} guarded")
    assert not offenders, "unguarded outbound calls: " + "; ".join(offenders)
