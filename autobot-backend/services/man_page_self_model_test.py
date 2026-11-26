# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Man-page facts link to the self-model's command entities and follow them into staleness (#22272, #22299)."""

import asyncio
from unittest.mock import AsyncMock, patch

from autobot_shared.self_model_keys import command_key, entity_key
from knowledge.stale_marker import STALE_FIELD, demote_stale
from services import man_page_self_model as mod

HOST = "10.0.0.5"
NODE = "node-redis"


class _Kb:
    """A knowledge base holding facts; ``update_fact`` merges metadata like the real one."""

    def __init__(self, facts):
        self.facts = facts

    async def update_fact(self, fact_id, metadata=None):
        self.facts[fact_id]["metadata"].update(metadata)
        return {"status": "success"}


async def _iter(facts, **_):
    yield [{"fact_id": fid, **fact} for fid, fact in facts.items()]


def _fact(command, **extra):
    return {"metadata": {"type": "man_page", "command": command, "machine_ip": HOST, **extra}}


def _reconcile(facts, unavailable):
    """One ``self_model.changed`` pass with the model holding *unavailable* ``{command: status}`` on the node."""
    rows = {"absent": [], "stale": []}
    for command, status in unavailable.items():
        rows[status].append({"entity_key": command_key(NODE, command), "status": status})

    async def query(filters):
        return {"total": len(rows[filters["status"]]), "entities": rows[filters["status"]]}

    with (
        patch.object(mod, "query_entities", query),
        patch.object(mod, "iter_facts", lambda **kw: _iter(facts, **kw)),
        patch.object(mod, "node_ids_for_hosts", AsyncMock(return_value={HOST: NODE})),
    ):
        return asyncio.run(mod.reconcile_staleness(_Kb(facts)))


def test_the_link_is_the_key_the_slm_computes_under_the_hosts_node_id():
    assert mod.link_fields(NODE, "LS ") == {
        mod.NODE_FIELD: NODE,
        mod.KEY_FIELD: entity_key("command", "ls", entity_key("node", NODE)),
    }
    assert mod.link_fields(None, "ls") == {}


def test_a_host_maps_to_its_node_id_through_the_slm_and_an_unreachable_slm_leaves_it_unlinked():
    with patch.object(mod, "node_ids_for_hosts", AsyncMock(return_value={HOST: NODE})) as ids:
        assert asyncio.run(mod.host_node_id(HOST)) == NODE
        ids.assert_awaited_once_with([HOST])
    with patch.object(mod, "node_ids_for_hosts", AsyncMock(side_effect=mod.SelfModelUnavailable("no client"))):
        assert asyncio.run(mod.host_node_id(HOST)) is None


def test_removing_a_command_marks_its_fact_and_reinstalling_clears_the_mark_without_deleting_it():
    facts = {"f1": _fact("xdotool"), "f2": _fact("ls")}
    counts = _reconcile(facts, {"xdotool": "absent"})
    assert facts["f1"]["metadata"][STALE_FIELD] == "absent" and not facts["f2"]["metadata"].get(STALE_FIELD)
    assert counts["updated"] == 2 and counts["failed"] == 0  # f1 marked, f2 only gained its link
    assert facts["f1"]["metadata"][mod.KEY_FIELD] == command_key(NODE, "xdotool")
    _reconcile(facts, {})  # the command is installed again
    assert not facts["f1"]["metadata"][STALE_FIELD] and set(facts) == {"f1", "f2"}


def test_a_stale_command_marks_its_fact_and_a_fact_on_another_host_is_left_alone():
    other = _fact("ls", machine_ip="10.0.0.9")
    facts = {"f1": _fact("ls"), "f2": other}
    _reconcile(facts, {"ls": "stale"})
    assert facts["f1"]["metadata"][STALE_FIELD] == "stale"
    assert STALE_FIELD not in other["metadata"]


def test_a_marked_fact_ranks_below_an_unmarked_one():
    current = {"metadata": {"command": "ls"}}
    marked = {"metadata": {"command": "ls", STALE_FIELD: "absent"}}
    assert demote_stale(0.8, marked) < demote_stale(0.8, current) == 0.8
