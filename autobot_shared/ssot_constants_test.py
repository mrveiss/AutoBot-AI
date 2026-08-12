# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Value pin for ``CategoryDefaults`` (#14047 review).

Every new assertion this issue's fix added elsewhere in the tree reads
``assert x == CategoryDefaults.GENERAL`` — if someone renames the constant's
*value* (e.g. ``GENERAL: str = "generic"``), the production call site and
every one of those assertions move together and stay green, silently
changing persisted KB metadata, an audit-log field, a Prometheus label, and
a MAP-Elites grid cell key. This file pins the literal independently, the
same role ``ssot-parity.spec.ts`` plays for the TypeScript mirror
(``CATEGORY_DEFAULTS`` in ``src/config/ssot-config.ts``) -- both read the
value as a hard string, not via the symbol under test.
"""

from autobot_shared.ssot_constants import CategoryDefaults


def test_general_value_is_pinned():
    assert CategoryDefaults.GENERAL == "general"


def test_unknown_value_is_pinned():
    assert CategoryDefaults.UNKNOWN == "unknown"


def test_search_mode_hybrid_value_is_pinned():
    assert CategoryDefaults.SEARCH_MODE_HYBRID == "hybrid"
