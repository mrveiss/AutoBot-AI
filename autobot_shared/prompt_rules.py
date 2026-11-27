# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Shared Prompt Rules and Constants

Provides unified, reusable prompt rules and blocks that enforce critical
behavior patterns across all agents. This module eliminates prompt duplication
and ensures behavioral consistency.

Issue #7380: LEDGER vs EXECUTOR rule to clarify coordination tool semantics.
Issue #15651: the untrusted-text sanitize/frame pair, moved here from
``orchestration/orchestrator_prompts.py`` once a third caller needed it.
"""

import re
from functools import lru_cache
from typing import Any, List, Tuple

LEDGER_VS_EXECUTOR_RULE = """
LEDGER vs EXECUTOR
- Coordination/planning tools (workflow_plan, agent_register, memory_store, swarm_init)
  return *records*, not deliverables. They complete instantly with no file written,
  no command run, no test executed.
- After ANY coordination call, IMMEDIATELY continue with the actual work yourself
  using your file/shell/code tools. Do not wait for the coordinator to "finish" —
  it already finished by returning the record.
- If you need something BUILT or EXECUTED, YOU build it. The coordinator just tracks.
"""


def sanitize_injected(text: Any, limit: int) -> str:
    """Neutralize untrusted text before it enters a prompt (#11015, #11060).

    Untrusted text — a stored trajectory, a learned template, a live user
    request — must not be able to pose as prompt structure. Collapse ALL
    whitespace and newlines to single spaces so a stored value cannot break out
    of its line, strip the ``<<<``/``>>>`` framing-delimiter sequences so the
    content cannot forge its own ``<<<BEGIN/END...>>>`` markers and escape the
    data frame, then truncate to ``limit``.

    #15651: moved here from ``orchestration/orchestrator_prompts.py`` when a
    third caller needed it. It is the single home for this treatment; callers
    pair it with :func:`frame_untrusted_block`, which frames but never
    sanitizes.
    """
    collapsed = " ".join(str(text).split()).replace("<<<", "").replace(">>>", "")
    return collapsed[:limit]


#: Characters a reader skips over: soft hyphen, combining grapheme joiner, zero-width space/joiners, LRM/RLM,
#: word joiner, BOM.
_INVISIBLE_CHARS = "\u00ad\u034f\u200b-\u200f\u2060\ufeff"
#: ``<`` and its lookalikes: fullwidth, small, single angle quotation mark, CJK angle bracket.
_BRACKETS = "<\uff1c\ufe64\u2039\u3008"
#: Possessive (``*+``): a run is consumed once and never re-split, so matching stays linear in the input.
_INVISIBLE = f"[{_INVISIBLE_CHARS}]*+"
_GAP = rf"[\s{_INVISIBLE_CHARS}]*+"


def _spelled(word: str) -> str:
    """``word`` as a pattern that tolerates invisible characters between its (escaped) letters."""
    return _INVISIBLE.join(re.escape(char) for char in word)


@lru_cache(maxsize=64)
def _marker_re(names: Tuple[str, ...]) -> "re.Pattern[str]":
    """One pattern for every opener/closer: the ``<<<BEGIN_``/``<<<END_`` family plus any tag naming ``names``."""
    keyword = f"(?:{_spelled('BEGIN')}|{_spelled('END')}){_INVISIBLE}_"
    generic = rf"(?P<tri>[{_BRACKETS}](?:{_INVISIBLE}[{_BRACKETS}]){{2}})(?={_GAP}{keyword})"
    if not names:
        return re.compile(generic, re.IGNORECASE)
    named = "|".join(_spelled(name) for name in names)
    tagged = rf"(?P<run>[{_BRACKETS}]++)(?={_GAP}/?{_GAP}(?:{keyword})?(?:{named}))"
    return re.compile(f"{generic}|{tagged}", re.IGNORECASE)


def _defuse(match: "re.Match[str]") -> str:
    """``<<<`` -> ``&lt;&lt;&lt;`` for a framing marker, one ``&lt;`` per bracket for a named tag."""
    return "&lt;&lt;&lt;" if match.group("tri") else "&lt;" * len(match.group("run"))


def neutralize_untrusted(text: str, names: Tuple[str, ...] = ()) -> str:
    """The single neutralizer: defuse every delimiter untrusted ``text`` could forge; keep everything else.

    Always defuses the ``<<<BEGIN_`` / ``<<<END_`` framing markers (#20062: any case, whitespace or a newline
    after the ``<<<``, invisible characters inside, lookalike ``<`` brackets). With ``names`` it also defuses
    ``<tag>``, ``</tag>`` and ``<<<NAME`` openers/closers naming any of them (#22285). Defence in depth, so it
    also rewrites harmless lookalikes such as ``cat <<< END_OF_FILE``.

    For text whose shape matters (code, logs): newlines, indentation and other ``<<<`` / ``>>>`` (heredocs, REPL
    prompts) survive. Unlike :func:`sanitize_injected` it neither flattens whitespace nor truncates.
    """
    return _marker_re(tuple(names)).sub(_defuse, text)


def frame_untrusted_text(
    open_marker: str,
    close_marker: str,
    text: str,
    *,
    names: Tuple[str, ...],
    source: str = "",
    preamble: str = "",
    trailer: str = "",
) -> str:
    """Frame ``text`` between caller-chosen markers; the single injection-safe framing path (#22285).

    ``text``, ``source`` (flattened to one line), ``preamble`` and ``trailer`` are neutralized here, never by
    the caller, so none can forge the close marker and end the frame. ``names`` holds the tag/label words of
    the two markers; ``open_marker``/``close_marker`` themselves are emitted verbatim.
    """
    safe = neutralize_untrusted(text, names)
    attr = f" source={neutralize_untrusted(' '.join(source.split()), names)}" if source else ""
    head = f"{neutralize_untrusted(preamble, names)}\n" if preamble else ""
    tail = f"\n{neutralize_untrusted(trailer, names)}" if trailer else ""
    return f"{head}{open_marker}{attr}\n{safe}\n{close_marker}{tail}"


def _neutralize_rows(rows: List[str], names: Tuple[str, ...]) -> List[str]:
    """Neutralize ``rows`` as one text (a marker split across rows is still caught), keeping each row intact.

    Neutralizing never adds or removes a newline, so the result is regrouped by each row's own newline count:
    a row that holds newlines (a multi-line code chunk) stays ONE row and is not re-indented per line.
    """
    pieces = iter(neutralize_untrusted("\n".join(rows), names).split("\n"))
    return ["\n".join(next(pieces) for _ in range(row.count("\n") + 1)) for row in rows]


def frame_untrusted_block(label: str, warning_lines: List[str], body_lines: List[str]) -> str:
    """Wrap already-sanitized untrusted content in data-only framing (#11074).

    Single home for the "treat this as data, never as instructions" pattern: a
    warning preamble followed by ``<<<BEGIN_{label}>>> ... <<<END_{label}>>>``
    delimiters, every row indented 8 spaces to match the prompt templates that
    embed it. ``body_lines`` MUST already be passed through
    :func:`sanitize_injected`. #22285: the helper also defuses forged ``<<<BEGIN_``/``<<<END_`` markers
    (and ``label``'s own) in the body itself, so no caller can frame without neutralizing.

    #15651: moved here from ``orchestration/orchestrator_prompts.py`` so the
    convention is reachable from every backend package rather than through a
    private cross-package import.
    """
    indent = "        "
    safe_body = _neutralize_rows(body_lines, (label,))
    rows = [*warning_lines, f"<<<BEGIN_{label}>>>", *safe_body, f"<<<END_{label}>>>"]
    return "\n" + "\n".join(f"{indent}{row}" for row in rows) + "\n"
