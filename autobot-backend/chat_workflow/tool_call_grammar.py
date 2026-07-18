# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Canonical `<TOOL_CALL ...>...</TOOL_CALL>` grammar for chat_workflow.

Single source of truth for every regex the tool-call pipeline uses to
recognize, normalize, detect completion of, and (defensively) strip the
`<TOOL_CALL name="..." params='...'>description</TOOL_CALL>` tag emitted
by LLMs mid-response. Issue #11693 consolidates six regexes that
previously lived independently in `chat_workflow/tool_handler.py` and
`chat_workflow/manager.py` — they had to be kept manually in sync
("kept in sync with ..." comments) and had already drifted once (#11666
was a partial fix precisely because the parser and the completion
detector disagreed).

Grammar overview
-----------------
Real models frequently emit a *malformed* close: missing the trailing
`>` (#11545), or truncating `_CALL` entirely to a bare `</TOOL` (#11552),
sometimes followed by a hallucinated "success" sentence. Every pattern
below tolerates those variants while still refusing to treat a stray
`</tool>` in ordinary prose (HTML/XML chat) as a tool call.

- ``TOOL_CALL_OPENING_RE`` — detects a well-formed
  ``<TOOL_CALL name=... params=...>`` opening tag. Used as the
  *structural anchor* that gates the bare-close detector below (a bare
  ``</tool`` only means anything once a real open tag is already in the
  buffer).
- ``TOOL_CALL_BARE_CLOSE_RE`` — matches a truncated ``</tool`` close
  (missing ``_CALL`` and/or ``>``). Only meaningful when
  ``TOOL_CALL_OPENING_RE`` also matched the same buffer (see
  ``manager._check_tool_call_completion``).
- ``TOOL_CALL_COMPLETE_RE`` — the primary "has this tool call finished
  streaming" detector: ``</tool_call``, ``</TOOL_CALL``, ``</TOOL_ CALL``,
  trailing ``>`` optional. Used to stop the stream before a hallucinated
  success line renders.
- ``TOOL_CALL_OPEN_RE`` / ``TOOL_CALL_CLOSE_RE`` — cosmetic normalizers
  that collapse an accidental space in ``<TOOL_ CALL`` / ``</TOOL_ CALL>``
  back to the canonical spelling before parsing (Issue #332).
- ``TOOL_CALL_PATTERN`` — the FULL parser: captures ``name``, the quoted
  ``params`` JSON/literal blob, and the free-text ``description``.
  Tolerates every close variant above (``</tool_call>``, ``</TOOL_CALL``,
  ``</TOOL``, ``</TOOL_ CALL>``, ...) via
  ``</tool(?:_?\\s*call\\b|\\b)\\s*>?``.

Cosmetic safety net
--------------------
``strip_unparsed_tool_tags`` removes a raw ``<TOOL_CALL ...>`` /
``</TOOL_CALL`` fragment from user-visible text ONLY when a well-formed
OPEN tag is present with no corresponding FULL-pattern match anywhere in
the same text — i.e. the tag genuinely never parsed into a tool call and
would otherwise leak to the user (#11545 cosmetic ask). Well-formed calls
that did parse are left untouched, so already-executed tool calls
elsewhere in the same buffer are unaffected.
"""

from __future__ import annotations

import re

# Issue #380 / #11693: cosmetic normalizers — collapse an accidental space
# in the tag spelling (`<TOOL_ CALL` / `</TOOL_ CALL>`) before parsing.
TOOL_CALL_OPEN_RE = re.compile(r"<TOOL_\s+CALL")
TOOL_CALL_CLOSE_RE = re.compile(r"</TOOL_\s+CALL>")

# Issue #727 / #11545: primary "has the tool call tag closed" detector, used
# to stop streaming before a hallucinated success line renders. The
# trailing `>` is optional — some models emit `</TOOL_CALL` + newline/prose
# without it. `\b` keeps `</tool_callable` from matching.
TOOL_CALL_COMPLETE_RE = re.compile(r"</\s*tool_?\s*call\b\s*>?", re.IGNORECASE)

# #11552: chat models frequently TRUNCATE the close to a bare `</TOOL`
# (dropping `_CALL`) and then hallucinate a success line. A bare `</tool…`
# also appears in legitimate prose (HTML/XML/JSX talk), and this detector
# has no structural anchor on its own — so it only counts as a completed
# tool call when TOOL_CALL_OPENING_RE has already matched a well-formed
# opening tag in the same buffer (the only way a real truncated call can
# occur). `\b` after `tool` keeps `</tool_call` (handled above) and
# `</toolbox` from matching here.
TOOL_CALL_BARE_CLOSE_RE = re.compile(r"</\s*tool\b", re.IGNORECASE)
TOOL_CALL_OPENING_RE = re.compile(r"<\s*tool_?\s*call\b[^>]*>", re.IGNORECASE)

# Issue #650 / #11545 / #11552: pre-compiled FULL parser (perf + single
# source of truth). Handles both uppercase and lowercase TOOL_CALL tags
# with nested JSON in params. The close tolerates `</TOOL[_[ ]CALL][>]`:
# `_CALL` and the trailing `>` are both optional. Requires a word boundary
# after `tool` (either the proper `_call\b` continuation, or `\b` when
# `_CALL` is dropped) so `</tool_callable…`/`</toolbox…` never match; the
# opening tag (`<TOOL_CALL name=… params=…>`) is still required, so a bare
# `</tool>` in prose can never match on its own.
TOOL_CALL_PATTERN = re.compile(
    r'<tool_call\s+name="([^"]+)"\s+params=(["\'])(.+?)\2>([^<]*)</tool(?:_?\s*call\b|\b)\s*>?',
    re.IGNORECASE | re.DOTALL,
)


def strip_unparsed_tool_tags(text: str) -> str:
    """Remove a raw, never-parsed `<TOOL_CALL ...>` fragment from user-visible text.

    #11545 (cosmetic): guarded to only fire when a well-formed OPEN tag is
    present with no corresponding FULL-pattern match anywhere in `text` —
    i.e. the tag genuinely failed to parse into a tool call and would
    otherwise leak raw markup to the user. Leaves already-parsed tool
    calls (and text with no tag at all) untouched.
    """
    if not TOOL_CALL_OPENING_RE.search(text):
        return text
    if TOOL_CALL_PATTERN.search(text):
        return text
    stripped = TOOL_CALL_OPENING_RE.sub("", text)
    stripped = TOOL_CALL_COMPLETE_RE.sub("", stripped)
    stripped = re.sub(r"\n{3,}", "\n\n", stripped)
    return stripped.strip()
