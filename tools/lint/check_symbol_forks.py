# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Find one concept defined under one name in several modules (#17312, #12771).

The duplication guard measures **clones** -- jscpd pairs of >=8 identical lines.
The expensive problem is **forks**: four modules that each define `ConfidenceLevel`
and have since drifted. Identical copies cannot disagree; drifted ones hand a
caller different behaviour depending on which import it reached, and they score
ZERO against a clone metric. #17312 measured exactly that: four redaction
implementations, 1164 lines, `Found 0 clones`.

This detector asks the question the clone metric cannot: **how many modules
define this name at top level?**

THE BOUNDARY (ratchet rule 1 -- state it where the reader meets the number)
--------------------------------------------------------------------------
Population: files returned by `git ls-files '*.py'` under ROOTS, minus EXCLUDED.
Predicate:  a *fork cluster* is one symbol NAME bound by a **module-level**
            `class`, `def` or `async def` in **two or more distinct files**.

What this detector is BLIND to, stated because a baseline cannot record what
its detector never saw:

  - **Methods.** Only module-level statements are read. Two classes with a
    `validate()` each are not a cluster; overriding is how classes work.
  - **Differently-named forks.** `redact_secrets` vs `scrub_credentials` are one
    concept and this never pairs them. Name identity is the whole signal, so
    the number is a FLOOR on canonical debt, never a total.
  - **Non-Python.** Vue/TS have their own canonical check (#7458).
  - **Conditional definitions.** A `def` inside `if TYPE_CHECKING:` or a
    try/except fallback is not module-level and is not counted.
  - **Re-exports.** `from x import Foo` does not define `Foo` here, correctly;
    but a module that aliases and subclasses will read as a second definition.
  - **Route handlers.** A function decorated `@router.get(...)` / `@app.post(...)`
    is excluded. Its name is local to its own router, so eight modules each
    defining `test_connection` are eight endpoints, not eight forks. Dropping
    this exclusion makes the top of the report entirely false positives -- it
    was the first thing the first run got wrong.

A cluster is a QUESTION, not a verdict. `ValidationResult` in seven modules may
be seven forks of one idea or seven unrelated local result types. The detector
says where to look and who the likely canonical is; a human decides.
"""

from __future__ import annotations

import argparse
import ast
import json
import sys
from collections import defaultdict
from dataclasses import dataclass, field
from pathlib import Path

from _scan_helpers import tracked_paths

_REPO_ROOT = Path(__file__).resolve().parents[2]

ROOTS = ("autobot-backend", "autobot-slm-backend", "autobot_shared")

# Directory parts that take a file out of the population entirely.
EXCLUDED_PARTS = frozenset({"__pycache__", "node_modules", "venv", ".venv", "migrations", "alembic"})

# Names whose repetition across modules is the intended design, not a fork.
# `main` is a script entry point; alembic revisions each define upgrade/downgrade
# (and their directories are excluded too, so this is belt and braces).
EXCLUDED_NAMES = frozenset({"main", "upgrade", "downgrade", "migrate"})

#: Floor on files successfully PARSED — not on files listed, and never on
#: findings. "0 new clusters" is meaningless if the sweep collapsed, and a
#: findings-based floor cannot tell a clean tree from a broken enumeration.
#: git lists ~5,279 python files; ~2,826 survive `in_population` and are
#: parsed. 2,000 sits under that and well over any plausible collapse.
MIN_FILES_PARSED = 2000

BASELINE = _REPO_ROOT / "repo_tests" / "symbol_fork_baseline.json"


def is_test_file(path: Path) -> bool:
    """Tests legitimately redefine names: fixtures, fakes, back-compat shims."""
    name = path.name
    return name.endswith("_test.py") or name.startswith("test_") or "tests" in path.parts


#: A MANDATORY byte-identical mirror, not a fork (#16401). Ansible ships
#: `autobot-slm-backend/slm/agent/` to the target host from
#: `autobot-slm-backend/ansible/roles/slm_agent/files/slm/agent/`, and
#: `ansible/tests/detect_agent_code_drift_test.py` fails if the two trees differ.
#: So every symbol there is defined twice BY DESIGN and must stay that way —
#: consolidating one would break the payload or the drift test.
#:
#: `duplication-guard.yml` already excludes this path for the same reason, with the
#: same wording: "there is nothing here this guard can ask anyone to deduplicate."
#: This detector did not, so 17 of the clusters it counted were that mirror. A
#: ratchet whose population includes entries nobody may touch reports a floor it
#: can never reach, and sends whoever works it toward a change that breaks a test.
#: Excluded here so the count means ACTIONABLE forks.
MIRRORED_PREFIX = "autobot-slm-backend/ansible/roles/slm_agent/files/"


def is_mandatory_mirror(path: Path) -> bool:
    """True for the ansible payload copy of `autobot-slm-backend/slm/agent/`."""
    return path.as_posix().startswith(MIRRORED_PREFIX)


def in_population(path: Path) -> bool:
    """The declared boundary, in one place so the test can pin it."""
    if EXCLUDED_PARTS & set(path.parts):
        return False
    if is_mandatory_mirror(path):
        return False
    return not is_test_file(path)


def tracked_python_files() -> list[Path]:
    """`git ls-files` rather than a walk: untracked scratch files are not the tree."""
    # `tracked_paths` rather than a hand-rolled `git ls-files`: an inherited
    # GIT_DIR outranks `cwd=`, so a bare call run from one worktree can
    # enumerate ANOTHER checkout's index and answer confidently about the wrong
    # tree (#14896, #15176). With 14 live worktrees here that is not theoretical.
    #
    # NOT `<root>/**/*.py`: that pathspec silently misses files sitting directly
    # in a root (autobot-backend/circuit_breaker.py and ~40 others), which made
    # the first frozen baseline 324 instead of 365. Match on the roots and
    # filter the extension here, where the rule is visible.
    tracked = tracked_paths(_REPO_ROOT, *ROOTS, exclude=sorted(EXCLUDED_PARTS))
    return [Path(rel) for rel in tracked if rel.endswith(".py")]


@dataclass
class Definition:
    """One module-level binding of a name."""

    path: str
    lineno: int
    kind: str
    body_statements: int


@dataclass
class Cluster:
    """One name, defined at module level in two or more files."""

    name: str
    definitions: list[Definition] = field(default_factory=list)

    @property
    def kinds(self) -> set[str]:
        return {d.kind for d in self.definitions}

    @property
    def drifted(self) -> bool:
        """Different body sizes mean the copies are not the same text any more.

        This is an indicator, not proof: two definitions can differ in size and
        still be one concept correctly specialised. It is here because a clone
        metric reports the *opposite* signal -- identical copies score high and
        drifted ones score zero.
        """
        return len({d.body_statements for d in self.definitions}) > 1


def is_route_handler(node: ast.AST) -> bool:
    """True for `@router.get(...)`-style decorators.

    A route handler's name is scoped to its own router, so the same name in
    several API modules is normal design. Without this, the loudest clusters
    are all endpoints and the real forks are buried under them.
    """
    for dec in getattr(node, "decorator_list", []):
        func = dec.func if isinstance(dec, ast.Call) else dec
        if isinstance(func, ast.Attribute) and isinstance(func.value, ast.Name):
            if func.value.id in ("router", "app", "api_router"):
                return True
    return False


def definitions_in(path: Path) -> "list[tuple[str, Definition]] | None":
    """Module-level class/def bindings. Nested and conditional defs are out of scope."""
    try:
        tree = ast.parse((_REPO_ROOT / path).read_text(encoding="utf-8"))
    except (SyntaxError, OSError):
        # None, not [] — "could not read this file" is a different fact from
        # "read it and it defines nothing", and the reach floor below counts
        # successful PARSES, so the two must not be conflated.
        return None
    found = []
    for node in tree.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)):
            kind = "function"
        elif isinstance(node, ast.ClassDef):
            kind = "class"
        else:
            continue
        if node.name.startswith("_") or node.name in EXCLUDED_NAMES:
            continue
        if is_route_handler(node):
            continue
        found.append((node.name, Definition(str(path), node.lineno, kind, len(node.body))))
    return found


def find_clusters(paths: list[Path]) -> "tuple[dict[str, Cluster], int]":
    """Group module-level definitions by name; keep those bound in >=2 files.

    Returns the clusters AND the number of files successfully PARSED, which is
    what the vacuity floor binds to. `len(paths)` counts what git listed, so a
    broken `in_population` or a tree of unparsable files would clear a floor on
    it while the sweep saw almost nothing (CodeRabbit).
    """
    by_name: dict[str, list[Definition]] = defaultdict(list)
    parsed = 0
    for path in paths:
        if not in_population(path):
            continue
        found = definitions_in(path)
        if found is None:
            continue
        parsed += 1
        for name, definition in found:
            by_name[name].append(definition)
    clusters = {}
    for name, defs in by_name.items():
        if len({d.path for d in defs}) > 1:
            clusters[name] = Cluster(name, sorted(defs, key=lambda d: (d.path, d.lineno)))
    return clusters, parsed


def canonical_candidate(cluster: Cluster, import_counts: dict[str, int]) -> Definition:
    """The member a consolidation should merge INTO.

    Ranked by call sites first -- the copy most code already depends on is the
    one whose removal costs most. `autobot_shared` breaks ties because the
    project's rule 2 is to reuse from there. Size is the last resort and the
    weakest signal: the biggest copy may simply be the one that rotted most.
    """

    def rank(d: Definition) -> tuple[int, int, int]:
        return (
            import_counts.get(d.path, 0),
            1 if d.path.startswith("autobot_shared/") else 0,
            d.body_statements,
        )

    return max(cluster.definitions, key=rank)


def count_importers(paths: list[Path], names: set[str]) -> dict[str, dict[str, int]]:
    """For each name, how many files import it from each defining module.

    Counts `from <module> import <name>`. A bare `import module` followed by
    attribute use is NOT counted -- stated because it makes these numbers a
    floor, and a member with 0 here may still have callers.
    """
    counts: dict[str, dict[str, int]] = defaultdict(lambda: defaultdict(int))
    for path in paths:
        try:
            tree = ast.parse((_REPO_ROOT / path).read_text(encoding="utf-8"))
        except (SyntaxError, OSError):
            continue
        for node in ast.walk(tree):
            if not isinstance(node, ast.ImportFrom) or not node.module:
                continue
            for alias in node.names:
                if alias.name in names:
                    counts[alias.name][node.module] += 1
    return {k: dict(v) for k, v in counts.items()}


def module_of(path: str) -> str:
    """Dotted module path as an importer would spell it, for both root layouts."""
    stem = path[:-3] if path.endswith(".py") else path
    parts = stem.split("/")
    if parts[0] in ("autobot-backend", "autobot-slm-backend"):
        parts = parts[1:]
    if parts and parts[-1] == "__init__":
        parts = parts[:-1]
    return ".".join(parts)


def importers_by_path(cluster: Cluster, by_module: dict[str, int]) -> dict[str, int]:
    """Re-key the per-module import counts onto each definition's file path."""
    return {d.path: by_module.get(module_of(d.path), 0) for d in cluster.definitions}


def format_cluster(cluster: Cluster, import_counts: dict[str, int]) -> str:
    """One cluster as a reviewable recommendation."""
    winner = canonical_candidate(cluster, import_counts)
    kinds = "/".join(sorted(cluster.kinds))
    lines = [
        f"{cluster.name}  ({kinds}, {len(cluster.definitions)} definitions" f"{', DRIFTED' if cluster.drifted else ''})"
    ]
    for d in cluster.definitions:
        mark = "  <- canonical candidate" if d is winner else ""
        lines.append(
            f"    {d.path}:{d.lineno}  {d.body_statements} stmts, {import_counts.get(d.path, 0)} importers{mark}"
        )
    lines.append(
        f"    FIX: merge the others into {winner.path} and re-point importers, or rename each to its own concept."
    )
    return "\n".join(lines)


def load_baseline() -> set[str]:
    if not BASELINE.exists():
        return set()
    return set(json.loads(BASELINE.read_text(encoding="utf-8"))["clusters"])


def write_baseline(names: set[str]) -> None:
    BASELINE.write_text(
        json.dumps(
            {
                "_boundary": (
                    "Names bound by a MODULE-LEVEL class/def in >=2 tracked .py files under "
                    f"{list(ROOTS)}, excluding {sorted(EXCLUDED_PARTS)} dirs, test files, "
                    f"underscore-prefixed names and {sorted(EXCLUDED_NAMES)}. "
                    "Methods, differently-named forks and non-Python are NOT seen -- "
                    "this count is a FLOOR on canonical debt. See tools/lint/check_symbol_forks.py."
                ),
                "_contract": (
                    "Shrink-only and BIDIRECTIONAL: a new name here fails CI, and an entry "
                    "that is no longer a fork cluster fails just as loudly. Delete it when "
                    "the duplication goes, or it tolerates whatever takes that name next "
                    "(#17312)."
                ),
                "clusters": sorted(names),
            },
            indent=2,
        )
        + "\n",
        encoding="utf-8",
    )


def _report(clusters: dict[str, Cluster], paths: list[Path], limit: int) -> None:
    by_name = count_importers(paths, set(clusters))
    ranked = sorted(clusters.values(), key=lambda c: (-len(c.definitions), c.name))
    for cluster in ranked[:limit]:
        print(format_cluster(cluster, importers_by_path(cluster, by_name.get(cluster.name, {}))))
        print()
    print(f"{len(clusters)} fork clusters (showing {min(limit, len(clusters))}).")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--report", action="store_true", help="print clusters with canonical recommendations")
    parser.add_argument("--limit", type=int, default=25, help="clusters to print in --report")
    parser.add_argument("--freeze", action="store_true", help="rewrite the baseline from the current tree")
    parser.add_argument("--audit-baseline", action="store_true", help="list baseline entries that no longer exist")
    args = parser.parse_args(argv)

    paths = tracked_python_files()
    clusters, parsed = find_clusters(paths)
    # Floor on files successfully PARSED, not on files git listed and not on
    # findings. `len(paths)` would clear this floor even if `in_population`
    # filtered everything out or every parse failed, which is the exact
    # collapse it exists to catch (CodeRabbit).
    if parsed < MIN_FILES_PARSED:
        print(
            f"check_symbol_forks: parsed only {parsed} of {len(paths)} listed python file(s), "
            f"expected at least {MIN_FILES_PARSED} — the sweep collapsed, so this run has no "
            "verdict to give. A floor on REACH, not on findings (#17312).",
            file=sys.stderr,
        )
        return 2

    if args.report:
        _report(clusters, paths, args.limit)
        return 0
    if args.freeze:
        write_baseline(set(clusters))
        print(f"froze {len(clusters)} clusters into {BASELINE.relative_to(_REPO_ROOT)}")
        return 0

    baseline = load_baseline()
    if args.audit_baseline:
        stale = sorted(baseline - set(clusters))
        for name in stale:
            print(f"STALE baseline entry (no longer a cluster): {name}")
        print(f"{len(stale)} stale of {len(baseline)}.")
        return 0

    # Shrink-only AND bidirectional: a NEW cluster fails, and a STALE entry
    # fails just as loudly. A baseline still listing a name nobody defines twice
    # any more is dead policy, and it silently tolerates whatever appears under
    # that name next. `--audit-baseline` reports staleness; this ENFORCES it.
    new = sorted(set(clusters) - baseline)
    stale = sorted(baseline - set(clusters))

    if new:
        by_name = count_importers(paths, set(new))
        print(f"{len(new)} NEW fork cluster(s) — one name, several module-level definitions (#17312):\n")
        for name in new:
            print(format_cluster(clusters[name], importers_by_path(clusters[name], by_name.get(name, {}))))
            print()
        print("Give the new concept its own name, or extend the existing definition instead of adding one.")
    if stale:
        print(
            f"{len(stale)} baseline entry(ies) are no longer fork clusters: {stale[:10]}\n"
            "Delete them. The list may only shrink, and it has to shrink HERE when the "
            "duplication is gone — otherwise the entry tolerates whatever takes that name next."
        )
    if new or stale:
        return 1
    print(
        f"symbol forks: {len(clusters)} clusters over {parsed} parsed files "
        f"({len(paths)} listed), none new and none stale against a baseline of {len(baseline)}."
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
