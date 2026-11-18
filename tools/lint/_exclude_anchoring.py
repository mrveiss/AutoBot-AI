# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Decision helpers shared by the bandit and flake8 exclude-anchoring guards (#14896, #18954).

``check_bandit_exclude_anchoring`` and ``check_flake8_exclude_anchoring`` carried
copies of :func:`unanchored_source_entries`, :func:`tracked_py_files`,
:func:`bare_entries`, :func:`entries_covering_tracked_python`,
:func:`load_entries` and the whole :func:`audit_excludes` skeleton. They differ
only in what their tool's matcher counts as "bare" or as "covering" and in the
wording and extra checks of their findings, so those are the parameters; each
guard binds them once and keeps only its tool-specific parts.

Stdlib-only: ``yaml`` is imported inside :func:`read_bandit_exclude_dirs`, the
one reader that needs it, so the flake8 guard still runs wherever Python does.
"""

from __future__ import annotations

import configparser
import pathlib
import re
import sys
from typing import Callable, Collection

sys.path.insert(0, str(pathlib.Path(__file__).resolve().parent))

from _scan_helpers import tracked_paths  # noqa: E402

from autobot_shared.paths import project_root  # noqa: E402

#: Mirror of ``flake8.utils.COMMA_SEPARATED_LIST_RE``. Reimplemented rather than
#: imported so this runs wherever Python does -- a guard that skips itself when a
#: dependency is missing reports clean. The flake8 test pins the mirror to the
#: real parser wherever flake8 is importable.
_SPLIT_RE = re.compile(r"[,\s]")

#: One entry of a guard's ordered checks: ``(entries, root) -> problem or None``.
Check = Callable[[list[str], pathlib.Path], "str | None"]


def unanchored_source_entries(
    entries: list[str],
    bare_entries: Callable[[list[str]], list[str]],
    artifact_names: Collection[str],
) -> list[str]:
    """Bare entries (per *bare_entries*) that are not a sanctioned artifact name.

    The decision the guards turn on, kept separate so callers can put a
    synthetic list through it instead of asserting on the config's text.
    """
    return [entry for entry in bare_entries(entries) if entry not in artifact_names]


def tracked_py_files(root: pathlib.Path | None = None) -> list[str]:
    """Every tracked ``*.py`` path under *root* (default: the project root), enumerated by git.

    Through the shared enumerator so the scrubbed git environment is not a
    per-hook repeat, and a failed or empty listing raises instead of reading as
    "the tool excludes nothing".
    """
    return tracked_paths(root if root is not None else project_root(), "*.py")


def bare_entries(entries: list[str], separators: str, skip_globs: bool) -> list[str]:
    """Entries a tool matches at any depth: none of *separators*, and no ``*`` when *skip_globs*.

    bandit tests a bare entry as a raw substring and reaches an entry holding
    ``*`` only through ``fnmatch`` (``skip_globs``); flake8 compares it to a
    basename and treats ``\\`` as a separator too.
    """
    return [
        entry for entry in entries if not any(sep in entry for sep in separators) and not (skip_globs and "*" in entry)
    ]


def entries_covering_tracked_python(
    entries: list[str],
    tracked: list[str],
    bare: Callable[[list[str]], list[str]],
    hits_in_path: Callable[[str, str], int],
) -> dict[str, int]:
    """Bare entries that cover tracked Python, mapped to how many hits, in config order.

    *hits_in_path* is the tool's OWN matcher (bandit: substring of the full
    path; flake8: a directory component equal to the entry). Verifying against
    any other predicate is how a guard for this bug would itself fail open.
    """
    counts: dict[str, int] = {}
    for entry in dict.fromkeys(bare(entries)):
        hits = sum(hits_in_path(entry, path) for path in tracked)
        if hits:
            counts[entry] = hits
    return counts


def read_bandit_exclude_dirs(config_text: str) -> list[str]:
    """Parsed ``exclude_dirs`` entries of a bandit config given as YAML text.

    PyYAML because that is what ``bandit.core.config.BanditConfig`` uses to
    read ``.bandit`` -- a hand-rolled parser could drift from bandit's own YAML
    rules (e.g. comment stripping) in a way that hides an entry from the audit.
    """
    import yaml

    parsed = yaml.safe_load(config_text) or {}
    return [str(entry) for entry in parsed.get("exclude_dirs") or []]


def split_exclude_value(value: str) -> list[str]:
    """Split an ``exclude`` option exactly as flake8 does."""
    return [item for item in (piece.strip() for piece in _SPLIT_RE.split(value)) if item]


def read_flake8_exclude(config_text: str) -> list[str]:
    """Parsed ``exclude`` entries of a flake8 config given as text.

    ``RawConfigParser`` because that is what ``flake8.options.config.load_config``
    uses; interpolation would change what a ``%`` in the value means.
    """
    parser = configparser.RawConfigParser()
    parser.read_string(config_text)
    return split_exclude_value(parser["flake8"]["exclude"])


def load_entries(
    config_path: pathlib.Path | None = None,
    *,
    default_name: str,
    reader: Callable[[str], list[str]],
) -> list[str]:
    """Exclude entries of the repo's *default_name* config (or a given one), parsed by *reader*."""
    path = config_path if config_path is not None else project_root() / default_name
    return reader(path.read_text(encoding="utf-8"))


def coverage_problem(
    base: pathlib.Path,
    entries: list[str],
    problems: list[str],
    *,
    covering: Callable[[list[str], list[str]], dict[str, int]],
    describe: Callable[[dict[str, int]], str],
    floor: int,
) -> None:
    """Append what the tracked-Python coverage pass finds (or why it could not run) to *problems*.

    A failed or empty listing is a problem here instead of propagating: the
    anchoring findings already collected are still worth printing, and this
    path is already a nonzero exit (#14896).
    """
    try:
        tracked = tracked_py_files(base)
    except RuntimeError as exc:
        tracked = []
        problems.append(str(exc))
    if len(tracked) < floor:
        problems.append(
            f"git ls-files returned only {len(tracked)} Python files (floor "
            f"{floor}) — the enumeration broke, so the coverage "
            "check below asserted nothing."
        )
        return
    covered = covering(entries, tracked)
    if covered:
        problems.append(describe(covered))


def audit_excludes(
    root: pathlib.Path | None = None,
    *,
    config_name: str,
    load: Callable[[pathlib.Path], list[str]],
    key: str,
    before: tuple[Check, ...],
    coverage: Callable[[pathlib.Path, list[str], list[str]], None],
    after: tuple[Check, ...],
) -> tuple[int, list[str]]:
    """Apply a tool's invariant to every entry of its exclude config.

    Returns ``(entries_reached, problems)``. ``entries_reached`` is counted from
    the parsed list so a config whose *key* has gone missing or empty cannot
    report a clean scan of nothing. Order of findings: *before* checks, the
    tracked-Python *coverage* pass, then *after* checks.
    """
    base = root if root is not None else project_root()
    entries = load(base / config_name)
    if not entries:
        return 0, [f"{base / config_name} parsed to zero {key} entries — the guard checked nothing."]
    problems = [message for check in before if (message := check(entries, base)) is not None]
    coverage(base, entries, problems)
    problems.extend(message for check in after if (message := check(entries, base)) is not None)
    return len(entries), problems
