# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Nothing tenant-scoped may be published to the `global` WebSocket channel (#17354).

`api/live_events.py`'s `_authorize_channel` admits **every authenticated client**
to `global`. Its comment used to assert, as a property, that the channel "carries
no per-tenant payload of its own". It was not a property: `api/workflow.py` had
seven publishes on it carrying an operator's `user_input`, a workflow's
`user_message`, step descriptions and error text, so every signed-in client
received them. Those moved to `workflow:{id}`, which is gated on `view`
permission by `_authorize_resource_channel`.

A comment cannot hold an invariant that any call site can break, so this is the
requirement stated as a test.

What this guard can and cannot see, stated because the gap is large:

- It reads **literal dict payloads**. `publish("global", event, {"task_id": ...})`
  is visible.
- It cannot read a payload passed as a variable —
  `publish("global", event_name, data)` in `api/agent.py:197`,
  `chat_workflow/cot_events.py:201` and nine others. Those are counted, not
  inspected, and `_MAX_OPAQUE_GLOBAL_PUBLISHES` is a ratchet so the blind spot
  cannot grow quietly. Lowering it is the only legal direction.

Mutation check: put `"user_input"` into any `global` publish's literal payload
and `test_no_new_global_publish_carries_a_tenant_key` goes red naming the file
and line; move one of the baselined sites off `global` without deleting its
entry and `test_the_baseline_has_no_stale_entries` goes red.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_BACKEND = repo_root() / "autobot-backend"

#: The two spellings that reach the event bus.
_PUBLISH_NAMES = {"publish", "publish_event"}

#: Keys that name one tenant's content or one tenant's resource. Deliberately
#: narrower than "anything that looks private": `message`, `output`, `result`
#: and `error` are status strings as often as they are content, and a guard that
#: flags them teaches people to route around it. These seven do not have an
#: innocent reading on a channel every authenticated client receives.
_TENANT_KEYS = frozenset({"user_input", "user_message", "session_id", "task_id", "workflow_id", "step_id", "goal"})

#: A floor, not a census: if the walk stops finding `global` publishes at all,
#: every assertion here would pass by matching nothing.
_MIN_GLOBAL_PUBLISHES_SEEN = 15

#: Publishes to `global` whose payload is a variable, so no literal scan can see
#: inside it. Counted rather than inspected. **This may only SHRINK** -- scoping
#: one of them, or making its payload a literal, lowers the number.
#: `api/agent.py:197` is the widest: a helper that hardcodes `"global"`, so none
#: of its callers can scope itself.
_MAX_OPAQUE_GLOBAL_PUBLISHES = 11

#: Pre-existing literal offenders, recorded so this guard blocks NEW ones today
#: rather than waiting for a 6-site campaign. Each is a `task_id` or
#: `workflow_id` on a channel every authenticated client receives; none carries
#: free text, which is why they are baselined rather than fixed here with the
#: `user_input` disclosure that prompted #17354.
#:
#: This list may only SHRINK -- `test_the_baseline_has_no_stale_entries` fails
#: when an entry stops offending, so a fix cannot leave its record behind.
_KNOWN_TENANT_KEYS_ON_GLOBAL = frozenset(
    {
        "diagnostics.py:157",
        "orchestration/workflow_runner.py:691",
        "task_handlers/communication_handlers.py:54",
        "task_handlers/communication_handlers.py:83",
        "worker_node.py:389",
        "worker_node.py:405",
    }
)


def _is_global_publish(node: ast.AST) -> bool:
    if not isinstance(node, ast.Call) or not node.args:
        return False
    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
    if name not in _PUBLISH_NAMES:
        return False
    first = node.args[0]
    return isinstance(first, ast.Constant) and first.value == "global"


def _scan() -> tuple[list[str], int, int]:
    """(literal offenders, opaque count, total `global` publishes seen)."""
    offenders: list[str] = []
    opaque = 0
    seen = 0
    for path in sorted(_BACKEND.rglob("*.py")):
        posix = path.as_posix()
        if "/tests/" in posix or path.name.endswith("_test.py"):
            continue
        try:
            tree = ast.parse(path.read_text(encoding="utf-8"))
        except (SyntaxError, UnicodeDecodeError):
            continue
        for node in ast.walk(tree):
            if not _is_global_publish(node):
                continue
            seen += 1
            where = f"{path.relative_to(_BACKEND).as_posix()}:{node.lineno}"
            payload = node.args[2] if len(node.args) > 2 else None
            if not isinstance(payload, ast.Dict):
                opaque += 1
                continue
            keys = {k.value for k in payload.keys if isinstance(k, ast.Constant)}
            if keys & _TENANT_KEYS:
                offenders.append(f"{where} {sorted(keys & _TENANT_KEYS)}")
    return offenders, opaque, seen


def test_the_scan_reaches_the_publishes_it_guards() -> None:
    """A walk that matches nothing would make every assertion below vacuous."""
    _, _, seen = _scan()

    assert seen >= _MIN_GLOBAL_PUBLISHES_SEEN, (
        f"only {seen} publish(es) to the 'global' channel were found under "
        f"{_BACKEND.name}/, expected at least {_MIN_GLOBAL_PUBLISHES_SEEN} -- this guard has "
        "stopped reaching its subject, so its verdict means nothing"
    )


def test_no_new_global_publish_carries_a_tenant_key() -> None:
    """#17354: `global` reaches every authenticated client."""
    offenders, _, _ = _scan()
    new = sorted(o for o in offenders if o.split(" ")[0] not in _KNOWN_TENANT_KEYS_ON_GLOBAL)

    assert not new, (
        "publish(es) to the 'global' channel carrying a tenant-scoped key (#17354).\n  "
        + "\n  ".join(new)
        + "\n\n'global' is authorized for every authenticated client "
        "(api/live_events.py, _authorize_channel). Publish to the resource's own channel "
        "instead -- 'workflow:{id}', 'agent:{id}' and 'session:{id}' each have an owner check "
        "in _authorize_resource_channel / _authorize_conversation_channel."
    )


def test_the_baseline_has_no_stale_entries() -> None:
    """A fixed site must leave the baseline, so the record only shrinks."""
    offenders, _, _ = _scan()
    still_offending = {o.split(" ")[0] for o in offenders}
    stale = sorted(_KNOWN_TENANT_KEYS_ON_GLOBAL - still_offending)

    assert not stale, (
        "these baseline entries no longer publish a tenant key to 'global' -- delete them "
        "so the record cannot drift back upward (#17354):\n  " + "\n  ".join(stale)
    )


def test_the_opaque_publish_count_only_shrinks() -> None:
    """The guard's own blind spot, ratcheted rather than described.

    A payload passed as a variable cannot be inspected here. Counting them means
    a new one is at least visible as a number, which is the difference between a
    known gap and a growing one.
    """
    _, opaque, _ = _scan()

    assert opaque <= _MAX_OPAQUE_GLOBAL_PUBLISHES, (
        f"{opaque} publishes to 'global' pass an opaque payload, up from "
        f"{_MAX_OPAQUE_GLOBAL_PUBLISHES}. This guard cannot see inside them, so each new one is "
        "an unreviewable broadcast. Either pass a literal payload or publish to a scoped "
        "channel; do not raise this number."
    )
