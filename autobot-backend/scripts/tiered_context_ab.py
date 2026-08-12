#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A/B harness for the tiered L0-L4 context stack (#5066, #13689).

Runs the tiered path against the legacy path over the same prompts and reports,
per path: which layers rendered, the assembled context, its token cost, and the
assembly latency.

Why a committed script rather than a one-off measurement: #13689 exists because
the original A/B left no record, so the next person could not tell an unrun
experiment from a negative result. Re-running this reproduces the numbers in
``docs/research/tiered-context-ab-13689.md``.

Scope is deliberately narrow, per #13689: this measures *what the stack puts in
the prompt* and what that costs. It is not a retrieval-quality benchmark —
recall quality is unmeasurable until #13251/#13243, and expanding this into that
was explicitly ruled out.

The layer data sources are supplied as doubles so the run is deterministic and
needs no live Redis/ChromaDB. That measures assembly, not a deployment; the
distinction is stated in the report rather than papered over.

Usage:
    python3 scripts/tiered_context_ab.py            # human-readable table
    python3 scripts/tiered_context_ab.py --json     # machine-readable
"""

from __future__ import annotations

import argparse
import asyncio
import json
import sys
import time
from pathlib import Path
from typing import Any, Dict, List
from unittest.mock import AsyncMock, MagicMock, patch

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

REPEATS = 20

# Prompts chosen to exercise one trigger each, plus one that fires none.
CASES = [
    {
        "name": "plain",
        "message": "can you help me with this",
        "expects": ["identity", "essential_story"],
    },
    {
        "name": "entity mention (L2)",
        "message": "How does Redis hold sessions?",
        "expects": ["identity", "essential_story", "related_context"],
    },
    {
        "name": "retrieval keyword (L3)",
        "message": "search the kb for the deploy runbook",
        "expects": ["identity", "essential_story", "deep_search"],
    },
    {
        "name": "goal-linked session (L4)",
        "message": "what is the status",
        "expects": ["identity", "essential_story", "goal_ancestry"],
        "goal_ancestry": [
            {"id": "1", "title": "Ship the platform", "level": "vision", "status": "active"},
            {"id": "2", "title": "Wake the context stack", "level": "objective", "status": "active"},
        ],
    },
]

ESSENTIAL_STORY = "## Essential Story\n- the deploy ran at 09:00\n- the owner is mrveiss"
# #13866: this was `{"name": ..., "description": ...}` — a shape no production
# write path produces. The double agreed with the layer's own wrong assumption,
# so the A/B reported L2 rendering when it cannot. The fixture now matches what
# `_build_entity_document` actually stores; L2 will render nothing here until
# #13686 teaches it to read `observations`, and that is the honest result.
ENTITY_FACTS = [
    {
        "id": "ent-redis",
        "type": "service",
        "name": "Redis",
        "created_at": 0,
        "updated_at": 0,
        "observations": ["in-memory store backing session state"],
        "metadata": {},
    }
]
# L3 returns whatever the knowledge service hands back — it adds no heading of
# its own — so the double emits a recognisable grounded-context block.
KB_CONTEXT = "## Knowledge Base\nDeploy runbook: run code-sync from the maintenance page."


def _memory_graph() -> Any:
    graph = MagicMock()
    graph.search_entities = AsyncMock(return_value=ENTITY_FACTS)
    return graph


def _knowledge_service() -> Any:
    """Double for the L3 retrieval seam.

    `Layer3DeepSearch.render` calls `conversation_aware_retrieve` and unpacks a
    4-tuple — not `search`. Getting this wrong is silent: the layer catches the
    resulting TypeError and renders an empty string, which reads exactly like
    "L3 did not fire".
    """
    svc = MagicMock()
    svc.conversation_aware_retrieve = AsyncMock(return_value=(KB_CONTEXT, ["runbook.md"], None, None))
    return svc


def _detect_layers(text: str) -> List[str]:
    """Map rendered headings back to layer names."""
    markers = {
        "## Identity": "identity",
        "## Essential Story": "essential_story",
        "## Related Context": "related_context",
        "## Knowledge": "deep_search",
        "## Goal Ancestry": "goal_ancestry",
    }
    return [name for marker, name in markers.items() if marker in text]


async def _build_tiered(case: Dict[str, Any]) -> str:
    from chat_history.layers import TieredContextBuilder

    with patch("chat_history.layers.TIERED_CONTEXT_ENABLED", True):
        with patch(
            "memory.essential_story.EssentialStoryGenerator.generate",
            new_callable=AsyncMock,
            return_value=ESSENTIAL_STORY,
        ):
            return await TieredContextBuilder().build(
                user_message=case["message"],
                model_name="default",
                session_id="ab-session",
                memory_graph=_memory_graph(),
                # #13866: None, mirroring the production call site
                # (llm_handler.py) since #13742. Passing a mock here reported L3
                # as rendering while production could not render it at all —
                # the same divergence that made the ENTITY_FACTS result false.
                knowledge_service=None,
                goal_ancestry=case.get("goal_ancestry"),
            )


async def _build_legacy(_case: Dict[str, Any]) -> str:
    """The legacy branch: unconditional EssentialStory, nothing else."""
    from memory.essential_story import EssentialStoryGenerator

    with patch(
        "memory.essential_story.EssentialStoryGenerator.generate",
        new_callable=AsyncMock,
        return_value=ESSENTIAL_STORY,
    ):
        return await EssentialStoryGenerator().generate(model_name="default")


async def _timed(fn, case: Dict[str, Any]) -> Dict[str, Any]:
    text = await fn(case)
    start = time.perf_counter()
    for _ in range(REPEATS):
        text = await fn(case)
    elapsed_ms = (time.perf_counter() - start) * 1000 / REPEATS

    from context_window_manager import get_context_window_manager

    return {
        "tokens": get_context_window_manager().estimate_tokens(text),
        "latency_ms": round(elapsed_ms, 3),
        "layers": _detect_layers(text),
        "text": text,
    }


async def run() -> Dict[str, Any]:
    results = []
    for case in CASES:
        tiered = await _timed(_build_tiered, case)
        legacy = await _timed(_build_legacy, case)
        results.append(
            {
                "case": case["name"],
                "message": case["message"],
                "expected_layers": case["expects"],
                "tiered": tiered,
                "legacy": legacy,
                "missing_layers": [layer for layer in case["expects"] if layer not in tiered["layers"]],
            }
        )
    return {"repeats": REPEATS, "results": results}


def _print(report: Dict[str, Any]) -> None:
    print(f"Tiered-context A/B (#13689) — {report['repeats']} repeats per measurement\n")  # noqa: print
    header = f"{'case':<26} {'path':<8} {'tokens':>7} {'ms':>8}  layers"
    print(header)  # noqa: print
    print("-" * len(header))  # noqa: print
    for row in report["results"]:
        for path in ("tiered", "legacy"):
            data = row[path]
            print(  # noqa: print
                f"{row['case'] if path == 'tiered' else '':<26} {path:<8} "
                f"{data['tokens']:>7} {data['latency_ms']:>8.3f}  {', '.join(data['layers']) or '(none)'}"
            )
        if row["missing_layers"]:
            print(f"{'':<26} MISSING: {', '.join(row['missing_layers'])}")  # noqa: print
        print()  # noqa: print


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable JSON")
    args = parser.parse_args()

    report = asyncio.run(run())
    if args.json:
        print(json.dumps(report, indent=2))  # noqa: print
    else:
        _print(report)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
