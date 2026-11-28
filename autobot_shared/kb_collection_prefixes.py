# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Canonical LLC KB collection name prefixes (#20945).

The one definition; ``llc.kb.collections.KbCollectionManager`` re-exposes these. Kept free of imports so a
parser (e.g. knowledge-graph bucket visibility) can use them without pulling in the KB stack.
"""

COMPANY_PREFIX = "company"
PROJECT_PREFIX = "project"
SPRINT_PREFIX = "sprint"
WORK_ITEM_PREFIX = "work_item"
AGENT_PREFIX = "agent"
