#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Pre-commit hook: block new local BaseModel subclasses in non-schema API endpoint files.

Schema migration work (#5799, #5996) moved 375+ classes from endpoint files into
domain schemas_*.py files. Without enforcement, local schemas will be re-introduced
over time. This hook prevents that regression.

Scan target:
  autobot-backend/api/*.py  — NOT schemas_*.py files

Allowlisted files (tightly-coupled domain logic, exempt by design):
  workflow_state.py  — WorkflowState tightly coupled with WorkflowStateMachine;
                       circular import risk if extracted (per #5996 audit)

Changed-lines scoping (#16178):
  --changed-lines-only           count only models whose ``class`` line this
                                 change ADDED, read from the staged diff
  --changed-lines-only --base R  the same, read from ``R..HEAD`` (the PR stage;
                                 the CI wrapper passes the base it resolved)
  Unscoped, the hook reads each file whole. That is what a direct run is for, and
  it is also what used to fail a change for a model it never touched. Scoped, a
  pre-existing model is listed as not counted rather than hidden, and a git
  failure fails the run rather than reading as "added nothing".
  Under pre-commit's --from-ref/--to-ref (CI's enforce-precommit job) nothing is
  staged, so the hook reads PRE_COMMIT_FROM_REF..HEAD instead. A file passed but
  not staged (``--all-files``, ``--files``) has no change to scope to and is
  judged whole-file.

Where a model goes — companion modules, not a re-split (owner ruling, #16178):
  The seven original domain modules (schemas_agent, _analytics, _chat, _code,
  _knowledge, _system, _workflows) sit at their file-size ceiling and may not
  grow, so a new model cannot go into them. It goes into a companion named for
  its domain and topic, schemas_<domain>_<topic>.py, as schemas_agent_requests.py
  and schemas_chat_rows.py already are. A frozen module shrinks only when a model
  moves out while its code is being worked on. The violation message computes
  every module's headroom from the file-size guard's own ceilings instead of
  naming a fixed list, so it cannot direct anyone into a file that refuses them.

Exit codes:
  0 — clean (scoped: nothing this change added)
  1 — violations found, or the added-line set could not be computed
  2 — invalid arguments

Background: #5799 (schemas_common.py split), #5996 (terminal/analytics/knowledge model
merges), #6056 (this hook), #16178 (changed-lines scoping, headroom-aware guidance).
"""

from __future__ import annotations

import argparse
import ast
import importlib.util
import os
import sys
from pathlib import Path
from typing import List, Sequence, Tuple

sys.path.insert(0, str(Path(__file__).resolve().parent))

from _scan_helpers import PY_FLOOR, added_lines, enforce_reach, scan_python_files, staged_paths  # noqa: E402

HOOK_ID = "no-local-schemas"

# Files in autobot-backend/api/ that are exempt from the check.
# Filename only (no directory prefix) — matched against path.name.
ALLOWLISTED_FILENAMES: frozenset[str] = frozenset(
    {
        "workflow_state.py",  # WorkflowState tightly coupled with WorkflowStateMachine (#5996)
    }
)

# The file-size guard owns the ceilings. Loaded by path so this hook reports the
# numbers that guard enforces, not a copy that drifts from them (#16178).
_SIZE_GUARD_REL = "scripts/check_python_file_size.py"
_KNOWN_LARGE_REL = "scripts/python_file_size_known_large.py"
_SCHEMAS_GLOB = "autobot-backend/api/schemas_*.py"

#: (repo-relative path, line, class name)
Hit = Tuple[str, int, str]


def _is_target_file(path: Path, repo_root: Path) -> bool:
    """Return True if *path* should be scanned by this hook.

    Conditions:
    - Resolves to within autobot-backend/api/
    - NOT named schemas_*.py
    - NOT in the allowlist
    """
    try:
        rel = path.resolve().relative_to(repo_root)
    except ValueError:
        return False

    parts = rel.parts
    # Must be inside autobot-backend/api/ (exactly — not a sub-package)
    if len(parts) < 3 or parts[0] != "autobot-backend" or parts[1] != "api":
        return False

    name = path.name
    if name.startswith("schemas_"):
        return False
    if name in ALLOWLISTED_FILENAMES:
        return False
    return True


def _basemodel_subclasses(tree: ast.Module) -> List[Tuple[int, str]]:
    """Return [(line_no, class_name)] for each BaseModel subclass in *tree*.

    Uses AST ClassDef nodes. A class is considered a BaseModel subclass when
    any of its bases is:
      - ast.Name with id == "BaseModel"
      - ast.Attribute with attr == "BaseModel"  (e.g. pydantic.BaseModel)
    """
    hits: List[Tuple[int, str]] = []
    for node in ast.walk(tree):
        if not isinstance(node, ast.ClassDef):
            continue
        for base in node.bases:
            if isinstance(base, ast.Name) and base.id == "BaseModel":
                hits.append((node.lineno, node.name))
                break
            if isinstance(base, ast.Attribute) and base.attr == "BaseModel":
                hits.append((node.lineno, node.name))
                break
    return hits


def _check_file(path: Path, repo_root: Path) -> List[Tuple[int, str]]:
    """Return [(line_no, class_name)] for each BaseModel subclass violation in *path*.

    Returns an empty list when:
    - The file is not a scan target
    - The file cannot be parsed (syntax error, encoding error, missing file)
    - No BaseModel subclasses are found
    """
    if not _is_target_file(path, repo_root):
        return []

    try:
        source = path.read_text(encoding="utf-8")
        tree = ast.parse(source, filename=str(path))
    except (SyntaxError, UnicodeDecodeError, OSError):
        return []

    return _basemodel_subclasses(tree)


def _collect_hits(files: Sequence[Path], repo_root: Path) -> List[Hit]:
    """Every violation in *files*, keyed by repo-relative path."""
    hits: List[Hit] = []
    for path in files:
        for line_no, class_name in _check_file(path, repo_root):
            try:
                rel = path.resolve().relative_to(repo_root.resolve()).as_posix()
            except ValueError:
                rel = str(path)
            hits.append((rel, line_no, class_name))
    return hits


def _split_by_added(hits: List[Hit], repo_root: Path, base: str | None) -> Tuple[List[Hit], List[Hit], List[str]]:
    """Partition *hits* into (added by this change, pre-existing), plus files judged whole.

    Only files that have a hit cost a git call. A model counts as added when its
    ``class`` line is one the change added. In staged mode a file with no staged
    change at all is not part of the commit, so an empty diff for it is not
    "nothing added": its hits are counted and the file reported as unscoped.
    """
    staged = staged_paths(repo_root) if base is None else None
    added: dict[str, set[int]] = {}
    new: List[Hit] = []
    earlier: List[Hit] = []
    unscoped: List[str] = []
    for rel, line, name in hits:
        if staged is not None and rel not in staged:
            new.append((rel, line, name))
            if rel not in unscoped:
                unscoped.append(rel)
            continue
        if rel not in added:
            added[rel] = added_lines(repo_root, rel, base)
        (new if line in added[rel] else earlier).append((rel, line, name))
    return new, earlier, unscoped


def _load_module(repo_root: Path, rel: str):
    """Import the module at *rel* by path, without putting scripts/ on sys.path."""
    spec = importlib.util.spec_from_file_location(f"_nls_{Path(rel).stem}", repo_root / rel)
    if spec is None or spec.loader is None:
        raise ImportError(f"cannot load {rel}")
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _headroom_rows(repo_root: Path) -> List[Tuple[str, int, int]]:
    """(filename, lines, ceiling) for every schemas_*.py module, most headroom first."""
    guard = _load_module(repo_root, _SIZE_GUARD_REL)
    known_large = _load_module(repo_root, _KNOWN_LARGE_REL).KNOWN_LARGE
    rows: List[Tuple[str, int, int]] = []
    for path in sorted(repo_root.glob(_SCHEMAS_GLOB)):
        lines = guard.count_lines(path)
        if path.name.endswith("_test.py") or lines is None:
            continue
        rel = path.relative_to(repo_root).as_posix()
        rows.append((path.name, lines, known_large.get(rel, guard.MAX_LINES)))
    return sorted(rows, key=lambda row: row[1] - row[2])


def _destination_guide(repo_root: Path) -> str:
    """Where a model can go: every schemas_*.py by headroom, frozen ones marked."""
    try:
        rows = _headroom_rows(repo_root)
    except Exception as exc:  # noqa: BLE001 -- advice must not mask the verdict; the failure is printed
        return f"  (headroom unavailable: could not read the file-size ceilings: {exc})"
    fits = [
        f"    {name:34s} {lines:5d} / {ceiling:<5d} (+{ceiling - lines})"
        for name, lines, ceiling in rows
        if lines < ceiling
    ]
    frozen = [f"    {name:34s} {lines:5d} / {ceiling}" for name, lines, ceiling in rows if lines >= ceiling]
    parts = ["  Modules with headroom under the file-size ceiling:", *fits]
    if frozen:
        parts += ["  Frozen at their ceiling, add a companion schemas_<domain>_<topic>.py instead (#16178):", *frozen]
    return "\n".join(parts)


def _report(new: List[Hit], earlier: List[Hit], repo_root: Path) -> int:
    """Print the verdict; a pre-existing model is listed, never hidden."""
    for rel, line, name in earlier:
        print(
            f"[{HOOK_ID}] not counted (pre-existing, not added by this change): {rel}:{line} '{name}'", file=sys.stderr
        )
    if not new:
        return 0
    for rel, line, name in new:
        print(f"[{HOOK_ID}] {rel}:{line}: Local BaseModel subclass '{name}' found.", file=sys.stderr)
    print(
        f"\n[{HOOK_ID}] {len(new)} violation(s). Move each model to a schemas_*.py module (#6056).\n"
        f"{_destination_guide(repo_root)}",
        file=sys.stderr,
    )
    return 1


def _resolve_base(explicit: str | None) -> str | None:
    """The range to scope to: an explicit --base, else the one pre-commit ran with.

    ``pre-commit run --from-ref A --to-ref B`` stages nothing, so the staged diff is
    empty and every model would read as pre-existing. pre-commit exports the range
    as PRE_COMMIT_FROM_REF (commands/run.py); FROM_REF..HEAD then describes the
    checked-out tree the hook is actually reading (#16178).
    """
    return explicit or os.environ.get("PRE_COMMIT_FROM_REF") or None


def run(files: Sequence[Path], repo_root: Path, *, changed_only: bool, base: str | None) -> int:
    """Check *files* under *repo_root*. Whether to scope is the caller's to state."""
    hits = _collect_hits(files, repo_root)
    if not changed_only:
        return _report(hits, [], repo_root)
    try:
        new, earlier, unscoped = _split_by_added(hits, repo_root, base)
    except RuntimeError as exc:
        print(
            f"[{HOOK_ID}] FATAL: could not compute the added-line set, refusing to report clean: {exc}", file=sys.stderr
        )
        return 1
    for rel in unscoped:
        print(f"[{HOOK_ID}] {rel}: not staged, so there is no change to scope to; judged whole-file", file=sys.stderr)
    return _report(new, earlier, repo_root)


def _parse_args(argv: Sequence[str]) -> argparse.Namespace:
    parser = argparse.ArgumentParser(prog=HOOK_ID, description=__doc__.splitlines()[0])
    parser.add_argument("files", nargs="*")
    parser.add_argument("--changed-lines-only", action="store_true", help="count only models this change added")
    parser.add_argument("--base", help="with --changed-lines-only: read BASE..HEAD instead of the staged diff")
    args = parser.parse_args(argv)
    if args.base and not args.changed_lines_only:
        parser.error("--base only means something with --changed-lines-only")
    if args.changed_lines_only and not args.files:
        parser.error("--changed-lines-only needs the files to scope; a full-repo scan has no change to scope to")
    return args


def main(argv: List[str]) -> int:
    args = _parse_args(argv[1:])
    repo_root = Path(__file__).resolve().parents[2]
    files, full_repo = scan_python_files(args.files, repo_root)
    # Vacuity floor (#14896): full-repo mode only -- pre-commit legitimately
    # hands this hook an argv with no Python in it.
    if enforce_reach(len(files), PY_FLOOR, hook=HOOK_ID, full_repo=full_repo):
        return 1
    return run(files, repo_root, changed_only=args.changed_lines_only, base=_resolve_base(args.base))


if __name__ == "__main__":
    sys.exit(main(sys.argv))
