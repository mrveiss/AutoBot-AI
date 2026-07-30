# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Research agent (Phase 0): findings -> KB facts + grounded /research synthesis.

Issue #12622 (child of umbrella #12621). See
``docs/architecture/RESEARCH_AGENT_PRECISION_EFFICIENCY_DESIGN.md`` for the
full architecture. This package composes existing KB/fetch/search modules
into one bounded coordinator; it introduces no parallel store.
"""
