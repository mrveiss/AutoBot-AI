# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The apps save a file through the kit's `saveBlob` / `saveTextFile` / `saveUrl`, not their own anchor (#20770).

**The boundary.** The count is every assignment to an anchor's `download` property
(`a.download = …`, `link.download = …`) in a `.vue` or `.ts` file under `autobot-frontend/src` and
`autobot-slm-frontend/src`, excluding tests, specs, stories and comment lines. That assignment is
what makes a click save a file, so a hand-rolled save cannot avoid it. The kit
(`libs/autobot-ui/src/utils/saveFile.ts`) holds the one implementation and is not scanned. A
`download` attribute written in a template (`<a :href download>`) is a link the user clicks, not a
script-built save, and is not counted.

**What the pin holds.** The saves in files an open PR held when this landed (#20773, #20479,
#20480, #20478, #20660). The pin goes down as each moves to the kit, and ends at 0.

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
_ASSIGNMENT = re.compile(r"\.download\s*=(?!=)")
_COMMENT_LINE = re.compile(r"^[ \t]*(?://|\*|/\*).*$", re.M)

PIN = 11


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
    return sum(len(_ASSIGNMENT.findall(_COMMENT_LINE.sub("", p.read_text(encoding="utf-8")))) for p in paths)


def _population(root: Path) -> list[str]:
    return [p.relative_to(root).as_posix() for p in _sources(root)]


REACH = declare(
    "frontend-hand-rolled-file-save-scan",
    discover=_population,
    floor=1126,  # mid-window: population 1156, window (1096, 1156)
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
