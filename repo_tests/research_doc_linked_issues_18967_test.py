# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Every research document lists the issues it produced (#18967).

A research document and the issues filed from it were linked one way at best: 25 of 56
documents had no issue pointing back at them, and 11 were pointed at by issues the
document itself never listed. A reader landing on either side could not reach the other.

This guard holds the in-repo half: each ``docs/research/*.md`` (except ``_index.md``)
carries a ``## Linked issues`` section with at least one ``- #N`` list item, or -- for
the frozen allowlist only -- the explicit ``None filed yet``, never both. An absent
section and an empty one are both failures, because "nothing was filed" must be stated,
never implied by omission.

**Stated limit.** The other direction -- each listed issue mentioning the document --
lives on GitHub, not in the tree, so no repo test can assert it. The ``research`` skill
carries that half as a rule.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root

#: The section heading, at level 2, anywhere in the document outside a code fence.
_SECTION = re.compile(r"^## Linked issues[ \t]*$")

#: The next level-1 or level-2 heading outside a code fence ends the section.
_NEXT_HEADING = re.compile(r"^#{1,2} ")

#: A code-fence delimiter; a ``#`` line between two of them is code, not a heading.
_FENCE = re.compile(r"^\s*(```|~~~)")

#: An issue reference counts only as a list item: ``- #<digits>``, optionally followed by text.
#: A ``#N`` buried in prose is a mention, not a listing.
_ISSUE_ITEM = re.compile(r"^- #\d+(?:\s.*)?$")
_NONE_FILED = "None filed yet"

#: The docs allowed to carry the none-marker. Frozen and shrink-only: a new doc lists its
#: issues, and an allowlisted doc that files one drops the marker and leaves this set.
_NONE_FILED_ALLOWED = frozenset(
    {
        "REDIS_OWNERSHIP_CONFLICT_RESEARCH_REPORT.md",
        "model-hardware-standard.md",
    }
)

#: Reach floor. A glob that matched nothing would otherwise report every document clean.
#: 50 against 57 today; it bounds a moved directory, not the population's growth.
_MIN_DOCS = 50


def _research_docs() -> list[Path]:
    """Run on docs-only PRs by `docs-liquid-tags.yml`, not the python filter (#17930 trade)."""
    return sorted(p for p in repo_root().glob("docs/research/*.md") if p.name != "_index.md")


def _unfenced_lines(text: str) -> list[str]:
    """The document's lines with every fenced code block removed."""
    kept: list[str] = []
    fenced = False
    for line in text.splitlines():
        if _FENCE.match(line):
            fenced = not fenced
        elif not fenced:
            kept.append(line)
    return kept


def section_lines(text: str) -> list[str] | None:
    """The ``## Linked issues`` section's lines outside code fences, or None when absent."""
    lines = _unfenced_lines(text)
    starts = [i for i, line in enumerate(lines) if _SECTION.match(line)]
    if not starts:
        return None
    body: list[str] = []
    for line in lines[starts[0] + 1 :]:
        if _NEXT_HEADING.match(line):
            break
        body.append(line)
    return body


def _verdict(body: list[str] | None) -> tuple[bool, bool] | None:
    """(lists an issue item, carries the none-marker), or None for a missing section."""
    if body is None:
        return None
    listed = any(_ISSUE_ITEM.match(line) for line in body)
    return listed, any(_NONE_FILED in line for line in body)


def unlinked(docs: dict[str, str]) -> list[str]:
    """Docs whose section is missing, lists nothing, or both lists issues and says none."""
    offenders: list[str] = []
    for name, text in docs.items():
        verdict = _verdict(section_lines(text))
        if verdict is None or verdict[0] == verdict[1]:
            offenders.append(name)
    return offenders


def marker_drift(docs: dict[str, str], allowed: frozenset[str]) -> tuple[list[str], list[str]]:
    """(docs using the none-marker off the allowlist, allowlisted docs no longer using it)."""
    using = {n for n, t in docs.items() if (v := _verdict(section_lines(t))) and v[1]}
    return sorted(using - allowed), sorted(allowed - using)


def test_the_research_directory_holds_a_population_worth_asserting_on() -> None:
    """Reach. A moved directory would otherwise pass as 'every document linked'."""
    count = len(_research_docs())
    assert count >= _MIN_DOCS, (
        f"only {count} research documents found, below the floor of {_MIN_DOCS} -- the "
        "directory has moved, so a clean result below would mean nothing was read"
    )


def test_every_research_doc_lists_its_issues() -> None:
    """#18967: the doc names the issues it produced, or says none were filed."""
    docs = {p.name: p.read_text(encoding="utf-8") for p in _research_docs()}
    offenders = unlinked(docs)
    assert not offenders, (
        f"these research documents have no '## Linked issues' section listing an issue "
        f"or saying '{_NONE_FILED}': {offenders}. A reader of the document cannot reach "
        "the work it produced -- list the issues, and add the document's path to each issue."
    )


def test_a_doc_without_the_section_is_reported() -> None:
    """The detector fires on absence."""
    assert unlinked({"a.md": "# T\n\nFindings, see #123.\n"}) == ["a.md"]


def test_an_empty_section_is_reported() -> None:
    """The detector fires on a section that lists nothing, even with refs elsewhere."""
    text = "# T\n\n## Linked issues\n\n## Appendix\n\nSee #123.\n"
    assert unlinked({"a.md": text}) == ["a.md"]


def test_a_listed_or_explicitly_empty_section_is_not_reported() -> None:
    """The contrast: an issue reference, or the explicit marker, both satisfy it."""
    listed = "# T\n\n## Linked issues\n\n- #18967 — the tracking issue\n"
    none = "# T\n\n## Linked issues\n\nNone filed yet.\n"
    assert unlinked({"a.md": listed, "b.md": none}) == []


def test_only_the_allowlisted_docs_say_none_filed() -> None:
    """The escape is capped: no new doc may use it, and a doc that filed leaves the list."""
    docs = {p.name: p.read_text(encoding="utf-8") for p in _research_docs()}
    unexpected, stale = marker_drift(docs, _NONE_FILED_ALLOWED)
    assert not unexpected, (
        f"these research documents say '{_NONE_FILED}' but are not allowlisted: "
        f"{unexpected}. File the issues the research produced and list them."
    )
    assert not stale, (
        f"these allowlisted documents no longer say '{_NONE_FILED}': {stale}. "
        "Remove them from _NONE_FILED_ALLOWED -- the allowlist only shrinks."
    )


def test_a_prose_mention_is_not_a_listed_issue() -> None:
    """Only a ``- #N`` list item counts; a ``#N`` inside a sentence does not."""
    prose = "# T\n\n## Linked issues\n\nSee #123 for context.\n"
    starred = "# T\n\n## Linked issues\n\n* #123 -- other bullet style\n"
    listed = "# T\n\n## Linked issues\n\nIntro (#999).\n\n- #123\n- #456 -- titled\n"
    assert unlinked({"prose.md": prose, "starred.md": starred, "ok.md": listed}) == [
        "prose.md",
        "starred.md",
    ]


def test_the_none_marker_is_exclusive() -> None:
    """A section listing issues AND saying none were filed contradicts itself."""
    both = "# T\n\n## Linked issues\n\n- #123 -- filed\n\nNone filed yet.\n"
    only_marker = "# T\n\n## Linked issues\n\nNone filed yet.\n"
    assert unlinked({"both.md": both, "marker.md": only_marker}) == ["both.md"]


def test_a_hash_line_inside_a_code_fence_does_not_end_the_section() -> None:
    """A ``# comment`` in a fenced block is code; the section runs on past it."""
    fenced = "# T\n\n## Linked issues\n\n```bash\n# a comment\n```\n\n- #123 -- after\n"
    real_heading = "# T\n\n## Linked issues\n\n## Appendix\n\n- #123 -- not in section\n"
    assert unlinked({"fenced.md": fenced, "heading.md": real_heading}) == ["heading.md"]


def test_a_fenced_marker_or_item_does_not_count() -> None:
    """Text inside a code fence is never a listing nor the marker."""
    fenced_item = "# T\n\n## Linked issues\n\n```\n- #123\n```\n"
    assert unlinked({"a.md": fenced_item}) == ["a.md"]


def test_marker_drift_reports_unlisted_users_and_stale_entries() -> None:
    """Both directions of the cap fire, and a compliant population is clean."""
    marker = "# T\n\n## Linked issues\n\nNone filed yet.\n"
    listed = "# T\n\n## Linked issues\n\n- #123\n"
    allowed = frozenset({"old.md", "filed.md"})
    docs = {"old.md": marker, "filed.md": listed, "new.md": marker}
    assert marker_drift(docs, allowed) == (["new.md"], ["filed.md"])
    assert marker_drift({"old.md": marker}, frozenset({"old.md"})) == ([], [])
