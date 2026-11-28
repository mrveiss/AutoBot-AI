# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Redis key names of the category fact sets and their quarantine index (#21957).

Dependency-free on purpose: ``categories.py``, ``category_quarantine.py`` and ``services/kb_wipe_redis.py``
all name these keys, and the wipe must not import the quarantine machinery to do it.
"""

#: ``category:facts:{category_id}`` -- the ids of the facts in a category.
FACTS_KEY = "category:facts:{}"
#: ``category:quarantined:{category_id}`` -- the quarantined members of that set (a derived projection).
QUARANTINED_KEY = "category:quarantined:{}"
#: Holds the index version a rebuild last completed; a different value (code bump, or a wipe) re-runs it.
REBUILT_MARKER = "category_quarantine_index:rebuilt"
