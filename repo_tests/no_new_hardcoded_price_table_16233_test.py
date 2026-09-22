# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No new hardcoded price table may enter the tree (#16233).

#16230 moved pricing to a live catalogue in Redis. #16233 asks for the thing
that keeps it there: the failure mode is not that the migration was wrong, it
is that six months from now somebody adds a small table "just for this one
provider" and it is plausible, and nobody looks. That is precisely how #15912's
two tables drifted -- `gpt-4o` at 5.00/15.00 against 2.50/10.00, for years,
because the numbers looked fine and the table was the only one its consumers
read.

This is a **census ratchet**, not a ban. Seven literal tables exist and are
named below; the set may shrink and may never grow. A price literal is not
forbidden -- an unreviewed *new* one is.

Discovery is deliberately not reimplemented here: it is
``model_pricing_tables_agree_15912_test.discover_pricing_tables``, which
recognises a table by its shape (``{model: {"input"/"output"}}`` or
``[(model_id, input, output[, cache])]``) rather than by name, so a table added
under any name in any file is covered. Two guards over one sweep also means a
break in the sweep shows up as two failures, not as two silent passes: #15912's
own floor test and this census fail together, and neither can quietly stop
looking while the other reports clean.

Why the five baselines are permitted rather than removed
--------------------------------------------------------

Owner ruling during #16230: the five ``BaselinePricingSource`` tables are wired
in as a last resort (``pricing_refresh._write_baseline_fallback``), reached only
when both live catalogues return nothing **and** the store is empty. Deleting
them would mean a first boot during a vendor outage leaves the store empty, the
sync cache cold, and ``budget.py`` raising ``UnpricedModel`` for every model --
every LLC agent run blocked. A stale price labelled stale beats no price.

They are therefore known, wired, and pinned here by exact path. What this guard
stops is a *sixth* one appearing beside them.

Mutation check: add a two-entry ``{"some-model": {"input": 1.0, "output": 2.0}}``
dict anywhere under a tracked ``.py`` and this goes red naming the file.
"""

from __future__ import annotations

from repo_tests.model_pricing_tables_agree_15912_test import discover_pricing_tables

#: Every literal price table that may exist, by ``path::NAME``. Shrinking is
#: always allowed. Adding an entry is a review decision, and the comment beside
#: it is the record of that decision -- an entry added without one has skipped
#: the only step this guard is.
_PERMITTED = {
    # The canonical table. Every derived view is a comprehension over it
    # (#15912), so this is the one place a real model price is written.
    "autobot_shared/model_pricing.py::MODEL_PRICING_PER_1M_TOKENS",
    # The five provider baselines. Wired as the last-resort fallback by #16230
    # per owner ruling; see this module's docstring.
    "autobot-backend/llm_shared/pricing/anthropic_source.py::_BASELINE",
    "autobot-backend/llm_shared/pricing/openai_source.py::_BASELINE",
    "autobot-backend/llm_shared/pricing/google_source.py::_BASELINE",
    "autobot-backend/llm_shared/pricing/deepseek_source.py::_BASELINE",
    "autobot-backend/llm_shared/pricing/vertexai_source.py::_BASELINE",
    # Not models: "ollama" and "default", the estimate rates the cost
    # projection falls back to. Shape-matched by the sweep because the sweep
    # matches on shape; kept visible rather than renamed out of its way.
    "autobot-backend/code_intelligence/llm_pattern_analysis/calculators.py::_NON_MODEL_RATES_PER_1K",
}


def test_the_sweep_still_finds_the_permitted_tables() -> None:
    """Runs first: an empty sweep would make the census below pass over nothing.

    The census asserts ``found - permitted == set()``. A sweep that broke and
    returned nothing satisfies that perfectly, and would report "no new
    hardcoded price tables" while being unable to see any at all -- the exact
    shape of false clean this file is here to prevent one level down.
    """
    found = set(discover_pricing_tables())
    missing = _PERMITTED - found

    assert not missing, (
        "the sweep no longer finds table(s) this census knows exist:\n  "
        + "\n  ".join(sorted(missing))
        + "\n\nIf they were genuinely removed, delete them from _PERMITTED in the same commit "
        "and say so. If they still exist, discover_pricing_tables() has stopped seeing them and "
        "this guard is blind — FIX THE SWEEP, do not adjust the census."
    )


def test_no_price_table_exists_outside_the_permitted_set() -> None:
    new = sorted(set(discover_pricing_tables()) - _PERMITTED)

    assert not new, (
        "hardcoded price table(s) added outside the permitted set (#16233):\n  "
        + "\n  ".join(new)
        + "\n\nPricing is runtime state read from the live catalogue via "
        "`llm_shared.pricing.sync_cache` (#16229, #16230). A literal table is read by whoever "
        "imports it and by nobody else, cannot be refreshed, and goes stale without saying so — "
        "#15912 found two that had disagreed for years because the numbers looked plausible.\n\n"
        "Write the price to `PricingRedisStore` (an operator override, or a source in "
        "`pricing_refresh._build_sources`) instead. If a literal really is the only option, add it "
        "to _PERMITTED in this file with the reason — that edit is the review."
    )
