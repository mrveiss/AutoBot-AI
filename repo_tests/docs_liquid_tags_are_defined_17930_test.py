# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No Liquid-rendered doc may carry a tag Jekyll cannot parse (#17930).

The docs site stopped building at `125c083ca0` and nobody noticed for days:

    Liquid syntax error (line 64): Unknown tag 'citation' (Liquid::SyntaxError)

The cause is not a templating mistake. `docs/research/private-tenant-chat-reference-app.md`
*quotes Markdoc's* tag syntax while describing it in prose. **Jekyll runs Liquid over the raw
Markdown before rendering**, so neither a code span nor a fenced block protects the literal:
Liquid reaches it and fails on a tag it does not define. The remedy is a raw guard around the
quotation; this guard is what makes the next one fail at review rather than by the site going
dark.

**Why it went unnoticed for days, which is the part a guard has to beat.** The `build` job runs
only when `docs/**` is in the changeset, so the failure is absent from most PRs and present on
docs PRs -- a defect that reads as flake. Sampling five consecutive `main` commits showed `build`
failing on three and absent on two.

**Two obvious fixes are both wrong**, recorded here because someone will reach for them:

* Defining `citation` as a Liquid plugin would invent a tag to satisfy a line quoting a DIFFERENT
  templating system. There are zero files under `docs/_plugins`.
* Deleting or rewriting the literal would delete the content -- the syntax is what the paragraph
  is about.

**Documenting this defect is itself exposed to it.** The first version of the explanatory comment
added beside the fix spelled the offending tags out literally -- and an HTML comment is not
protected from Liquid either, so the explanation would have been parsed and would have
reintroduced the defect it was explaining. Name such tags in prose, or raw-guard the example.

THE POPULATION IS FRONT-MATTER FILES, NOT EVERY `*.md` (#17930 review, #17844)
------------------------------------------------------------------------------
The first version of this guard declared ``what="Jekyll-processed Markdown docs"`` and scanned
every `*.md` under `docs/` outside the config's own `exclude:` -- 739 files. That label was
false, and #17844 is open about exactly this failure: ``declare()``'s ``what=`` is unverified
free text, so a floor can be measured correctly over the wrong population.

Jekyll decides *page or static file* by front matter: ``Jekyll::Utils.has_yaml_header?`` reads
the first line and asks whether it is ``---``. A file without one is **copied verbatim** and
never reaches Liquid, so it cannot break the build no matter what it quotes. Measured on this
tree: 131 of those 739 files begin with front matter. The other 608 were a population in which
this guard could only ever produce false positives, and the floor was sized over them.

Verified before narrowing, because the premise has one escape hatch: `jekyll-optional-front-
matter` makes front-matter-less pages render after all. `docs/_config.yml` lists one plugin
(`jekyll-seo-tag`) and `docs/Gemfile` three gems (`jekyll`, `just-the-docs`, `jekyll-seo-tag`);
the plugin is absent from both, and `.github/workflows/pages.yml` builds with plain
`bundle exec jekyll build`. Add that plugin and this guard's population becomes every `*.md`
again -- the predicate below is the place that has to change.

`EXCLUDED_DIRS` mirrors `docs/_config.yml`'s own `exclude:`, because Jekyll does not process
those trees and a guard flagging them would be correct about the text and wrong about the build.
That is why `docs/archives/` is not scanned: it holds `{% macro %}`, undefined in Liquid and
harmless because it is never rendered.

WHAT THE DETECTOR CHECKS, AND WHY NAMES WERE NOT ENOUGH
--------------------------------------------------------
Checking tag NAMES against a whitelist is half the property. Liquid also rejects a structurally
broken template, and every one of `{% endif %}` alone, `{% else %}` alone, `{% endfor %}` alone,
an unclosed `{% if %}` and an unclosed `{% raw %}` is a `Liquid::SyntaxError` built entirely out
of whitelisted names -- so the first version of this guard returned "clean" for all five. The
irony worth recording: the sibling fix riding this same branch (#17932) is a stray `{% endif %}`.
`unbalanced_tags` adds the structural half.
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

DOCS = "docs"

#: The tree this guard reads, spelled the way `.github/filters/python-paths.yml` spells it so
#: the two can be compared (#17930 review). It was a bare `"*.md"`, which
#: `glob_declared_reads_15900_test` reads as a ROOT-relative sweep into trees the filter cannot
#: reach -- so the dependency was recorded in `_glob_declared_uncovered.py` as an accepted gap
#: instead of being covered, and that record's own header forbids adding an entry to make a new
#: uncovered dependency pass. Every file this guard reads lives under `docs/`, so the dependency
#: is coverable; the filter now covers it and the record no longer names this guard.
#:
#: The walk below stays rooted at `docs/` rather than becoming `root.glob(DOCS_GLOB)`:
#: `repo_root_walks_use_git_15955_test` flags a `**` glob from the repository root, because such
#: a walk descends into the nested checkouts under `.worktrees/` and `.claude/`.
DOCS_GLOB = "docs/**/*.md"

#: Tags Liquid and Jekyll define. A tag outside this set raises `Liquid::SyntaxError` at build
#: time. Enumerated rather than discovered: the point is to compare the tree against what the
#: renderer accepts, and deriving the set from the tree would make any new typo self-authorising.
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

#: Block tags and the end tag each requires. Every name here is in `DEFINED_TAGS`, which is the
#: point: these are the errors a name whitelist cannot see.
BLOCK_TAGS = {
    "capture": "endcapture",
    "case": "endcase",
    "comment": "endcomment",
    "for": "endfor",
    "highlight": "endhighlight",
    "if": "endif",
    "ifchanged": "endifchanged",
    "raw": "endraw",
    "tablerow": "endtablerow",
    "unless": "endunless",
}
END_TAGS = {end: start for start, end in BLOCK_TAGS.items()}

#: Tags valid only INSIDE a particular block. `{% else %}` at top level is a syntax error the
#: same way `{% endif %}` at top level is, and both are whitelisted names.
INNER_TAGS = {
    "break": frozenset({"for", "tablerow"}),
    "continue": frozenset({"for", "tablerow"}),
    "else": frozenset({"case", "for", "if", "unless"}),
    "elsif": frozenset({"if", "unless"}),
    "when": frozenset({"case"}),
}

_TAG = re.compile(r"\{%-?\s*([A-Za-z_][A-Za-z0-9_]*)")
_RAW_REGION = re.compile(r"\{%-?\s*raw\s*-?%\}.*?\{%-?\s*endraw\s*-?%\}", re.S)
#: Liquid's `comment` block overrides `unknown_tag` to do nothing, so a foreign tag inside one is
#: ignored rather than fatal. Without this the guard rejected Markdown Jekyll accepts.
_COMMENT_REGION = re.compile(r"\{%-?\s*comment\s*-?%\}.*?\{%-?\s*endcomment\s*-?%\}", re.S)

#: Jekyll's own page/static-file test: `Utils.has_yaml_header?` reads the first line and matches
#: `\A---\r?\n`. A file failing it is copied verbatim and Liquid never sees it.
_FRONT_MATTER = re.compile(rb"^---\r?\n")


def has_front_matter(path: Path) -> bool:
    """Whether Jekyll renders *path* as a page rather than copying it as a static file."""
    try:
        with path.open("rb") as handle:
            return _FRONT_MATTER.match(handle.readline()) is not None
    except OSError:
        return False


def _non_excluded_docs(root: Path) -> list[Path]:
    """Every `*.md` under `docs/` outside the dirs `_config.yml` excludes -- page or not."""
    skip = excluded_dirs()
    docs = root / DOCS
    leaf = DOCS_GLOB.rsplit("/", 1)[-1]
    return sorted(p for p in docs.rglob(leaf) if not any(part in skip for part in p.relative_to(docs).parts))


def _liquid_rendered_docs(root: Path) -> list[Path]:
    """The docs Liquid actually parses: the non-excluded ones that carry front matter."""
    return [p for p in _non_excluded_docs(root) if has_front_matter(p)]


#: Reach floor. A discovery-based guard that scans nothing reports a clean run having asserted
#: nothing -- the failure #15826 catalogues across this repo's tree scanners.
#:
#: Re-measured at 131 for the front-matter population, NOT carried across from the 650 that was
#: sized over 739 files of which 608 can never break the build (#15928 forbids carrying a floor
#: across a population change, and that is the whole point of this re-pin).
#:
#: The numbers are measured, and the risk they are sized against is the CEILING, not shrinkage.
#: `verify_floor` fails when `count - floor > skips + growth`, so an over-wide window is not free
#: caution -- it is a date on which an unrelated PR goes red. Measured on `main` by counting the
#: front-matter population at past revisions, since the site landed ~120 days ago:
#:
#:     120d 102 · 110d 114 · 100d 114 · 80d 114 · 70d 116 · 50d 120 · 40d 119 · 20d 117 · now 131
#:
#: That is +0.24 files/day, and the largest drawdown in the series is 3 files.
#:
#: * `floor=125` sits 6 below today -- twice the largest observed drawdown, so ordinary
#:   archiving does not fire it, while the loss of a seventh file (4.6% of the sweep)
#:   does.
#: * `growth=50` puts the ceiling at 175, which is 44 above today: ~180 days at the measured
#:   rate before a deliberate ratchet is due.
#:
#: A `min_fraction` was reconsidered rather than dismissed (#17930 review). The earlier note
#: claimed the relative mode was unusable because `archives/` grows the denominator -- that was
#: only true of ONE candidate reference, and `reference=` is overridable. Against the
#: non-excluded docs count the ratio is strikingly stable: 0.167 / 0.182 / 0.180 / 0.174 / 0.176
#: / 0.171 / 0.170 / 0.165 / 0.177 over the same nine revisions, so `min_fraction=0.15` would
#: never need re-pinning. It is still not taken, for a measured reason: 0.15 of 739 is 110, so
#: the sweep could lose 21 files -- 16% -- before firing, where `floor=125` fires on the 7th
#: (4.6%); partial loss is the failure that
#: `test_every_declared_floor_is_pinned_to_its_population` exists for. The staleness that
#: justifies trading that away does not apply at this scale -- the population that produced
#: SEVENTEEN re-pins grew at ~33 files/day and burned its ceiling in hours; this one grows at
#: 0.24/day and buys ~180 days. Revisit if the rate rises or the ratio starts drifting.
DOCS_SCANNED = declare(
    "jekyll-processed-docs",
    discover=_liquid_rendered_docs,
    roots=(DOCS,),
    floor=125,
    growth=50,
    skips=0,
    what="Markdown docs with front matter, the only ones Jekyll renders through Liquid",
)


def excluded_dirs() -> frozenset[str]:
    """Top-level names under `docs/` that Jekyll's own config excludes from processing."""
    config = yaml.safe_load((repo_root() / DOCS / "_config.yml").read_text(encoding="utf-8"))
    entries = (config or {}).get("exclude") or []
    return frozenset(str(e).strip('"').strip("/") for e in entries if "*" not in str(e))


def liquid_text(text: str) -> str:
    """*text* with the regions Liquid does not parse for tags removed.

    ORDER IS THE CORRECTNESS CONDITION, and it governs both strips for the same reason.
    Raw regions go FIRST: a guard that flagged every `{% ... %}` would reject the fix for this
    very defect. Comment regions go SECOND, because a `{% comment %}` *quoted inside* a raw block
    is content, and stripping comments first would make it open a region that swallows the rest
    of the document up to an unrelated `{% endcomment %}` -- including real violations.
    """
    return _COMMENT_REGION.sub("", _RAW_REGION.sub("", text))


def undefined_tags(text: str) -> list[str]:
    """Tag names in *text* that Liquid does not define, ignoring regions it does not parse."""
    return sorted({m for m in _TAG.findall(liquid_text(text)) if m not in DEFINED_TAGS})


def unbalanced_tags(text: str) -> list[str]:
    """Structural Liquid errors in *text* that a name whitelist cannot see.

    A stack over the same stripped text `undefined_tags` reads. An unclosed `{% raw %}` survives
    the strip precisely because the strip needs both halves, so it is reported here rather than
    hiding the rest of the file.

    Known limitation, stated rather than discovered later: `{% liquid %}`'s inline tag syntax
    puts several tags in one `{% %}`, and only the first word is read. No doc in this tree uses
    it; a doc that starts to would need this extended.
    """
    stack: list[str] = []
    problems: list[str] = []
    for match in _TAG.finditer(liquid_text(text)):
        name = match.group(1)
        if name in BLOCK_TAGS:
            stack.append(name)
        elif name in END_TAGS:
            opener = END_TAGS[name]
            if not stack:
                problems.append(f"{{% {name} %}} with no {{% {opener} %}} open")
            elif stack[-1] != opener:
                problems.append(f"{{% {name} %}} closes {{% {opener} %}}, but {{% {stack[-1]} %}} is open")
            else:
                stack.pop()
        elif name in INNER_TAGS and not any(open_block in INNER_TAGS[name] for open_block in stack):
            problems.append(f"{{% {name} %}} outside any block that allows it")
    problems.extend(f"{{% {name} %}} is never closed by {{% {BLOCK_TAGS[name]} %}}" for name in reversed(stack))
    return problems


def test_the_doc_scan_still_reaches_the_tree() -> None:
    """Reach floor, before any assertion that iterates the set."""
    DOCS_SCANNED.examined(repo_root())


def test_the_exclude_list_is_read_from_jekylls_own_config() -> None:
    """A hand-copied exclude list drifts from the renderer's. `archives` is the live case."""
    skip = excluded_dirs()
    assert "archives" in skip, (
        "docs/_config.yml no longer excludes `archives`; its unrendered Jinja tags would now break "
        "the build, and this guard would have to start flagging them"
    )


def test_the_site_does_not_render_front_matter_less_files() -> None:
    """The premise the population rests on: no plugin makes a static file render (#17844).

    `jekyll-optional-front-matter` is the one thing that would turn every `*.md` into a page.
    Checked in BOTH places it could be enabled, because a gem present in the bundle and absent
    from `plugins:` does not load, and a name in `plugins:` without the gem fails the build.
    """
    config = yaml.safe_load((repo_root() / DOCS / "_config.yml").read_text(encoding="utf-8"))
    plugins = [str(p) for p in (config or {}).get("plugins") or []]
    gemfile = (repo_root() / DOCS / "Gemfile").read_text(encoding="utf-8")
    assert "optional-front-matter" not in " ".join(plugins), (
        f"docs/_config.yml now loads a plugin that renders front-matter-less files ({plugins}); "
        "this guard's population is front-matter files only and must widen back to every *.md"
    )
    assert "optional-front-matter" not in gemfile, (
        "docs/Gemfile now carries the optional-front-matter gem; if it reaches `plugins:` this "
        "guard's population is wrong -- see the module docstring"
    )


def test_a_doc_without_front_matter_is_not_in_the_population() -> None:
    """The contrast for the narrowing. Without it, "scan pages" is satisfied by scanning all."""
    population = set(DOCS_SCANNED.examined(repo_root()))
    eligible = _non_excluded_docs(repo_root())
    static = [p for p in eligible if p not in population]
    assert static, (
        "every non-excluded doc now carries front matter, so this test asserts nothing about the "
        "narrowing; re-check the predicate rather than deleting the test"
    )
    assert not [p for p in static if has_front_matter(p)], "a front-matter file was dropped from the population"


def test_no_rendered_doc_carries_a_liquid_tag_jekyll_cannot_parse() -> None:
    offenders: list[str] = []
    for path in DOCS_SCANNED.examined(repo_root()):
        text = path.read_text(encoding="utf-8")
        bad = undefined_tags(text) + unbalanced_tags(text)
        if bad:
            offenders.append(f"{path.relative_to(repo_root())}: {', '.join(bad)}")
    assert not offenders, (
        "a Liquid-rendered doc contains a tag Jekyll cannot parse, which fails the site build "
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


def test_a_foreign_tag_inside_a_comment_block_is_accepted() -> None:
    """Liquid's `comment` block ignores unknown tags, so flagging one rejects valid Markdown."""
    assert undefined_tags("{% comment %}{% citation %}{% endcomment %}") == []


def test_the_same_tag_outside_the_comment_block_is_still_reported() -> None:
    """The mandatory contrast. Without it, "ignore comments" degenerates into ignoring the file."""
    text = "{% comment %}{% citation %}{% endcomment %} then {% citation %}"
    assert undefined_tags(text) == ["citation"]


def test_a_comment_tag_quoted_inside_a_raw_region_does_not_open_a_comment() -> None:
    """The ordering fixture: raw regions must be stripped BEFORE comment regions.

    Stripping comments first makes the quoted `{% comment %}` open a region that runs to the
    quoted `{% endcomment %}`, swallowing the real violation between them.
    """
    text = "{% raw %}{% comment %}{% endraw %} {% citation %} {% raw %}{% endcomment %}{% endraw %}"
    assert undefined_tags(text) == ["citation"]


def test_whitespace_control_dashes_do_not_hide_a_tag() -> None:
    """`{%- set -%}` is the same defect with Liquid's whitespace-control spelling."""
    assert undefined_tags("a {%- set x = 1 -%} b") == ["set"]


# --- the structural half: every case below is built from WHITELISTED names ------------------


@pytest.mark.parametrize(
    "text",
    ["{% endif %}", "{% else %}", "{% endfor %}", "{% if x %}", "{% raw %}"],
    ids=["stray-endif", "stray-else", "stray-endfor", "unclosed-if", "unclosed-raw"],
)
def test_a_structurally_broken_template_is_reported(text: str) -> None:
    """All five returned `[]` while only names were checked, and all five fail the site build."""
    assert unbalanced_tags(text), f"accepted a Liquid syntax error: {text}"
    assert undefined_tags(text) == [], "these are whitelisted NAMES -- the name check cannot see them"


def test_a_crossed_pair_is_reported() -> None:
    """Both names are defined and both halves are present; the nesting is still wrong."""
    assert unbalanced_tags("{% if x %}{% endfor %}")


@pytest.mark.parametrize(
    "text",
    [
        "{% if x %}a{% else %}b{% endif %}",
        "{% for i in y %}{% if i %}{% break %}{% endif %}{% endfor %}",
        "{% case x %}{% when 1 %}a{% else %}b{% endcase %}",
        "{% capture t %}x{% endcapture %}",
        "{% raw %}{% endif %}{% endraw %}",
        "{% comment %}{% endif %}{% endcomment %}",
        "{% assign x = 1 %}{% include a.html %}",
    ],
    ids=["if-else", "for-break", "case-when", "capture", "raw-quoted-end", "comment-quoted-end", "inline"],
)
def test_well_formed_liquid_is_accepted(text: str) -> None:
    """The contrast. Without it, "check balance" is satisfied by rejecting every template."""
    assert unbalanced_tags(text) == []
