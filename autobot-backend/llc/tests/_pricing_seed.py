# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Warm `sync_cache` for tests that ingest a cost event (#16230).

Pricing used to come from a static table: always present, no setup. It now comes
from `llm_shared.pricing.sync_cache`'s in-memory mirror, populated by a
background scheduler that minimal-mount LLC tests never start — no network, no
Redis. Left cold, `BudgetService.ingest_cost_event` raises `UnpricedModel`
rather than recording a cost, which is correct behaviour and a broken test.

Shared rather than copied: two test modules needed the identical fixture, and a
third will. The seeded price is a *parameter*, not a constant here — a module
asserting on a resulting dollar figure has to own the number it asserts on.
"""

from __future__ import annotations

import time
from contextlib import contextmanager
from typing import Iterator


@contextmanager
def seeded_pricing_cache(model_id: str, input_per_1m: float, output_per_1m: float) -> Iterator[None]:
    """Install one price in the process-local mirror, and take it back out after.

    Torn down to *cold*, not to some previous value: the mirror is a module
    global shared by every caller in the process, so a test that left a price
    behind would hand the next one a catalogue it never asked for.
    """
    from llm_shared.pricing import sync_cache
    from llm_shared.pricing.sources import ModelPricing

    price = ModelPricing(
        provider="test",
        model_id=model_id,
        input_per_1m=input_per_1m,
        output_per_1m=output_per_1m,
    )
    sync_cache._snapshot = sync_cache._Snapshot(prices={model_id: price}, fetched_at=time.monotonic())
    try:
        yield
    finally:
        sync_cache._reset_for_tests()
