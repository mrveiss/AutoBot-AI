# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Research-quarantine KB search filter (#12622, #12623, #13009).

``ResearchOrchestrator`` (#12622) lands web-research findings as KB facts
tagged ``metadata.collection == config.research_quarantine_collection``.
Those facts are quarantined -- invisible to every general-purpose chat/RAG
read -- until the corroboration + promotion gate (#12623) reviews them and
flips that metadata field.

``async_chat_workflow.py::_execute_kb_search`` was the first call site fixed
(#12622). #13009 audited every other ``kb.search()`` call site reachable
from a general-purpose surface and found several more with the same gap;
this module is the single shared filter so the exclusion is defined once
instead of copy-pasted at each call site.

The ``$ne`` operator also matches facts that predate the ``collection``
field entirely (no key at all) -- verified against the installed ChromaDB
(#12622) and against ``knowledge.backends.memory_adapter.InMemoryCollection``
(#12623), so pre-existing facts stay visible.

Research-internal readers (the corroboration/promotion gate itself --
``services/claim_verifier.py``, ``services/research/orchestrator.py``,
``services/research/planner.py``) must NOT use this filter: they exist to
read the quarantine collection.
"""

from autobot_shared.ssot_config import config

# Module-level constant (not a function): the filter is a static dict, cheap
# to import and share; no per-call construction needed.
RESEARCH_QUARANTINE_FILTER: dict = {"collection": {"$ne": config.research_quarantine_collection}}
