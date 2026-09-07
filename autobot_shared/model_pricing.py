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
convenient and circular -- the table is keyed on names defined there, so the
two modules would import each other and fail on first import either way. The
five importers were repointed instead.
"""

from typing import Dict

from autobot_shared.ssot_constants import (
    ANTHROPIC_CLAUDE3_HAIKU_DATED,
    ANTHROPIC_CLAUDE3_OPUS_DATED,
    ANTHROPIC_CLAUDE3_SONNET_DATED,
    ANTHROPIC_CLAUDE35_HAIKU,
    ANTHROPIC_CLAUDE35_SONNET,
    ANTHROPIC_CLAUDE_HAIKU4_5,
    ANTHROPIC_CLAUDE_OPUS4,
    ANTHROPIC_CLAUDE_SONNET4,
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
}
