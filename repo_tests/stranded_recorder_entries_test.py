# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15566 -- entries in the repository's *recorders* that the tree no longer holds.

A **recorder** holds a path as data; a **reference** holds it as a link. Every
link-checker walks straight past recorders, so when a file moves or is deleted
its references get fixed -- someone sees the dead link -- and its **records** are
silently stranded. Six recorder files were stranded by five separate changes in
a single day (#15566's own evidence), each caught by CI failing *after* the
change rather than by anyone scoping it; in one case the detector reported
"pass, 0 violations" while a later step failed on the stranded entry, so even
the failure pointed at the wrong thing.

The population is *changes that strand a record*, not *records that changed*.
``repo_tests/sys_modules_leak_baseline.txt`` shows **zero commits** for the day
it was stranded: an entry was removed on the belief a leak was fixed, CI failed,
and the removal was reverted. A commit-count sweep sees nothing there. Existence
of the recorded path is the only signal that survives that.

## What this guard reads, and why the enumeration is half discovered

Two recorder shapes, deliberately handled differently:

* **Python ledgers** -- a module-level dict, set, list or tuple whose string
  entries are repository-root-relative paths. These are DISCOVERED, never
  listed, because a ledger inside a guard is written by whoever writes the
  guard and a hand-maintained register of them is exactly the dormant list this
  issue exists to prevent. 34 are found in the current tree, from
  ``KNOWN_LARGE``'s 499 rows to a three-entry lint allowlist.
* **Text and JSON baselines** -- their entry format is per-file (pipe-delimited,
  tab-delimited, one-per-line, JSON keys) and cannot be inferred, so each is
  REGISTERED with the reader that parses it and the count it must still yield.
  A registered recorder that vanished, or whose reader stopped parsing it,
  fails by name instead of quietly contributing nothing.

## What makes an entry stale

The recorded path is not in the tracked tree and not on disk. Nothing weaker:
a count that no longer matches or a name that no longer resolves are the same
class, but they are per-recorder semantics, and a guard that tried to know all
of them would know none of them well.

## Stale is a FAILURE TO SHRINK, not an inconsistency

Every recorder here is a down-only ratchet: growth is forbidden and an entry is
supposed to be removed in the same commit as the fix that made it wrong. So a
stranded entry is not merely two files disagreeing -- it is a shrink that did
not happen, and the fix is always to remove the entry, never to make the tree
match it. A recorder that shrank correctly leaves nothing behind for this guard
to find, which is why the discrimination costs no extra rule.

Entries are only ever read as **root-relative** paths: a first segment that is
not a top-level directory of this repository is a fragment or a foreign name
(a MIME type, a Hugging Face model id, a ``psf/black`` pre-commit slug), and
reporting those absent would report on a question nobody asked here. That single
condition is what takes the candidate ledgers from 44 to 34 and their false
findings from nine to zero.

## The pre-change advisory

:func:`recorders_naming` answers the other half of #15566's ask: given the paths
a change is about to remove or move, which recorders record them. It turns the
after-the-fact CI failures that motivated this issue into a before-the-fact
list, and it is the same index this guard already builds, so it costs nothing.
"""

from __future__ import annotations

import ast
import json
import re
import subprocess  # nosec B404  # fixed argv, no shell, no caller input
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Callable, Dict, Iterable, List, Sequence, Set, Tuple

from autobot_shared.paths import scrubbed_git_env

REPO_ROOT = Path(__file__).resolve().parents[1]

# Floors bind to the sweep's REACH, never to its findings: a findings floor
# reports a clean tree the moment the walk breaks. Measured when this landed --
# 5,403 files parsed, 34 ledgers plus 5 registered text recorders, 2,630
# recorded entries checked.
MIN_FILES_PARSED = 4000
MIN_LEDGERS_DISCOVERED = 25
MIN_ENTRIES_CHECKED = 1800

EXCLUDED_DIR_NAMES = frozenset({".worktrees", "node_modules", "__pycache__", ".venv", "venv"})

#: A ledger needs this many rooted entries before it is one. Below it, a pair of
#: paths in a tuple is an ordinary constant, not a record of the tree.
MIN_LEDGER_ENTRIES = 3

#: And this share of its string entries must be rooted paths, so a list holding
#: two paths among twenty prose strings is not read as a ledger.
MIN_ROOTED_SHARE = 0.8

_SUFFIXES = "py|yml|yaml|ts|tsx|js|vue|sh|md|json|toml|txt|cfg|ini|service|conf|sql|html|css|j2|pyi|sample"
_FILEISH = re.compile(rf"^[\w.\-/]+\.({_SUFFIXES})$")
_DIRISH = re.compile(r"^[\w.\-]+(/[\w.\-]+)+/?$")


def _one_path_per_line(text: str) -> List[str]:
    """Every non-comment, non-blank line, whole."""
    return [line.strip() for line in text.splitlines() if line.strip() and not line.lstrip().startswith("#")]


def _pipe_field_two(text: str) -> List[str]:
    """Field 2 of a ``count|kind|path|value`` row."""
    rows = (line.split("|") for line in _one_path_per_line(text))
    return [row[2].strip() for row in rows if len(row) > 2]


def _tab_field_zero(text: str) -> List[str]:
    """Field 0 of a tab-delimited row."""
    return [line.split("\t")[0].strip() for line in _one_path_per_line(text)]


def _secrets_baseline_keys(text: str) -> List[str]:
    """The scanned-file keys of a detect-secrets baseline."""
    return sorted(json.loads(text).get("results", {}))


@dataclass(frozen=True)
class TextRecorder:
    """A recorder whose entry format cannot be inferred, so it is registered with its reader.

    ``min_entries`` is re-proved on every run. A registered recorder that lost
    its rows -- renamed columns, a reader that stopped parsing, a file emptied
    by a bad merge -- contributes nothing and would otherwise make the sweep
    look cleaner, which is the failure mode the whole issue is about.
    """

    path: str
    read: Callable[[str], List[str]]
    min_entries: int
    note: str


#: Recorders that hold repository paths as text. Two tracked baselines are
#: deliberately absent: ``scripts/api_wiring_baseline.txt`` records API routes
#: and ``.github/commit-trailer-baseline.txt`` records commit SHAs. Both are
#: recorders in exactly this sense and both can strand, but neither entry is a
#: path, so path-existence is the wrong staleness test for them and pretending
#: otherwise would report every row of both forever.
TEXT_RECORDERS: Tuple[TextRecorder, ...] = (
    TextRecorder(
        "pipeline-scripts/hardcoded_values_baseline.txt",
        _pipe_field_two,
        1000,
        "stranded by resolving three hardcoded values (#15462)",
    ),
    TextRecorder(
        "repo_tests/sys_modules_leak_baseline.txt",
        _one_path_per_line,
        20,
        "stranded by a fixture change, then reverted -- zero net commits (#15524)",
    ),
    TextRecorder(
        "repo_tests/extension_import_baseline.txt",
        _tab_field_zero,
        3,
        "one row per extension whose import boundary is grandfathered",
    ),
    TextRecorder(
        ".secrets.baseline",
        _secrets_baseline_keys,
        0,
        "stranded by removing a directory (#15223); empty today, so the floor is the parse",
    ),
    TextRecorder(
        "autobot-infrastructure/shared/config/.secrets.baseline",
        _secrets_baseline_keys,
        0,
        "the second baseline both sides missed in #15223",
    ),
)

#: Stranded entries, pinned exactly. **Empty, and meant to stay that way.**
#:
#: The first run found exactly one -- ``autobot_shared/ssot_constants/ttl.py``
#: in ``check_no_literal_ttl_seconds.py``'s allowlist, naming a package split of
#: ``ssot_constants`` that never landed -- and it was removed in the same commit
#: as this guard rather than recorded here. That is deliberate: a guard that
#: ships with a baseline on day one turns the baseline into the permanent home
#: of the defect it exists to catch, which is the lesson
#: ``check_no_shell_placeholder_paths`` records at length. The mapping stays as
#: the mechanism a future strand can be parked in *with a reason and an issue*,
#: never as a place to put a finding instead of fixing it.
KNOWN_STRANDED: Dict[str, Tuple[str, ...]] = {}


class Tree:
    """The tracked tree, answering "is this recorded path still here?"."""

    def __init__(self, paths: Iterable[str], root: Path) -> None:
        self.root = root
        self.paths: Set[str] = {p.replace("\\", "/") for p in paths}
        self.top_level: Set[str] = {Path(p).parts[0] for p in self.paths}
        self.directories: Set[str] = {
            str(parent) for p in self.paths for parent in Path(p).parents if str(parent) != "."
        }

    def is_rooted(self, entry: str) -> bool:
        """True when *entry* reads as a path relative to THIS repository's root.

        Without this, a MIME type, a Hugging Face model id and a pre-commit repo
        slug all look like paths, and a ledger of them looks entirely stranded.
        """
        if "/" not in entry or entry.split("/")[0] not in self.top_level:
            return False
        return bool(_FILEISH.match(entry)) or bool(_DIRISH.match(entry))

    def holds(self, entry: str) -> bool:
        trimmed = entry.rstrip("/")
        return trimmed in self.paths or trimmed in self.directories or (self.root / trimmed).exists()


def _string_entries(node: ast.expr) -> List[str]:
    """The string keys or elements of a collection literal, or nothing."""
    if isinstance(node, ast.Dict):
        candidates: Sequence[ast.expr] = [k for k in node.keys if k is not None]
    elif isinstance(node, (ast.Set, ast.List, ast.Tuple)):
        candidates = node.elts
    else:
        return []
    return [n.value for n in candidates if isinstance(n, ast.Constant) and isinstance(n.value, str)]


def ledgers_in(source: str, tree: Tree) -> Dict[str, Tuple[str, ...]]:
    """``{name: entries}`` for every module-level path ledger in *source*.

    Discovered rather than registered: a ledger inside a guard is written by
    whoever writes the guard, and a hand-maintained register of them becomes the
    dormant list this whole check exists to prevent.
    """
    found: Dict[str, Tuple[str, ...]] = {}
    for node in ast.parse(source).body:
        for name, value in _module_level_bindings(node):
            entries = _string_entries(value)
            rooted = [e for e in entries if tree.is_rooted(e)]
            if len(rooted) >= MIN_LEDGER_ENTRIES and len(rooted) >= MIN_ROOTED_SHARE * len(entries):
                found[name] = tuple(rooted)
    return found


def _module_level_bindings(node: ast.stmt) -> List[Tuple[str, ast.expr]]:
    """``(name, value)`` for a top-level assignment, annotated or not."""
    if isinstance(node, ast.Assign):
        return [(t.id, node.value) for t in node.targets if isinstance(t, ast.Name)]
    if isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name) and node.value is not None:
        return [(node.target.id, node.value)]
    return []


@dataclass
class Census:
    """Every recorder found, what it records, and what the sweep touched getting there."""

    records: Dict[str, Tuple[str, ...]]
    files_parsed: int
    ledgers: int

    @property
    def entries(self) -> int:
        return sum(len(v) for v in self.records.values())

    def stranded(self, tree: Tree) -> Dict[str, Tuple[str, ...]]:
        """Recorder -> the entries whose path the tree no longer holds."""
        out: Dict[str, Tuple[str, ...]] = {}
        for recorder, entries in self.records.items():
            gone = tuple(sorted(e for e in entries if not tree.holds(e)))
            if gone:
                out[recorder] = gone
        return out


def _tracked_paths() -> Tuple[str, ...]:
    listed = subprocess.run(  # nosec B603 B607  # fixed argv, no shell
        ["git", "ls-files"],
        cwd=REPO_ROOT,
        capture_output=True,
        text=True,
        encoding="utf-8",
        check=True,
        env=scrubbed_git_env(),
    )
    paths = [line.replace("\\", "/") for line in listed.stdout.splitlines() if line.strip()]
    return tuple(p for p in paths if not any(part in EXCLUDED_DIR_NAMES for part in Path(p).parts))


@lru_cache(maxsize=1)
def _tree() -> Tree:
    return Tree(_tracked_paths(), REPO_ROOT)


@lru_cache(maxsize=1)
def _census() -> Census:
    """Discover every Python ledger, then add every registered text recorder."""
    tree = _tree()
    records: Dict[str, Tuple[str, ...]] = {}
    parsed = ledgers = 0
    for relative in tree.paths:
        if not relative.endswith(".py"):
            continue
        try:
            source = (REPO_ROOT / relative).read_text(encoding="utf-8")
        except (OSError, UnicodeDecodeError):
            continue
        try:
            found = ledgers_in(source, tree)
        except (SyntaxError, ValueError):
            continue
        parsed += 1
        ledgers += len(found)
        records.update({f"{relative}:{name}": entries for name, entries in found.items()})
    records.update(_registered_records())
    return Census(records=records, files_parsed=parsed, ledgers=ledgers)


def _registered_records() -> Dict[str, Tuple[str, ...]]:
    """Every registered text recorder, read through its own reader."""
    out: Dict[str, Tuple[str, ...]] = {}
    tree = _tree()
    for recorder in TEXT_RECORDERS:
        text = (REPO_ROOT / recorder.path).read_text(encoding="utf-8")
        out[recorder.path] = tuple(e for e in recorder.read(text) if tree.is_rooted(e))
    return out


def recorders_naming(paths: Iterable[str]) -> Dict[str, Tuple[str, ...]]:
    """The pre-change advisory: which recorders record any of *paths*.

    Given the paths a change is about to delete or move, this names the
    recorders it will strand -- turning after-the-fact CI failures into a
    before-the-fact list, which is the second half of what #15566 asks for.
    """
    wanted = {p.replace("\\", "/").rstrip("/") for p in paths}
    census = _census()
    return {
        recorder: tuple(sorted(e for e in entries if e.rstrip("/") in wanted))
        for recorder, entries in census.records.items()
        if any(e.rstrip("/") in wanted for e in entries)
    }


def _assert_reach(census: Census) -> None:
    """The vacuity floor. Reach, never findings -- a broken walk must fail by name."""
    assert (
        census.files_parsed >= MIN_FILES_PARSED
    ), f"FIX THE SWEEP: only {census.files_parsed} Python files parsed, floor is {MIN_FILES_PARSED}."
    assert census.ledgers >= MIN_LEDGERS_DISCOVERED, (
        f"FIX THE SWEEP: only {census.ledgers} path ledgers discovered, floor is {MIN_LEDGERS_DISCOVERED}. "
        "The discovery rule stopped recognising ledgers, not the tree stopped having them."
    )
    assert (
        census.entries >= MIN_ENTRIES_CHECKED
    ), f"FIX THE SWEEP: only {census.entries} recorded entries checked, floor is {MIN_ENTRIES_CHECKED}."


def test_the_sweep_reaches_the_population_it_claims():
    """Floor first, so a collapsed sweep fails by name instead of passing vacuously green."""
    _assert_reach(_census())


def test_every_registered_text_recorder_is_present_and_still_parses():
    """A registered recorder that lost its rows would make the sweep look cleaner, not redder."""
    for recorder in TEXT_RECORDERS:
        path = REPO_ROOT / recorder.path
        assert path.is_file(), f"FIX THE SWEEP: registered recorder {recorder.path} is gone ({recorder.note})"
        entries = recorder.read(path.read_text(encoding="utf-8"))
        assert len(entries) >= recorder.min_entries, (
            f"FIX THE SWEEP: {recorder.path} yielded {len(entries)} entries through "
            f"{recorder.read.__name__}, below its recorded {recorder.min_entries}"
        )


def test_the_stranded_census_is_pinned_and_may_only_shrink():
    """No recorder may strand a new entry, and no fixed entry may stay pinned."""
    census = _census()
    _assert_reach(census)
    stranded = census.stranded(_tree())

    new = {
        recorder: tuple(e for e in entries if e not in KNOWN_STRANDED.get(recorder, ()))
        for recorder, entries in stranded.items()
    }
    new = {recorder: entries for recorder, entries in new.items() if entries}
    assert not new, (
        "Recorder entr(ies) name a path the tree no longer holds. A stranded entry is a "
        f"failure to SHRINK: remove it, do not extend the census. {new}"
    )

    healed = {
        recorder: tuple(e for e in entries if e not in stranded.get(recorder, ()))
        for recorder, entries in KNOWN_STRANDED.items()
    }
    healed = {recorder: entries for recorder, entries in healed.items() if entries}
    assert not healed, f"The census over-states the tree -- drop these in the same commit as their fix: {healed}"


# --------------------------------------------------------------------------
# Contrast cases. Each discrimination gets a fixture that must trip it and one
# that must not; without the second half, every one of these would pass just as
# well with its rule deleted.
# --------------------------------------------------------------------------

_FIXTURE_TREE = Tree(
    paths=[
        "autobot_shared/ssot_constants.py",
        "repo_tests/collection_coverage_test.py",
        "tools/lint/check_field_defaults.py",
    ],
    root=Path("/nonexistent-so-only-the-tracked-set-answers"),
)


def test_a_ledger_of_rooted_paths_is_discovered():
    source = (
        "ALLOWLIST = {\n"
        '    "autobot_shared/ssot_constants.py",\n'
        '    "repo_tests/collection_coverage_test.py",\n'
        '    "tools/lint/check_field_defaults.py",\n'
        "}\n"
    )
    assert set(ledgers_in(source, _FIXTURE_TREE)) == {"ALLOWLIST"}


def test_a_ledger_of_foreign_slash_names_is_not_a_path_ledger():
    """MIME types, model ids and pre-commit slugs all contain a slash and record nothing here."""
    source = 'MIME = {"audio/webm": 1, "audio/ogg": 2, "video/mp4": 3, "psf/black": 4}\n'
    assert ledgers_in(source, _FIXTURE_TREE) == {}


def test_a_ledger_of_paths_relative_to_some_other_root_is_not_discovered():
    """`api/knowledge.py` is real, relative to a subtree; absent is not a finding about it."""
    source = 'SOURCES = ["api/knowledge.py", "utils/document_parser.py", "media/document/pipeline.py"]\n'
    assert ledgers_in(source, _FIXTURE_TREE) == {}


def test_two_paths_are_a_constant_not_a_ledger():
    source = 'PAIR = ("autobot_shared/ssot_constants.py", "repo_tests/collection_coverage_test.py")\n'
    assert ledgers_in(source, _FIXTURE_TREE) == {}


def test_a_mostly_prose_list_is_not_a_ledger():
    """The share rule: three real paths among many prose strings is not a record of the tree."""
    prose = ", ".join(f'"reason number {n}"' for n in range(20))
    source = (
        "MIXED = [\n"
        '    "autobot_shared/ssot_constants.py",\n'
        '    "repo_tests/collection_coverage_test.py",\n'
        '    "tools/lint/check_field_defaults.py",\n'
        f"    {prose},\n"
        "]\n"
    )
    assert ledgers_in(source, _FIXTURE_TREE) == {}


def test_a_stranded_entry_is_reported():
    source = 'ALLOWLIST = {"autobot_shared/ssot_constants.py", "repo_tests/collection_coverage_test.py", "tools/lint/gone.py"}\n'
    census = Census(
        records={f"x.py:{k}": v for k, v in ledgers_in(source, _FIXTURE_TREE).items()}, files_parsed=0, ledgers=0
    )
    assert census.stranded(_FIXTURE_TREE) == {"x.py:ALLOWLIST": ("tools/lint/gone.py",)}


def test_a_ledger_whose_paths_all_exist_is_silent():
    """Contrast: the same shape, and the only difference is that the tree still holds them."""
    source = (
        'ALLOWLIST = {"autobot_shared/ssot_constants.py", "repo_tests/collection_coverage_test.py",'
        ' "tools/lint/check_field_defaults.py"}\n'
    )
    census = Census(
        records={f"x.py:{k}": v for k, v in ledgers_in(source, _FIXTURE_TREE).items()}, files_parsed=0, ledgers=0
    )
    assert census.stranded(_FIXTURE_TREE) == {}


def test_the_registered_readers_each_parse_their_own_shape():
    assert _pipe_field_two("1|other|autobot-backend/a2a/__init__.py|https://example\n") == [
        "autobot-backend/a2a/__init__.py"
    ]
    assert _tab_field_zero("plugins/core-plugins/x/main.py\ttools\n") == ["plugins/core-plugins/x/main.py"]
    assert _one_path_per_line("# comment\n\nautobot-backend/conftest.py\n") == ["autobot-backend/conftest.py"]
    assert _secrets_baseline_keys('{"results": {"a/b.py": []}}') == ["a/b.py"]


def test_the_advisory_names_the_recorders_a_change_would_strand():
    """#15566's other half: given what a change removes, say what records it."""
    census = _census()
    _assert_reach(census)
    recorder, entries = next((r, e) for r, e in sorted(census.records.items()) if e)
    naming = recorders_naming([entries[0]])
    assert recorder in naming and entries[0] in naming[recorder]


def test_the_advisory_names_nothing_for_a_path_no_recorder_holds():
    """Contrast: an advisory that answers for every path answers for none."""
    assert recorders_naming(["no/such/path.py"]) == {}
