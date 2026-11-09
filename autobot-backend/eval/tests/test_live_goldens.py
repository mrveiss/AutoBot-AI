# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The shipped goldens must tell a good answer from a bad one (#20843).

For every golden, a canned refusal, an echo of the prompt and a too-short answer each FAIL, and a good answer
PASSES. Each goes through the real candidate pipeline (criteria evaluator, classifier, allowlist), so a criterion
loosened until it passes anything turns one of these red.
"""

import pytest

from eval.live import LiveChatCandidate, LiveRunRecord, forbidden_tools
from eval.store import load_golden_set

_GOLDENS = {g.trajectory_id: g for g in load_golden_set()}

_GOOD = {
    "code_fix_null_guard": (
        "```python\ndef connect(config):\n    timeout = config.get('timeout', DEFAULT_TIMEOUT)\n"
        "    return open_connection(config['host'], timeout=timeout)\n```\nThe missing key now falls back."
    ),
    "qa_deploy_role": (
        "Open the setup wizard for the SLM, pick the target node and the service role, then run the playbook. "
        "The role is synced from code_source to the node, and the service restarts once the playbook finishes, "
        "so check the node's status page afterwards to confirm it came back healthy."
    ),
    "triage_502_websocket": (
        "The health endpoint is plain HTTP, while a WebSocket needs the proxy to forward the Upgrade and "
        "Connection headers. After a restart, check that the reverse proxy passes both headers and that the "
        "WebSocket worker came back up behind it."
    ),
}
_REFUSAL = "I don't know how to help with that, sorry."
_LONG_REFUSAL = "I don't know. " * 20 + "wizard playbook code_source Upgrade Connection headers websocket"


async def _kb():
    return "populated"


async def _resolve(model):
    return "http://127.0.0.1:11434"


async def _run(golden, **record):
    async def turn(g, model, workspace):
        return LiveRunRecord(**record)

    candidate = LiveChatCandidate(
        ["m"], "ollama", turn_runner=turn, resolve_endpoint=_resolve, resolve_provider=lambda: "ollama", probe_kb=_kb
    )
    await candidate.prepare()
    return await candidate.runner_for("m")(golden)


def _grounded(golden):
    return golden.task_class in {"knowledge_qa", "troubleshooting"}


def test_the_corpus_is_the_three_shipped_goldens():
    assert set(_GOLDENS) == set(_GOOD)


@pytest.mark.asyncio
@pytest.mark.parametrize("tid", sorted(_GOOD))
async def test_a_good_answer_passes(tid):
    golden = _GOLDENS[tid]
    result = await _run(golden, final_text=_GOOD[tid], used_knowledge=_grounded(golden))
    assert result.passed is True, result.criteria_detail
    assert result.failure_categories == []


@pytest.mark.asyncio
@pytest.mark.parametrize("tid", sorted(_GOOD))
@pytest.mark.parametrize("kind", ["refusal", "long_refusal", "prompt_echo", "too_short"])
async def test_a_bad_answer_fails(tid, kind):
    golden = _GOLDENS[tid]
    text = {
        "refusal": _REFUSAL,
        "long_refusal": _LONG_REFUSAL,
        "prompt_echo": golden.query,
        "too_short": "Use the wizard." if tid != "code_fix_null_guard" else "x = c.get('timeout', DEFAULT_TIMEOUT)",
    }[kind]
    result = await _run(golden, final_text=text, used_knowledge=_grounded(golden))
    assert result.passed is False, f"{tid}/{kind} passed: {result.criteria_detail}"


@pytest.mark.asyncio
@pytest.mark.parametrize("tid", ["qa_deploy_role", "triage_502_websocket"])
async def test_a_good_looking_answer_with_no_grounding_fails(tid):
    result = await _run(_GOLDENS[tid], final_text=_GOOD[tid], used_knowledge=False)
    assert result.passed is False and result.failure_categories == ["unsupported_claim"]


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "text",
    [
        "```python\ndef connect(config):\n    # I won't use DEFAULT_TIMEOUT here\n"
        "    return open(config['host'], timeout=config['timeout'])\n```",
        "```python\ndef connect(config):\n    return open(config['host'], timeout=config.get('timeout'))\n```\n"
        "That is the fix I would use.",
    ],
    ids=["mentions-default-without-applying-it", "get-without-a-default"],
)
async def test_the_null_guard_must_actually_apply_the_default(text):
    assert (await _run(_GOLDENS["code_fix_null_guard"], final_text=text)).passed is False


@pytest.mark.asyncio
async def test_the_null_guard_accepts_an_explicit_branch_that_applies_the_default():
    text = (
        "```python\ndef connect(config):\n    if 'timeout' not in config:\n        timeout = DEFAULT_TIMEOUT\n"
        "    else:\n        timeout = config['timeout']\n    return open(config['host'], timeout=timeout)\n```"
    )
    assert (await _run(_GOLDENS["code_fix_null_guard"], final_text=text)).passed is True


@pytest.mark.asyncio
async def test_calling_any_tool_fails_a_golden_that_allows_none():
    golden = _GOLDENS["code_fix_null_guard"]
    result = await _run(golden, final_text=_GOOD[golden.trajectory_id], tool_sequence=["execute_command"])
    assert result.passed is False and "forbidden_tool: execute_command" in result.criteria_detail
    assert "forbidden_tool" in result.failure_categories  # so the per-model histogram counts it


def test_the_allowlist_is_expected_tools_plus_allowed_tools_and_empty_by_default():
    golden = _GOLDENS["qa_deploy_role"]
    record = LiveRunRecord(tool_sequence=["web_search", "web_search", "read_file"])
    assert forbidden_tools(golden, record) == ["web_search", "read_file"]
    golden.allowed_tools = ["web_search"]
    try:
        assert forbidden_tools(golden, record) == ["read_file"]
    finally:
        golden.allowed_tools = []


_PARAPHRASE = (
    "Use the SLM's guided setup page: choose the node and the role, then kick off the Ansible run. The code is "
    "synced from the code source onto the node and the service is restarted afterwards, so verify the node "
    "reports healthy once it is back."
)


@pytest.mark.asyncio
async def test_a_correct_paraphrase_of_the_deploy_answer_passes_without_the_exact_words():
    result = await _run(_GOLDENS["qa_deploy_role"], final_text=_PARAPHRASE, used_knowledge=True)
    assert result.passed is True, result.criteria_detail


@pytest.mark.asyncio
async def test_an_answer_covering_only_one_of_the_three_concepts_still_fails():
    one = (
        "Open the setup wizard on the SLM page and pick the node you want from the list it shows you, then pick "
        "the role from the dropdown and confirm the choice. Afterwards look at the node details to check things."
    )
    assert (await _run(_GOLDENS["qa_deploy_role"], final_text=one, used_knowledge=True)).passed is False


@pytest.mark.asyncio
async def test_one_concept_plus_a_generic_sync_sentence_still_fails():
    generic = (
        "Open the setup page and pick anything; the data will sync to your laptop later. Nothing else is needed, "
        "and you can come back to the page whenever you like to look at what you picked earlier on, at any time."
    )
    assert len(generic) >= 200
    result = await _run(_GOLDENS["qa_deploy_role"], final_text=generic, used_knowledge=True)
    assert result.passed is False
    assert "2 of 3 concepts" in result.criteria_detail
