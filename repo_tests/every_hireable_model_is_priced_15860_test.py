# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Every model an agent can actually run on has a price (#15860).

`MODEL_PRICING_PER_1M_TOKENS` did not contain `claude-sonnet-4-6` — the
Anthropic provider's default and the model LLC hires agents on. `ingest_cost_event`
treated an unpriced model as free, so `budget_spent` never moved and dollar-mode
enforcement did not apply to the model almost everything runs on.

**The table is not required to price every constant.** 22 model constants in
`ssot_constants.py` have no entry, and most are unreachable — a provider nobody
configures, a dated alias nothing selects. Demanding all of them would be a
larger claim than the defect supports and would fail on models that genuinely
do not matter.

What must hold is narrower and checkable: **a model something can be hired or
defaulted onto must be priced.** Those are read from the modules that name
them, not restated here, so a new default that nobody prices fails this.
"""

import ast
import re
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
_HIRES = REPO_ROOT / "autobot-backend/llc/api/agent_hires.py"
_CONSTANTS = REPO_ROOT / "autobot_shared/ssot_constants.py"
_PRICING = REPO_ROOT / "autobot_shared/model_pricing.py"


def priced_models() -> set[str]:
    """The literal model strings priced in MODEL_PRICING_PER_1M_TOKENS.

    Resolved through the constants they are keyed by: the table maps
    `ANTHROPIC_CLAUDE_SONNET4_6` -> price, and that constant holds the wire
    string. Reading only the key names would compare identifiers to model
    strings and pass on nothing.
    """
    source = _CONSTANTS.read_text(encoding="utf-8")
    names = dict(
        re.findall(
            r'^(\w+(?:CLAUDE|GPT|GEMINI|LLAMA|MISTRAL|QWEN|PHI|GEMMA|DEEPSEEK)\w*)\s*[:=][^=\n]*?"([^"]+)"',
            source,
            re.M,
        )
    )

    # The names still live in ssot_constants; the table moved to model_pricing
    # (#15860's extraction). Reading both from one file finds no table at all.
    table_source = _PRICING.read_text(encoding="utf-8")
    start = table_source.index("MODEL_PRICING_PER_1M_TOKENS")
    block = table_source[start : table_source.index("\n}", start)]
    keys = set(re.findall(r"^\s*(\w+):", block, re.M))

    resolved = {names[k] for k in keys if k in names}
    assert resolved, "no priced model resolved to a wire string — the table's shape changed"
    return resolved


def hireable_models() -> dict[str, str]:
    """Model strings an LLC agent can be hired on, read from `agent_hires`."""
    tree = ast.parse(_HIRES.read_text(encoding="utf-8"))
    found = {}
    for node in tree.body:
        if not isinstance(node, ast.Assign):
            continue
        for target in node.targets:
            if isinstance(target, ast.Name) and target.id.endswith("_MODEL"):
                if isinstance(node.value, ast.Constant) and isinstance(node.value.value, str):
                    found[target.id] = node.value.value
    assert found, "no *_MODEL constants found in agent_hires.py — this test would prove nothing"
    return found


def test_every_hireable_model_is_priced():
    """The defect: LLC hires on `claude-sonnet-4-6`, which had no price."""
    priced = priced_models()
    unpriced = {name: model for name, model in hireable_models().items() if model not in priced}

    assert not unpriced, (
        "these models can be hired but have no entry in MODEL_PRICING_PER_1M_TOKENS, "
        f"so every cost event for them accrues nothing: {unpriced}"
    )


def test_the_sweep_resolved_a_plausible_number_of_prices():
    """Reach floor, bound to what was read rather than to what was found.

    Both sides are extracted by pattern. If either extractor silently matched
    nothing, `unpriced` above would be empty and the test would pass having
    compared two empty sets.
    """
    assert len(priced_models()) >= 20, f"only {len(priced_models())} priced models resolved"
    assert len(hireable_models()) >= 2, "fewer hireable models than agent_hires defines"


def test_a_model_absent_from_the_table_is_detected():
    """Contrast case: the comparison must be able to report a miss.

    Without this, `test_every_hireable_model_is_priced` is indistinguishable
    from one whose `unpriced` is empty for the wrong reason.
    """
    priced = priced_models()
    assert "a-model-nobody-priced" not in priced
    fake = {"FAKE_MODEL": "a-model-nobody-priced"}
    assert {n: m for n, m in fake.items() if m not in priced} == fake
