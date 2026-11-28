# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``@mention`` parsing for comments and work items (#19582).

A mention names an agent by its ``agent_id`` slug: ``@ceo-acme please look``. The
parser only extracts candidate slugs; whether one names a real agent, and in which
company, is decided by the wake dispatcher's tenant-scoped lookup.

What is NOT a mention: the local part of an e-mail address (``ops@acme.io``) and a
bare ``@``. Trailing sentence punctuation is not part of the slug (``@ceo.`` names
``ceo``).
"""

import re
from typing import List, Optional

#: Upper bound on wakes one piece of text can cause, so a pasted roster cannot fan a
#: single comment out into a run per agent in the company.
MAX_MENTIONS_PER_TEXT = 10

# Not preceded by a word char, '@' or '.', so 'ops@acme.io' and '@@x' are not mentions.
# A slug starts and ends alphanumeric; '.', '_' and '-' may sit inside it.
_MENTION_RE = re.compile(r"(?<![\w@.])@([A-Za-z0-9](?:[A-Za-z0-9_.-]*[A-Za-z0-9_])?)")


def parse_mentions(text: Optional[str]) -> List[str]:
    """The distinct slugs ``@mentioned`` in *text*, in first-seen order, capped."""
    seen: List[str] = []
    for slug in _MENTION_RE.findall(text or ""):
        if slug not in seen:
            seen.append(slug)
        if len(seen) >= MAX_MENTIONS_PER_TEXT:
            break
    return seen


def new_mentions(text: Optional[str], previous: Optional[str]) -> List[str]:
    """Mentions in *text* that *previous* did not already have (an edit re-wakes no one)."""
    before = set(parse_mentions(previous))
    return [slug for slug in parse_mentions(text) if slug not in before]
