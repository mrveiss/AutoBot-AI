# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The apps save a file through the kit's `saveBlob` / `saveTextFile` / `saveUrl`, not their own anchor (#20770).

**The boundary.** The count is every assignment to an anchor's `download` property
(`a.download = …`, `a['download'] = …`, `Object.assign(a, { download })`,
`a.setAttribute('download', …)`) in a `.vue` or `.ts` file under `autobot-frontend/src` and
`autobot-slm-frontend/src`, excluding tests, specs, stories and comment lines. That assignment is
what makes a click save a file, so a hand-rolled save cannot avoid it. The kit
(`libs/autobot-ui/src/utils/saveFile.ts`) holds the one implementation and is not scanned. A
`download` attribute written in a template (`<a :href download>`) is a link the user clicks, not a
script-built save, and is not counted. Where a form carries a receiver, the receiver is read too
(#21195): `Object.assign(settings, { download: value })` and a `download` attribute on a
non-anchor receiver are not saves, and the shorthand `Object.assign(a, { download })` counts like
the `download: name` spelling does (#21195).

**What the pin holds.** The saves in files that open PRs #21122, #21126, #21132 and #21087 still
touch; each moves to the kit when its PR lands. The pin goes down as each does, and ends at 0.

**One number, not a per-file table**, as in `frontend_local_date_formatter_ratchet_19905_test.py`. The
pin is down-only against the base (#19283). The reach floor guards the scan itself, since a moved
folder would otherwise read as a clean 0.
"""

from __future__ import annotations

import re
from pathlib import Path

from repo_tests._paths import repo_root
from repo_tests._ratchet_base import base_table
from repo_tests._reach import declare

_ROOTS = ("autobot-frontend/src", "autobot-slm-frontend/src")
_EXCLUDED = re.compile(r"(\.test\.|\.spec\.|\.stories\.|/__tests__/)")
_ASSIGNMENT = re.compile(
    r"\.download\s*=(?!=)"
    r"|\[\s*['\"`]download['\"`]\s*\]\s*=(?!=)"
    r"|Object\.assign\(\s*(?P<assign_receiver>[^,()]+?)\s*,[^{}()]*?\{\s*"
    r"(?:[^{}]*?,\s*)?(?:download\b\s*[:,}]|['\"`]download['\"`]\s*:)"
    r"|(?:(?P<attr_receiver>[A-Za-z_$][\w$]*(?:\??\.[A-Za-z_$][\w$]*)*)\s*\??\.)?"
    r"setAttribute\(\s*['\"`]download['\"`]"
)
_COMMENT_LINE = re.compile(r"^[ \t]*(?://|\*|/\*).*$", re.M)
#: A receiver segment that reads as an anchor (#21195): a bare `a`, or a name carrying
#: `anchor` / `link` (`anchorEl`, `linkRef`). `settings` and friends carry neither.
_ANCHOR_RECEIVER = re.compile(r"a|(?:\w*(?:anchor|link)\w*)", re.I)
#: A same-file `const` / `let` / `var` binding, read for receivers the name cannot
#: place: `const el = document.querySelector('a')` binds an anchor, `el` alone does not.
#: An optional type annotation between the name and `=` is skipped, so a typed
#: declaration (`const el: HTMLAnchorElement = …`) still binds its initializer.
_BINDING = re.compile(r"\b(?:const|let|var)\s+([A-Za-z_$][\w$]*)\s*(?::[^=;\n]*)?=\s*([^;\n]+)")
#: String and template literals, blanked at the same length before brace matching so
#: a `{` inside a string or a regex does not unbalance the scope walk.
_STRING_LITERAL = re.compile(r"'(?:\\.|[^'\\])*'|\"(?:\\.|[^\"\\])*\"|`(?:\\.|[^`\\])*`")
#: Evidence, in a binding's initializer, that the variable holds an anchor element:
#: the tag-a lookups. An id or selector of unknown target is not evidence (#21195).
_ANCHOR_SOURCE = re.compile(
    r"querySelector\s*\(\s*['\"`]a['\"`]"
    r"|createElement\s*\(\s*['\"`]a['\"`]"
    r"|getElementsByTagName\s*\(\s*['\"`]a['\"`]",
    re.I,
)

PIN = 6


def _is_anchor(receiver: str | None, bindings: dict[str, str] | None = None) -> bool:
    """Whether the receiver of an `Object.assign` / `setAttribute` form is an anchor (#21195).

    A receiver the pattern cannot name (`x().setAttribute(…)`) is not evidence of a
    non-anchor and keeps the pre-#21195 treatment: it counts. A named receiver that
    reads as an anchor counts across optional chains (`anchorRef?.current`), and a name
    that says nothing (`el`) is resolved against the file's own `const`/`let`/`var`
    bindings: bound to an anchor element it counts, bound elsewhere or not bound at all
    the name decides (`settings` stays out — counting unknowns again is the over-count
    #21195 asked to remove).
    """
    if receiver is None:
        return True
    segments = receiver.replace("?.", ".").split(".")
    if any(_ANCHOR_RECEIVER.fullmatch(segment) for segment in segments):
        return True
    init = (bindings or {}).get(segments[0])
    if init is None:
        return False
    return bool(_ANCHOR_SOURCE.search(init)) or bool(_ANCHOR_RECEIVER.fullmatch(init.strip()))


def _scope_ends(text: str, starts: list[int]) -> list[int]:
    """The end position of the innermost block enclosing each declaration in *starts*.

    The walk matches braces over the string-blanked source, so a `const` inside a
    function or block ends its scope at that block's `}` and cannot stand in for a
    later use outside it (#21195). A declaration no block encloses (top level) runs
    to the end of the file. Unbalanced braces degrade to that same file-wide end.
    """
    src = _STRING_LITERAL.sub(lambda m: " " * len(m.group(0)), text)
    remaining = set(starts)
    stack: list[int] = []
    owner: dict[int, int | None] = {}
    for pos, char in enumerate(src):
        if pos in remaining:
            owner[pos] = stack[-1] if stack else None
            remaining.discard(pos)
        if char == "{":
            stack.append(pos)
        elif char == "}" and stack:
            stack.pop()
    closes: dict[int, int] = {}
    stack = []
    for pos, char in enumerate(src):
        if char == "{":
            stack.append(pos)
        elif char == "}" and stack:
            closes[stack.pop()] = pos
    end = len(src)
    return [end if owner[s] is None else closes.get(owner[s], end) for s in starts]


def _binding_in_force(
    declarations: list[tuple[int, str, str, int]], receiver: str | None, pos: int
) -> dict[str, str] | None:
    """The declaration of the receiver's root name that applies at `pos`.

    A later redeclaration must not stand in for the value the use actually sees —
    two functions each binding `el` read their own — and neither may a nearer
    declaration whose block has already closed: `const el = …` inside a bare inner
    block is out of scope where the outer `el` is still in force (#21195).
    """
    if receiver is None:
        return None
    name = receiver.replace("?.", ".").split(".")[0]
    applicable = [init for start, decl, init, scope_end in declarations if decl == name and start < pos <= scope_end]
    return {name: applicable[-1]} if applicable else None


def _sources(root: Path) -> list[Path]:
    """Every in-boundary `.vue` and `.ts` source of both apps."""
    found = []
    for rel in _ROOTS:
        src = root / rel
        for path in sorted(src.rglob("*")):
            inner = "/" + path.relative_to(src).as_posix()
            if path.suffix in (".ts", ".vue") and "node_modules" not in path.parts and not _EXCLUDED.search(inner):
                found.append(path)
    return found


def count(paths: list[Path]) -> int:
    """Anchor `download` assignments over *paths*, comment lines removed."""
    total = 0
    for path in paths:
        text = _COMMENT_LINE.sub("", path.read_text(encoding="utf-8"))
        starts = [m.start() for m in _BINDING.finditer(text)]
        scope_ends = _scope_ends(text, starts)
        declarations = [
            (m.start(), m.group(1), m.group(2), scope_ends[i]) for i, m in enumerate(_BINDING.finditer(text))
        ]
        for match in _ASSIGNMENT.finditer(text):
            receiver = match.group("assign_receiver") or match.group("attr_receiver")
            if _is_anchor(receiver, _binding_in_force(declarations, receiver, match.start())):
                total += 1
    return total


def _population(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in _sources(root)]


REACH = declare(
    "frontend-hand-rolled-file-save-scan",
    discover=_population,
    floor=1155,  # mid-window: population 1185, window (1125, 1185)
    growth=60,
    what="vue and ts sources in both frontends",
    roots=_ROOTS,
)


def _w(root: Path, rel: str, body: str) -> Path:
    target = root / rel
    target.parent.mkdir(parents=True, exist_ok=True)
    target.write_text(body, encoding="utf-8")
    return target


class TestTheDetectorWorksBeforeItsOutputIsRead:
    def test_it_counts_each_hand_rolled_save(self, tmp_path: Path) -> None:
        paths = [
            _w(tmp_path, "a/A.vue", "const a = document.createElement('a')\na.download = name\na.click()\n"),
            _w(tmp_path, "a/b.ts", "  link.download = `x-${id}.csv`\n"),
            _w(tmp_path, "a/C.vue", "anchor.download='f.json'; other.download = g\n"),
        ]
        assert count(paths) == 4

    def test_it_counts_a_set_attribute_download(self, tmp_path: Path) -> None:
        planted = _w(tmp_path, "a/P.vue", "link.setAttribute('download', filename)\n")
        assert count([planted]) == 1

    def test_it_counts_the_other_spellings_of_the_download_property(self, tmp_path: Path) -> None:
        assert count([_w(tmp_path, "a/O.vue", "Object.assign(a, { href: u, download: name })\n")]) == 1
        assert count([_w(tmp_path, "a/I.vue", "a['download'] = name\n")]) == 1
        assert count([_w(tmp_path, "a/T.vue", "a.setAttribute(`download`, name)\n")]) == 1

    def test_it_counts_a_shorthand_download_property(self, tmp_path: Path) -> None:
        assert count([_w(tmp_path, "a/S.vue", "Object.assign(a, { href: u, download })\n")]) == 1
        assert count([_w(tmp_path, "a/S2.vue", "Object.assign(link, { download })\n")]) == 1

    def test_a_download_on_a_non_anchor_receiver_is_not_a_save(self, tmp_path: Path) -> None:
        paths = [
            _w(tmp_path, "a/N.vue", "Object.assign(settings, { download: value })\n"),
            _w(tmp_path, "a/N2.ts", "Object.assign(prefs, { download })\n"),
            _w(tmp_path, "a/N3.vue", "settings.setAttribute('download', value)\n"),
            _w(tmp_path, "a/N4.vue", "settings?.setAttribute('download', value)\n"),
        ]
        assert count(paths) == 0

    def test_a_set_attribute_counts_across_an_optional_chain(self, tmp_path: Path) -> None:
        paths = [
            _w(tmp_path, "a/C1.vue", "anchorRef?.current?.setAttribute('download', name)\n"),
            _w(tmp_path, "a/C2.vue", "linkEl.current.setAttribute(`download`, name)\n"),
        ]
        assert count(paths) == 2

    def test_a_receiver_named_by_a_binding_reads_its_initializer(self, tmp_path: Path) -> None:
        paths = [
            _w(tmp_path, "a/B1.vue", "const el = document.querySelector('a')\nel?.setAttribute('download', name)\n"),
            _w(tmp_path, "a/B2.ts", "const node = document.createElement('a')\nnode.setAttribute('download', name)\n"),
        ]
        assert count(paths) == 2

    def test_a_binding_that_is_not_an_anchor_does_not_make_the_receiver_one(self, tmp_path: Path) -> None:
        paths = [
            _w(
                tmp_path,
                "a/N5.vue",
                "const el = document.querySelector('#share')\nel?.setAttribute('download', name)\n",
            ),
            _w(
                tmp_path,
                "a/N6.ts",
                "const box = document.querySelector('.toolbar')\nbox.setAttribute('download', name)\n",
            ),
        ]
        assert count(paths) == 0

    def test_a_typed_binding_still_reads_its_initializer(self, tmp_path: Path) -> None:
        paths = [
            _w(
                tmp_path,
                "a/T1.ts",
                "const el: HTMLAnchorElement = document.createElement('a')\nel.setAttribute('download', name)\n",
            ),
        ]
        assert count(paths) == 1

    def test_each_use_resolves_the_declaration_in_force_at_that_point(self, tmp_path: Path) -> None:
        paths = [
            _w(
                tmp_path,
                "a/R.ts",
                "function save() { const el = document.createElement('a'); el.setAttribute('download', name) }\n"
                "function other() { const el = document.createElement('div'); el.setAttribute('download', name) }\n",
            ),
        ]
        assert count(paths) == 1

    def test_a_declaration_in_a_closed_block_does_not_hide_the_outer_one(self, tmp_path: Path) -> None:
        paths = [
            _w(
                tmp_path,
                "a/SB.ts",
                "function save() {\n"
                "  const el = document.createElement('a');\n"
                "  {\n"
                "    const el = document.createElement('div');\n"
                "  }\n"
                "  el.setAttribute('download', name);\n"
                "}\n",
            ),
        ]
        assert count(paths) == 1

    def test_a_kit_call_a_comparison_a_comment_and_a_template_attribute_are_not_saves(self, tmp_path: Path) -> None:
        paths = [
            _w(tmp_path, "a/A.vue", "saveBlob(blob, 'x.csv')\nsaveTextFile(t, 'y.md', 'text/markdown')\n"),
            _w(tmp_path, "a/B.ts", "if (a.download == name) {}\nif (a.download === name) {}\n"),
            _w(tmp_path, "a/C.vue", "// a.download = name\n * link.download = name\n"),
            _w(tmp_path, "a/D.vue", '<template><a :href="url" download>x</a></template>\n'),
        ]
        assert count(paths) == 0


def test_the_apps_do_not_hand_roll_more_file_saves_than_pinned() -> None:
    root = repo_root()
    for rel in _ROOTS:
        assert (root / rel).is_dir(), f"{rel} has moved; this guard reads it by path"
    now = count([root / rel for rel in REACH.examined(root)])
    assert (
        now <= PIN
    ), f"{now} hand-rolled file saves, pin {PIN}: call saveBlob / saveTextFile / saveUrl from @autobot/ui."
    assert now == PIN, f"{now} hand-rolled file saves, pin says {PIN}: lower PIN to {now} (#20770)."


def test_the_pin_was_not_raised_against_the_base() -> None:
    base = base_table(repo_root(), ("repo_tests/frontend_hand_rolled_file_save_ratchet_20770_test.py",), "PIN")
    if base != {}:
        assert PIN <= base, f"PIN rose from {base} to {PIN}; the pin only goes down."
