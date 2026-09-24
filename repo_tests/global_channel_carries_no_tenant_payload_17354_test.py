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
  `publish("global", event_name, data)` in `api/agent.py`'s
  `_publish_event_safe`, `chat_workflow/cot_events.py`'s `_try_publish`, and
  nine others. Those are counted, not inspected, and
  `_MAX_OPAQUE_GLOBAL_PUBLISHES` is a ratchet so the blind spot cannot grow
  quietly. Lowering it is the only legal direction.

Mutation check: put `"user_input"` into any `global` publish's literal payload
and `test_no_new_global_publish_carries_a_tenant_key` goes red naming the file
and line; move one of the baselined sites off `global` without deleting its
entry and `test_the_baseline_has_no_stale_entries` goes red.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

_BACKEND = repo_root() / "autobot-backend"

#: The spellings that reach the event bus. `publish_event_safe` is
#: `api/agent_events.py`'s wrapper: its channel is a PARAMETER, so the `publish`
#: call inside it is opaque here, and a call site passing the broadcast constant
#: would have been invisible too (#17354). Matching the wrapper by name keeps the
#: deliberate broadcasts in view -- moving a publish behind a helper must not be
#: a way out of this guard's reach.
_PUBLISH_NAMES = {"publish", "publish_event", "publish_event_safe"}

#: The one name that means "every authenticated client" without saying "global"
#: (`api/agent_events.BROADCAST_CHANNEL`).
_BROADCAST_CONSTANT = "BROADCAST_CHANNEL"

#: `EventBus.publish`, `events.bus.publish_event` and `LiveEventManager.publish`
#: all name their first and third parameters these, so one keyword spelling
#: covers every publisher this guard scans (#17363).
_CHANNEL_PARAM = "channel"
_PAYLOAD_PARAM = "payload"

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
#: `api/agent.py`'s `_publish_event_safe` is the widest: a helper that hardcodes
#: `"global"`, so none of its callers can scope itself.
#:
#: 11 -> 5. Four terminal/command publishes moved to `chat:{id}` and two
#: keyword-spelled payloads stopped counting as opaque once `_argument` could read
#: them (#17363); the alias-aware matcher then added four sites, all with literal
#: payloads, so the count did not move; then #17354's remaining two -- the agent
#: router's `_publish_event_safe` and `cot_events._try_publish`, the two widest
#: helpers, each hardcoding `"global"` for callers that had an owner -- took a
#: channel parameter and left this population entirely.
#:
#: A widening of the matcher re-freezes this number: "only shrinks" holds for a
#: fixed detector, not across a change to what it can see.
_MAX_OPAQUE_GLOBAL_PUBLISHES = 5

#: Pre-existing literal offenders, recorded so this guard blocks NEW ones today
#: rather than waiting for a 6-site campaign. Each is a `task_id` or
#: `workflow_id` on a channel every authenticated client receives; none carries
#: free text, which is why they are baselined rather than fixed here with the
#: `user_input` disclosure that prompted #17354.
#:
#: This list may only SHRINK -- `test_the_baseline_has_no_stale_entries` fails
#: when an entry stops offending, so a fix cannot leave its record behind. The
#: one exception is a widening of the matcher: the last two entries are not new
#: code, they are pre-existing sites the positional-only read could not see
#: (#17363). Both are a human-decision notification -- an approval awaiting a
#: reviewer, a research checkpoint awaiting a decision -- so the fix is an
#: admin/owner-scoped channel plus its frontend subscriber, not a payload trim,
#: and that is #17373 rather than this PR. The three `agent_loop/loop.py` entries
#: arrived the same way -- they publish through the `_bus_publish_event` alias,
#: which the name-only matcher never recognised -- and carry `task_id` only, the
#: same shape as the six original entries.
_KNOWN_TENANT_KEYS_ON_GLOBAL = frozenset(
    {
        "diagnostics.py:157",
        "orchestration/workflow_runner.py:691",
        "task_handlers/communication_handlers.py:54",
        "task_handlers/communication_handlers.py:83",
        "worker_node.py:389",
        "worker_node.py:405",
        "services/approval_gate_service.py:388",
        "services/autoresearch/auto_research_agent.py:1101",
        "agent_loop/loop.py:369",
        "agent_loop/loop.py:654",
        "agent_loop/loop.py:1787",
    }
)


def _argument(node: ast.Call, position: int, keyword: str) -> ast.AST | None:
    """The argument reaching one parameter, positionally or by keyword (#17363).

    A `**kwargs` splat carries `kw.arg is None` and resolves to `None` here, which
    lands it in the opaque bucket -- the safe side.
    """
    if len(node.args) > position:
        return node.args[position]
    for kw in node.keywords:
        if kw.arg == keyword:
            return kw.value
    return None


def _local_publish_names(tree: ast.Module) -> frozenset[str]:
    """`_PUBLISH_NAMES` plus whatever this module renamed them to on import.

    `agent_loop/loop.py:59` and `orchestration/primitives/events.py:20` both do
    `from events.bus import publish_event as _bus_publish_event`, and
    `orchestrator.py:87` renames it again on re-export. Matching the call name
    alone missed four `global` publishes carrying `task_id` (#17363) -- found by
    re-deriving this population with grep after the matcher changed, which is
    what RATCHET_BASELINES.md's rule 3 exists for. Read from the module's own
    imports rather than hardcoded, so the next rename is covered without an edit.
    """
    renamed = {
        alias.asname
        for node in ast.walk(tree)
        if isinstance(node, (ast.Import, ast.ImportFrom))
        for alias in node.names
        if alias.asname and alias.name.rpartition(".")[2] in _PUBLISH_NAMES
    }
    return frozenset(_PUBLISH_NAMES | renamed)


def _is_global_publish(node: ast.AST, names: frozenset[str]) -> bool:
    if not isinstance(node, ast.Call):
        return False
    name = node.func.attr if isinstance(node.func, ast.Attribute) else getattr(node.func, "id", "")
    if name not in names:
        return False
    channel = _argument(node, 0, _CHANNEL_PARAM)
    if isinstance(channel, ast.Constant):
        return channel.value == "global"
    if isinstance(channel, ast.Name):
        return channel.id == _BROADCAST_CONSTANT
    return isinstance(channel, ast.Attribute) and channel.attr == _BROADCAST_CONSTANT


def _scan_source(source: str, label: str) -> tuple[list[str], int, int]:
    """(literal offenders, opaque count, `global` publishes seen) in one module.

    Split out from `_scan` so the fixture tests below exercise the same matcher
    the tree walk uses, rather than a second copy of it.
    """
    offenders: list[str] = []
    opaque = 0
    seen = 0
    tree = ast.parse(source)
    names = _local_publish_names(tree)
    for node in ast.walk(tree):
        if not _is_global_publish(node, names):
            continue
        seen += 1
        where = f"{label}:{node.lineno}"
        payload = _argument(node, 2, _PAYLOAD_PARAM)
        if not isinstance(payload, ast.Dict):
            opaque += 1
            continue
        keys = {k.value for k in payload.keys if isinstance(k, ast.Constant)}
        if keys & _TENANT_KEYS:
            offenders.append(f"{where} {sorted(keys & _TENANT_KEYS)}")
    return offenders, opaque, seen


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
            source = path.read_text(encoding="utf-8")
        except UnicodeDecodeError:
            continue
        try:
            found, module_opaque, module_seen = _scan_source(source, path.relative_to(_BACKEND).as_posix())
        except SyntaxError:
            continue
        offenders.extend(found)
        opaque += module_opaque
        seen += module_seen
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


# --- Fixtures -----------------------------------------------------------------
#
# A tree scan cannot prove the scanner *would* see a keyword-spelled call while
# no such call exists in the tree -- and #17363's hole was exactly a path with no
# live example, which is why it survived review. So the proof is constructed:
# each fixture below is a call shape, run through the same `_scan_source` the
# walk uses. These are what separate "found nothing" from "did not look".

_KEYWORD_PAYLOAD = 'publish_event("global", "x", payload={"task_id": "t1"})\n'
_POSITIONAL_PAYLOAD = 'publish_event("global", "x", {"task_id": "t1"})\n'
_KEYWORD_CHANNEL = 'publish_event(channel="global", event_type="x", payload={"user_input": "secret"})\n'
_KEYWORD_OPAQUE = 'publish_event("global", "x", payload=data)\n'
_KWARGS_SPLAT = 'publish_event("global", "x", **extra)\n'
_CLEAN_PAYLOAD = 'publish_event("global", "x", payload={"count": 3})\n'
_SCOPED_CHANNEL = 'publish_event(f"chat:{cid}", "x", payload={"task_id": "t1"})\n'


def test_a_keyword_payload_is_inspected_not_skipped() -> None:
    """#17363: `payload=` used to resolve to None and bucket as opaque."""
    offenders, opaque, seen = _scan_source(_KEYWORD_PAYLOAD, "fixture.py")

    assert seen == 1
    assert opaque == 0, "a literal payload spelled as a keyword must be inspected, not counted as opaque"
    assert offenders == ["fixture.py:1 ['task_id']"]


def test_a_positional_payload_is_still_inspected() -> None:
    """The path that already worked, asserted so the widening cannot break it."""
    offenders, opaque, _ = _scan_source(_POSITIONAL_PAYLOAD, "fixture.py")

    assert opaque == 0
    assert offenders == ["fixture.py:1 ['task_id']"]


def test_a_keyword_channel_is_not_a_way_past_the_scanner() -> None:
    """`channel="global"` reaches the same parameter as the first argument."""
    offenders, _, seen = _scan_source(_KEYWORD_CHANNEL, "fixture.py")

    assert seen == 1, "a publish whose channel is spelled `channel='global'` must still be scanned"
    assert offenders == ["fixture.py:1 ['user_input']"]


def test_a_payload_passed_by_name_as_a_variable_counts_as_opaque() -> None:
    """Keyword spelling must not turn a variable payload into a clean verdict."""
    offenders, opaque, seen = _scan_source(_KEYWORD_OPAQUE, "fixture.py")

    assert (seen, opaque, offenders) == (1, 1, [])


def test_a_kwargs_splat_counts_as_opaque() -> None:
    """`kw.arg is None` resolves to no payload, which must land on the safe side."""
    _, opaque, seen = _scan_source(_KWARGS_SPLAT, "fixture.py")

    assert (seen, opaque) == (1, 1)


def test_a_payload_without_a_tenant_key_is_not_an_offender() -> None:
    """Negative control: the scanner is not simply flagging every `global` publish."""
    offenders, opaque, seen = _scan_source(_CLEAN_PAYLOAD, "fixture.py")

    assert (seen, opaque, offenders) == (1, 0, [])


def test_a_scoped_channel_is_not_scanned_at_all() -> None:
    """The guard's subject is `global`; a `chat:{id}` publish is out of scope."""
    offenders, opaque, seen = _scan_source(_SCOPED_CHANNEL, "fixture.py")

    assert (seen, opaque, offenders) == (0, 0, [])


_ALIASED_PUBLISH = (
    "from events.bus import publish_event as _bus_publish_event\n"
    '_bus_publish_event("global", "x", {"task_id": "t1"})\n'
)
_ALIASED_UNRELATED = (
    "from other.module import notify as _bus_publish_event\n" '_bus_publish_event("global", "x", {"task_id": "t1"})\n'
)


def test_a_renamed_publish_helper_is_still_scanned() -> None:
    """#17363: `publish_event as _bus_publish_event` hid four `task_id` publishes."""
    offenders, _, seen = _scan_source(_ALIASED_PUBLISH, "fixture.py")

    assert seen == 1, "a publish called through an `import ... as` alias must still be scanned"
    assert offenders == ["fixture.py:2 ['task_id']"]


def test_an_unrelated_function_renamed_to_the_same_alias_is_not_scanned() -> None:
    """The alias set comes from what was imported, not from the local name."""
    _, _, seen = _scan_source(_ALIASED_UNRELATED, "fixture.py")

    assert seen == 0, "the alias must be honoured only when it actually binds a publish helper"


_BROADCAST_CONSTANT_CALL = 'publish_event_safe(BROADCAST_CHANNEL, "x", {"session_id": "s1"})\n'
_BROADCAST_CONSTANT_CLEAN = 'publish_event_safe(BROADCAST_CHANNEL, "x", {"message": "Agent paused."})\n'


def test_the_broadcast_constant_is_scanned_like_the_literal() -> None:
    """A helper's constant must not be a way out of the guard's reach (#17354)."""
    offenders, _, seen = _scan_source(_BROADCAST_CONSTANT_CALL, "fixture.py")

    assert seen == 1, "publishing via BROADCAST_CHANNEL must be scanned like publishing to 'global'"
    assert offenders == ["fixture.py:1 ['session_id']"]


def test_a_deliberate_broadcast_without_tenant_content_stays_clean() -> None:
    """Negative control: the constant is not itself the offence."""
    offenders, opaque, seen = _scan_source(_BROADCAST_CONSTANT_CLEAN, "fixture.py")

    assert (seen, opaque, offenders) == (1, 0, [])
