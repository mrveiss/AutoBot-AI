# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Per-model token pricing (#15908).

Extracted from ``ssot_constants`` rather than grown there. That module is
grandfathered at its recorded size (#14236) and the exemption freezes the size
it was granted for -- and this table is the part that keeps growing: 22 model
constants are still unpriced, and #15860 was two of them going unnoticed.

**Absence from this table means unpriced, not free.** Every local model carries
an explicit zero entry, which is what lets ``BudgetService.ingest_cost_event``
treat a missing model as an error rather than as a cost of zero. Pricing a free
model by omitting it would reintroduce #15860 silently.

Imports flow one way: this module reads the model-name constants from
``ssot_constants`` and nothing there imports back. A re-export would have been
convenient and **circular** -- the table is keyed on names defined there, so the
two modules would import each other and fail on first import either way. That is
the durable reason for having none. (A re-export here would also be deleted by
the auto-formatter, since it reads as an unused import -- #15911 -- but that is
contingent on a bot's configuration, and the cycle is not.) The importers were
repointed instead.

**This is the only literal table of model prices in the repository.** It was
not, until #15912: ``MODEL_COSTS_PER_1M_TOKENS`` (13 entries, same unit, same
schema) and ``MODEL_PRICING_PER_1K_TOKENS`` (10 entries, different unit) sat in
``ssot_constants`` beside where this one used to be. Both are now comprehensions
over this table, defined below. A comprehension cannot drift; two literals can,
and had:

* ``PER_1K`` priced ``gpt-4o`` at 5.00/15.00 per 1M against 2.50/10.00 here, and
  ``gpt-3.5-turbo`` at 1.50/2.00 against 0.50/1.50. Stale, plausible, and the
  only table its consumers read.
* ``llm_shared/pricing/deepseek_source.py`` charged 0.55/2.19 against the model
  id ``deepseek-r1`` -- which is ``LOCAL_DEEPSEEK_R1``, priced 0.0/0.0 here as a
  locally-hosted model. One string, two meanings, depending on which table you
  reached for.

Five provider baselines remain in ``llm_shared/pricing/`` and are **not**
derived: they exist as a fallback for when a provider's pricing API is
unreachable, and carry provider-specific fields this table does not. They are
held in step by ``repo_tests/model_pricing_tables_agree_15912_test.py``, which
discovers pricing tables by *shape* rather than by name -- a search for the four
baselines that named this module found four, and there are five. Nothing pointed
at ``vertexai_source.py``.

Before #15910 the three dict tables sat in one file, so anyone editing a price
saw all of them. Proximity was the whole mechanism, and extracting this table
removed it. The guard is what replaces it.

"""

from typing import Dict

from autobot_shared.ssot_constants import (
    ANTHROPIC_CLAUDE3_HAIKU,
    ANTHROPIC_CLAUDE3_HAIKU_DATED,
    ANTHROPIC_CLAUDE3_OPUS,
    ANTHROPIC_CLAUDE3_OPUS_DATED,
    ANTHROPIC_CLAUDE3_SONNET,
    ANTHROPIC_CLAUDE3_SONNET_DATED,
    ANTHROPIC_CLAUDE35_HAIKU,
    ANTHROPIC_CLAUDE35_SONNET,
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE_OPUS4,
    ANTHROPIC_CLAUDE_OPUS4_6,
    ANTHROPIC_CLAUDE_SONNET4,
    ANTHROPIC_CLAUDE_SONNET4_6,
    ANTHROPIC_CLAUDE_SONNET4_SHORT,
    DEEPSEEK_R1_API,
    DEEPSEEK_V3,
    GOOGLE_GEMINI15_FLASH,
    GOOGLE_GEMINI15_PRO,
    GOOGLE_GEMINI20_FLASH,
    GOOGLE_GEMINI25_FLASH,
    GOOGLE_GEMINI25_PRO,
    LOCAL_CODELLAMA,
    LOCAL_DEEPSEEK_CODER,
    LOCAL_DEEPSEEK_R1,
    LOCAL_GEMMA2,
    LOCAL_GEMMA3,
    LOCAL_LLAMA3,
    LOCAL_LLAMA31,
    LOCAL_LLAMA32,
    LOCAL_LLAMA33,
    LOCAL_MISTRAL,
    LOCAL_MIXTRAL,
    LOCAL_PHI3,
    LOCAL_PHI4,
    LOCAL_QWEN3,
    LOCAL_QWEN25,
    OPENAI_GPT4,
    OPENAI_GPT4_TURBO,
    OPENAI_GPT4O,
    OPENAI_GPT4O_MINI,
    OPENAI_GPT35_TURBO,
    OPENAI_GPT41,
    OPENAI_GPT41_MINI,
    OPENAI_GPT41_NANO,
    OPENAI_O1,
    OPENAI_O1_MINI,
    OPENAI_O3,
    OPENAI_O3_MINI,
    OPENAI_O4_MINI,
)

MODEL_PRICING_PER_1M_TOKENS: Dict[str, Dict[str, float]] = {
    ANTHROPIC_CLAUDE_OPUS4: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE_HAIKU4_5: {"input": 0.80, "output": 4.00},
    ANTHROPIC_CLAUDE_SONNET4: {"input": 3.00, "output": 15.00},
    # #15860: the Anthropic provider default (see the default_model fallback in
    # llm_shared/providers/anthropic.py) and the model LLC hires agents on
    # (SONNET_MODEL in llc/api/agent_hires.py). Absent from this table, so every
    # cost event for it resolved to zero and dollar budgets never accrued for the
    # model almost everything runs on. Priced at the Sonnet 4 tier.
    ANTHROPIC_CLAUDE_SONNET4_6: {"input": 3.00, "output": 15.00},
    # The same omission, and the expensive half of it.
    ANTHROPIC_CLAUDE_OPUS4_6: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE35_SONNET: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE35_HAIKU: {"input": 0.80, "output": 4.00},
    ANTHROPIC_CLAUDE3_OPUS_DATED: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE3_SONNET_DATED: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE3_HAIKU_DATED: {"input": 0.25, "output": 1.25},
    OPENAI_GPT41: {"input": 2.00, "output": 8.00},
    OPENAI_GPT41_MINI: {"input": 0.40, "output": 1.60},
    OPENAI_GPT41_NANO: {"input": 0.10, "output": 0.40},
    OPENAI_GPT4O: {"input": 2.50, "output": 10.00},
    OPENAI_GPT4O_MINI: {"input": 0.15, "output": 0.60},
    OPENAI_GPT4_TURBO: {"input": 10.00, "output": 30.00},
    OPENAI_GPT4: {"input": 30.00, "output": 60.00},
    OPENAI_GPT35_TURBO: {"input": 0.50, "output": 1.50},
    OPENAI_O1: {"input": 15.00, "output": 60.00},
    OPENAI_O1_MINI: {"input": 3.00, "output": 12.00},
    OPENAI_O3: {"input": 2.00, "output": 8.00},
    OPENAI_O3_MINI: {"input": 1.10, "output": 4.40},
    OPENAI_O4_MINI: {"input": 1.10, "output": 4.40},
    GOOGLE_GEMINI25_PRO: {"input": 1.25, "output": 5.00},
    GOOGLE_GEMINI25_FLASH: {"input": 0.075, "output": 0.30},
    GOOGLE_GEMINI20_FLASH: {"input": 0.075, "output": 0.30},
    GOOGLE_GEMINI15_PRO: {"input": 1.25, "output": 5.00},
    GOOGLE_GEMINI15_FLASH: {"input": 0.075, "output": 0.30},
    DEEPSEEK_V3: {"input": 0.27, "output": 1.10},
    DEEPSEEK_R1_API: {"input": 0.55, "output": 2.19},
    LOCAL_LLAMA3: {"input": 0.0, "output": 0.0},
    LOCAL_LLAMA31: {"input": 0.0, "output": 0.0},
    LOCAL_LLAMA32: {"input": 0.0, "output": 0.0},
    LOCAL_LLAMA33: {"input": 0.0, "output": 0.0},
    LOCAL_MISTRAL: {"input": 0.0, "output": 0.0},
    LOCAL_MIXTRAL: {"input": 0.0, "output": 0.0},
    LOCAL_CODELLAMA: {"input": 0.0, "output": 0.0},
    LOCAL_QWEN25: {"input": 0.0, "output": 0.0},
    LOCAL_QWEN3: {"input": 0.0, "output": 0.0},
    LOCAL_DEEPSEEK_CODER: {"input": 0.0, "output": 0.0},
    LOCAL_DEEPSEEK_R1: {"input": 0.0, "output": 0.0},
    LOCAL_PHI3: {"input": 0.0, "output": 0.0},
    LOCAL_PHI4: {"input": 0.0, "output": 0.0},
    LOCAL_GEMMA2: {"input": 0.0, "output": 0.0},
    LOCAL_GEMMA3: {"input": 0.0, "output": 0.0},
    # #15912: folded in from `MODEL_COSTS_PER_1M_TOKENS`, which is now a view over
    # this table. These are undated aliases of models already priced above --
    # `claude-3-opus` for `claude-3-opus-20240229`, and so on. Both spellings are
    # in use by callers, and both must resolve, so both are keys.
    #
    # An alias pair is invisible to a table-vs-table comparison, which keys on
    # the id string: `claude-sonnet-4` and `claude-sonnet-4-20250514` are
    # different strings and would never be compared to each other.
    #
    # That is checked, not mitigated by layout. An earlier version of this
    # comment claimed "keeping them adjacent is the whole mitigation" and was
    # wrong twice: these sit ~60 lines from the twins they would drift from, and
    # proximity is the mechanism #15912 exists because it failed. See
    # `alias_pairs()` in the guard, which derives the pairing from the
    # `_DATED`/`_SHORT` naming convention.
    ANTHROPIC_CLAUDE3_OPUS: {"input": 15.00, "output": 75.00},
    ANTHROPIC_CLAUDE3_SONNET: {"input": 3.00, "output": 15.00},
    ANTHROPIC_CLAUDE3_HAIKU: {"input": 0.25, "output": 1.25},
    ANTHROPIC_CLAUDE_SONNET4_SHORT: {"input": 3.00, "output": 15.00},
}


#: Per-1K view. **Derived, never written.** `MODEL_PRICING_PER_1K_TOKENS` used to
#: be a second literal in `ssot_constants`, and it had drifted: `gpt-4o` at
#: 5.00/15.00 against 2.50/10.00 everywhere else, `gpt-3.5-turbo` at 1.50/2.00
#: against 0.50/1.50. Nobody had reason to look -- the numbers were plausible and
#: the table was the only one its consumers read. A comprehension cannot drift;
#: two literals can, and did (#15912).
#:
#: The key rename lives here, visibly, rather than in a reader's head.
MODEL_PRICING_PER_1K_TOKENS: Dict[str, Dict[str, float]] = {
    model: {"prompt": price["input"] / 1000, "completion": price["output"] / 1000}
    for model, price in MODEL_PRICING_PER_1M_TOKENS.items()
}

#: Two entries that are not models and so cannot be derived from a table of
#: models. `TokenTracker.track_usage` reads `"default"` as its fallback when a
#: model is unknown, so dropping it would silently make every unknown model free.
MODEL_PRICING_PER_1K_TOKENS.update(
    {
        "ollama": {"prompt": 0.0, "completion": 0.0},
        "default": {"prompt": 0.001, "completion": 0.002},
    }
)

#: Per-1M view under the older name. **Derived, never written.** Was a 13-entry
#: literal in `ssot_constants` with the same unit and schema as the table above,
#: overlapping it on nine models and agreeing with it only because somebody kept
#: them agreeing by hand (#15912).
MODEL_COSTS_PER_1M_TOKENS: Dict[str, Dict[str, float]] = MODEL_PRICING_PER_1M_TOKENS
