# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A live frontend WebSocket client's URL names a route the backend actually serves (#17020).

#17020 found two frontend clients opening WebSocket endpoints the backend does not serve
(`useCanvasWebSocket.ts` and the now-retired `Terminal.vue`). `SSHTerminal.vue` -- the terminal
component something actually mounts (`ChatTabContent.vue`) -- was checked by hand and found
correct; this pins that finding so a future edit to either side (the URL template, or the
backend route) is caught rather than silently drifting apart again the same way.

Scoped to the one client resolved by #17020's own investigation, not a general frontend-wide
scanner (that already exists for the SLM frontend, `slm_frontend_calls_reach_served_routes_test.py`
-- building an equivalent for the much larger main frontend is a separate undertaking, not
something this one client's pin needs).
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root
from repo_tests._registry_catalogue import catalogue_entries, entries_in_source

_ROOT = repo_root()

_SSH_TERMINAL_VUE = _ROOT / "autobot-frontend" / "src" / "components" / "terminal" / "SSHTerminal.vue"
_TERMINAL_PY = _ROOT / "autobot-backend" / "api" / "terminal.py"


#: The exact template SSHTerminal.vue's buildWsUrl() returns, minus the origin -- asserted
#: against the source text itself so a future edit to the template is caught by this string no
#: longer matching, not by a regex that would also accept an unintended rewrite.
_EXPECTED_TEMPLATE = "/api/terminal/ws/ssh/${props.hostId}${params}"


def test_ssh_terminal_vue_still_builds_the_expected_url_template() -> None:
    """Positive assertion first -- if the template moved, the match below would vacuously pass
    by comparing two things neither of which is what SSHTerminal.vue actually sends.
    """
    text = _SSH_TERMINAL_VUE.read_text(encoding="utf-8")
    assert _EXPECTED_TEMPLATE in text, (
        f"SSHTerminal.vue no longer builds {_EXPECTED_TEMPLATE!r} -- "
        "update this pin to match the new template, then re-verify it against a real backend route"
    )


def test_ssh_terminal_vue_url_matches_a_route_terminal_py_registers() -> None:
    template_path = _EXPECTED_TEMPLATE.split("${props.hostId}")[0].split("${params}")[0]
    # "/api/terminal/ws/ssh/" -- the literal prefix up to the first interpolation.
    assert template_path == "/api/terminal/ws/ssh/", (
        f"unexpected template shape {template_path!r} -- this test's parsing assumption broke, "
        "not necessarily the route itself"
    )

    terminal_py = _TERMINAL_PY.read_text(encoding="utf-8")
    assert re.search(r'@router\.websocket\("/ws/ssh/\{host_id\}"\)', terminal_py), (
        'terminal.py no longer registers @router.websocket("/ws/ssh/{host_id}") -- ' "SSHTerminal.vue's URL would 404"
    )

    # The catalogue's location is resolved, not named (#16375): this used to
    # `re.search` the source of `api/registry.py`, which found nothing once the
    # catalogue moved to `api/registry_catalog.py`. Asserting over parsed entries
    # also stops the check depending on how the literal happens to be formatted --
    # the old regex required `prefix=` on the line after `module_path=`, so a
    # reformat would have broken it as surely as the move did.
    advertised = dict(catalogue_entries(_ROOT / "autobot-backend"))
    assert advertised, (
        "no RouterConfig entries were parsed from the catalogue at all, so the prefix "
        "assertion below would pass over an empty mapping"
    )
    assert advertised.get("api.terminal") == "/api/terminal", (
        f"api.terminal's registered prefix is {advertised.get('api.terminal')!r}, not "
        '"/api/terminal" -- SSHTerminal.vue\'s hardcoded /api/terminal/... would no longer match'
    )


def test_the_route_regex_would_catch_a_removed_or_renamed_route() -> None:
    """Negative control over the SAME regex the route-match test above uses, on synthetic text
    standing in for a terminal.py that no longer registers the route (renamed, deleted, or
    re-decorated with a different path) -- proves the regex fails closed rather than matching
    something unrelated and passing vacuously.
    """
    route_pattern = r'@router\.websocket\("/ws/ssh/\{host_id\}"\)'
    mutated_route_removed = (
        '@router.websocket("/ws/ssh_legacy/{host_id}")\nasync def ssh_terminal_websocket(...):\n    pass\n'
    )
    assert not re.search(
        route_pattern, mutated_route_removed
    ), "the route regex matched text where the route was renamed -- it is not actually pinning anything"

    # The control must exercise the reader the LIVE assertion uses (review).
    # It previously re-tested the `re.search` pattern that the AST reader
    # replaced, so it proved the dead path still worked and said nothing about
    # the replacement -- a contrast pair aimed at the code you removed.
    mutated_prefix_changed = (
        'RouterConfig(\n    name="terminal",\n    module_path="api.terminal",\n    prefix="/terminal-v2",\n)'
    )
    entries, unreadable = entries_in_source(mutated_prefix_changed, origin="<mutated>")
    assert not unreadable, f"the control's own fixture is unreadable: {unreadable}"
    assert dict(entries).get("api.terminal") == "/terminal-v2", (
        "the AST reader did not read the mutated prefix back, so this control is not "
        "exercising the reader the assertion above depends on"
    )
    assert dict(entries).get("api.terminal") != "/api/terminal", (
        "the reader returned the ORIGINAL prefix for a source that declares a changed one "
        "-- the live assertion would pass a renamed route"
    )
