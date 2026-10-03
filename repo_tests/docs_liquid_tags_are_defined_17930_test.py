# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No processed doc may contain a Liquid tag Jekyll does not define (#17930).

The docs site stopped building at `125c083ca0` and nobody noticed for days:

    Liquid syntax error (line 64): Unknown tag 'citation' (Liquid::SyntaxError)

The cause is not a templating mistake. `docs/research/private-tenant-chat-reference-app.md`
*quotes Markdoc's* tag syntax while describing it in prose, and a second file quotes an
Ansible/Jinja2 template. **Jekyll runs Liquid over the raw Markdown before rendering**, so neither a
code span nor a fenced block protects the literal: Liquid reaches it and fails on a tag it does not
define. The remedy is a raw guard around the quotation; this guard is what makes the next one fail
at review rather than by the site going dark.

**Why it went unnoticed for days, which is the part a guard has to beat.** The `build` job runs only
when `docs/**` is in the changeset, so the failure is absent from most PRs and present on docs PRs —
a defect that reads as flake. Sampling five consecutive `main` commits showed `build` failing on
three and absent on two.

**Two obvious fixes are both wrong**, recorded here because someone will reach for them:

* Defining `citation` as a Liquid plugin would invent a tag to satisfy a line quoting a DIFFERENT
  templating system. There are zero files under `docs/_plugins`.
* Deleting or rewriting the literal would delete the content — the syntax is what the paragraph is
  about.

**Documenting this defect is itself exposed to it.** The first version of the explanatory comment
added beside the fix spelled the offending tags out literally -- and an HTML comment is not
protected from Liquid either, so the explanation would have been parsed and would have
reintroduced the defect it was explaining. Name such tags in prose, or raw-guard the example. This
guard would have caught it, which is the test of whether a guard covers the documentation of its
own subject.

`EXCLUDED_DIRS` mirrors `docs/_config.yml`'s own `exclude:`, because Jekyll does not process those
trees and a guard flagging them would be correct about the text and wrong about the build. That is
why `docs/archives/` is not scanned: it holds `{% macro %}`, undefined in Liquid and harmless
because it is never rendered.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

DOCS = "docs"

#: Tags Liquid and Jekyll define. A tag outside this set raises `Liquid::SyntaxError` at build time.
#: Enumerated rather than discovered: the point is to compare the tree against what the renderer
#: accepts, and deriving the set from the tree would make any new typo self-authorising.
DEFINED_TAGS = frozenset(
    {
        # Liquid core
        "assign",
        "capture",
        "endcapture",
        "case",
        "when",
        "endcase",
        "comment",
        "endcomment",
        "cycle",
        "decrement",
        "increment",
        "for",
        "endfor",
        "break",
        "continue",
        "if",
        "elsif",
        "else",
        "endif",
        "unless",
        "endunless",
        "raw",
        "endraw",
        "include",
        "render",
        "liquid",
        "echo",
        "tablerow",
        "endtablerow",
        "ifchanged",
        "endifchanged",
        # Jekyll
        "highlight",
        "endhighlight",
        "link",
        "post_url",
        "seo",
        "feed_meta",
        "gist",
        "include_relative",
    }
)

_TAG = re.compile(r"\{%-?\s*([A-Za-z_][A-Za-z0-9_]*)")
_RAW_REGION = re.compile(r"\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}", re.S)

#: Reach floor. A discovery-based guard that scans nothing reports a clean run having asserted
#: nothing -- the failure #15826 catalogues across this repo's tree scanners.
MIN_DOCS_SCANNED = 200


def excluded_dirs() -> frozenset[str]:
    """Top-level names under `docs/` that Jekyll's own config excludes from processing."""
    config = yaml.safe_load((repo_root() / DOCS / "_config.yml").read_text(encoding="utf-8"))
    entries = (config or {}).get("exclude") or []
    return frozenset(str(e).strip('"').strip("/") for e in entries if "*" not in str(e))


def undefined_tags(text: str) -> list[str]:
    """Tag names in *text* that Liquid does not define, ignoring raw-guarded regions.

    A detector over source so fixtures can drive it. Stripping the raw regions FIRST is the whole
    correctness condition: a guard that flagged every `{% ... %}` would reject the fix for this very
    defect, and would pass its own acceptance test while forbidding legitimate templating.
    """
    return sorted({m for m in _TAG.findall(_RAW_REGION.sub("", text)) if m not in DEFINED_TAGS})


def _processed_docs() -> list[Path]:
    skip = excluded_dirs()
    root = repo_root() / DOCS
    return sorted(p for p in root.rglob("*.md") if not any(part in skip for part in p.relative_to(root).parts))


def test_the_doc_scan_still_reaches_the_tree() -> None:
    """Reach floor, before any assertion that iterates the set."""
    found = _processed_docs()
    assert len(found) >= MIN_DOCS_SCANNED, (
        f"only {len(found)} processed docs found, expected at least {MIN_DOCS_SCANNED} -- the glob "
        "or the exclude parsing has stopped reaching the tree, and the assertion below would pass "
        "over almost nothing"
    )


def test_the_exclude_list_is_read_from_jekylls_own_config() -> None:
    """A hand-copied exclude list drifts from the renderer's. `archives` is the live case."""
    skip = excluded_dirs()
    assert "archives" in skip, (
        "docs/_config.yml no longer excludes `archives`; its unrendered Jinja tags would now break "
        "the build, and this guard would have to start flagging them"
    )


def test_no_processed_doc_carries_a_liquid_tag_jekyll_cannot_parse() -> None:
    offenders: list[str] = []
    for path in _processed_docs():
        bad = undefined_tags(path.read_text(encoding="utf-8"))
        if bad:
            offenders.append(f"{path.relative_to(repo_root())}: {', '.join(bad)}")
    assert not offenders, (
        "a processed doc contains a Liquid tag Jekyll does not define, which fails the site build "
        "with Liquid::SyntaxError (#17930):\n  "
        + "\n  ".join(offenders)
        + "\n\nIf the text is QUOTING another templating system, wrap it in a raw guard. Do not "
        "define a Liquid plugin to satisfy a quotation, and do not delete the literal."
    )


# --- the detector, driven on fixtures, because a clean tree proves nothing ------------------


@pytest.mark.parametrize("tag", ["citation", "set", "macro", "endmacro", "block", "extends"])
def test_an_unguarded_foreign_tag_is_reported(tag: str) -> None:
    assert undefined_tags("text {%% %s items=[] %%} more" % tag) == [tag]


@pytest.mark.parametrize("tag", ["if", "for", "assign", "highlight", "post_url", "raw"])
def test_a_defined_tag_is_accepted(tag: str) -> None:
    """The contrast that stops this degenerating into "no `{% %}` in docs".

    A guard rejecting every tag would pass the acceptance test above and forbid all legitimate
    templating -- and would reject the raw guard that fixes this defect.
    """
    assert undefined_tags("text {%% %s %%} more" % tag) == []


def test_a_raw_guarded_foreign_tag_is_accepted() -> None:
    """The fix for this defect must not be flagged by the guard that detects it."""
    assert undefined_tags("before {% raw %}`{% citation items=[] /%}`{% endraw %} after") == []


def test_a_foreign_tag_outside_the_raw_region_is_still_reported() -> None:
    """Stripping raw regions must not swallow the rest of the document."""
    text = "{% raw %}{% citation %}{% endraw %} then {% macro x %}"
    assert undefined_tags(text) == ["macro"]


def test_whitespace_control_dashes_do_not_hide_a_tag() -> None:
    """`{%- set -%}` is the same defect with Liquid's whitespace-control spelling."""
    assert undefined_tags("a {%- set x = 1 -%} b") == ["set"]
