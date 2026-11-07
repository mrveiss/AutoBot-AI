# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Connector egress policy is applied, and applied to the right URL class (#13625).

Rule 8 turns on one distinction: the operator-configured *instance host* may use
the private-network opt-in; anything else — a URL read out of a document, an API
response or a user request — is public-only, always. Getting that backwards is
the dangerous direction, because it looks like it works.

**The population is enumerated, not listed (#17576).** This file used to hold a
dict of five filenames with an expected call count each, and its strongest test
was named for its own boundary: *"no unguarded tracked_request remains in the
**named** connectors"*. Four connectors sitting beside those five — `gdrive`,
`notion`, `onedrive`, `slack` — each made an unguarded outbound call for as long
as that dict existed, because a guard that iterates what it was told about cannot
see a call site nobody added to it. The directory is the population now, so a new
connector is in scope by existing.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

_CONNECTORS = Path(__file__).resolve().parent

#: Floors, measured against this directory rather than the tree (#17517's lesson:
#: a floor taken from a different population is not a floor). 23 non-test modules,
#: 10 of them making outbound calls, at the time of #17576. Both only ever rise;
#: a collapse means the enumeration stopped seeing the directory, and a clean
#: result would then assert nothing.
_MODULE_FLOOR = 18
_OUTBOUND_FLOOR = 8

#: A bare ``aiohttp.ClientSession`` is forbidden by Rule 8. This one is the
#: documented exception, counted by ``tests/test_raw_client_session_ceiling_12992.py``
#: with its reason there: the OAuth token exchange passes an explicit pinned
#: ``connector`` for DNS-rebind safety, which the shared client does not expose.
#: An entry here is a claim that a reason is recorded elsewhere, not a pass.
_RAW_SESSION_EXCEPTIONS = {"oauth_flow.py"}


def _modules() -> list[Path]:
    """Every non-test module in this directory."""
    return sorted(
        p for p in _CONNECTORS.glob("*.py") if not p.name.endswith("_test.py") and not p.name.startswith("test_")
    )


def _code(path: Path) -> str:
    """Source with line comments stripped, so a mention in prose is not a call."""
    return "\n".join(ln.split("#", 1)[0] for ln in path.read_text(encoding="utf-8").splitlines())


#: Every request method of ``HTTPClientManager`` that takes ``guard_egress``:
#: ``tracked_request`` and ``request`` directly, ``get``/``post`` and the
#: ``get_json``/``post_json`` wrappers through ``**kwargs``. ``tracked_request``
#: is unambiguous on any receiver; the others also name ``dict.get`` and friends,
#: so they count only on a receiver that is the client (``get_http_client()``) or
#: a name saying so, which keeps ``result.get("status_code")`` out (#17576).
_OUTBOUND_CALL = re.compile(
    r"(?:\btracked_request"
    r"|(?:get_http_client\(\)|\b\w*(?:client|session|manager)\w*)\s*\.\s*(?:request|get|post|get_json|post_json))\("
)


def _call_slices(code: str) -> list[str]:
    """The argument text of each outbound manager call, by balanced parentheses.

    Counting ``tracked_request(`` and ``guard_egress=`` separately and comparing
    the totals is what the first version of this did, and it is wrong twice: a
    docstring saying *"pass the result as guard_egress="* inflates the second
    count with no call at all (``base.py`` does exactly that, and this guard
    caught it), and two calls with two mentions pass even when one call carries
    both and the other none. The policy belongs to a call, so the check reads one
    call at a time.
    """
    slices = []
    for match in _OUTBOUND_CALL.finditer(code):
        depth, i = 1, match.end()
        while i < len(code) and depth:
            depth += (code[i] == "(") - (code[i] == ")")
            i += 1
        slices.append(code[match.end() : i])
    return slices


def _outbound(path: Path) -> tuple[int, list[int]]:
    """(number of calls, 1-based indexes of the calls carrying no policy)."""
    calls = _call_slices(_code(path))
    return len(calls), [n for n, args in enumerate(calls, 1) if "guard_egress" not in args]


def test_the_enumeration_still_sees_the_directory():
    """The floor check. Without it, a glob that matches nothing passes everything."""
    modules = _modules()
    assert len(modules) >= _MODULE_FLOOR, (
        f"enumerated only {len(modules)} modules, below the floor of {_MODULE_FLOOR} — "
        "the sweep has stopped seeing the directory, so a clean result asserts nothing"
    )
    with_calls = [p.name for p in modules if _outbound(p)[0]]
    assert len(with_calls) >= _OUTBOUND_FLOOR, (
        f"found outbound calls in only {len(with_calls)} modules ({with_calls}), below the floor "
        f"of {_OUTBOUND_FLOOR} — the detector has stopped matching, not the connectors stopped calling"
    )


def test_every_outbound_call_declares_an_egress_policy():
    """Rule 8 at every call site in the directory, named or not."""
    offenders = []
    for path in _modules():
        if path.name in _RAW_SESSION_EXCEPTIONS:
            continue  # its policy is the pinned connector, not guard_egress; see _RAW_SESSION_EXCEPTIONS
        calls, unguarded = _outbound(path)
        if unguarded:
            offenders.append(f"{path.name}: call(s) {unguarded} of {calls} carry no guard_egress")
    assert not offenders, "outbound calls with no egress policy (Rule 8, #13625, #17576):\n  " + "\n  ".join(offenders)


@pytest.mark.parametrize(
    "call",
    [
        'get_http_client().tracked_request("GET", url)',
        'client.request("GET", url)',
        "self._client.get(url)",
        "get_http_client().post(url, data=x)",
        "http_client.get_json(url)",
        "client.post_json(url, {})",
    ],
)
def test_contrast_the_detector_sees_every_manager_request_method(call):
    """An unguarded call by any manager method is an offender; the guarded form is not."""
    assert len(_call_slices(call)) == 1
    assert "guard_egress" not in _call_slices(call)[0]
    guarded = call[:-1] + ", guard_egress=False)"
    assert "guard_egress" in _call_slices(guarded)[0]


@pytest.mark.parametrize("call", ['result.get("status_code")', 'cfg.get("token", "")', "self._cache.get(key)"])
def test_contrast_the_detector_ignores_dict_style_get(call):
    assert _call_slices(call) == []


def test_no_connector_builds_a_bare_client_session():
    """Rule 8's other half: never build a bare ``aiohttp.ClientSession``."""
    offenders = [
        path.name
        for path in _modules()
        if "aiohttp.ClientSession(" in _code(path) and path.name not in _RAW_SESSION_EXCEPTIONS
    ]
    assert not offenders, (
        "bare aiohttp.ClientSession outside the documented exceptions: "
        + ", ".join(offenders)
        + " — use get_http_client().tracked_request(), or record the reason with the #12992 ceiling"
    )


def test_a_raw_session_exception_still_builds_one():
    """A stranded exception is a stale claim, the doctrine #15208 states."""
    stranded = [
        name
        for name in sorted(_RAW_SESSION_EXCEPTIONS)
        if not (_CONNECTORS / name).is_file() or "aiohttp.ClientSession(" not in _code(_CONNECTORS / name)
    ]
    assert not stranded, f"exempted but no longer builds a raw session — delete the entry: {stranded}"


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


def test_vendor_api_policy_is_public_only():
    """A hosted vendor API has no self-hosted deployment, so no private-address case.

    The override key (`cfg.get("slack_api_base", _SLACK_API_BASE)`) means the host
    *is* operator-configurable, which is why the call needs a policy at all — and
    why the policy must not be the instance-host opt-in (#17576).
    """
    from knowledge.connectors.base import VENDOR_API_EGRESS

    assert VENDOR_API_EGRESS is False


@pytest.mark.parametrize("filename", ["gdrive.py", "notion.py", "onedrive.py", "slack.py"])
def test_the_vendor_connectors_use_the_vendor_policy(filename):
    """Not merely guarded — guarded with the policy that cannot reach a private host."""
    code = _code(_CONNECTORS / filename)

    assert "guard_egress=VENDOR_API_EGRESS" in code
    assert "instance_host_egress" not in code, f"{filename} is a hosted API, not a self-hosted instance"


def test_instance_host_policy_follows_the_deployment_flag():
    from knowledge.connectors.base import instance_host_egress

    assert instance_host_egress() is False, "the private-network opt-in must default to off"
