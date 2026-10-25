# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The base a change is ratcheted against, read fail-closed (#19283).

Down-only ratchets used hand-maintained totals (MAX_CEILING_TOTAL, TOTAL_OCCURRENCES,
css_rule_declarations) or a second mirrored table, so that raising an entry would show up
somewhere. Every PR that lowered a different entry also edited that one total line, and two
such PRs always conflicted. The tripwire here is the base commit instead: each entry must not
exceed what the same table said at the base, and an entry the base did not have is a raise.
Nothing is hand-summed, so PRs that lower different entries touch different lines.

The base is:
- in CI (``GITHUB_ACTIONS``): ``AUTOBOT_RATCHET_BASE_SHA`` when ci.yml sets it -- a merge
  group's ``base_sha``, on a push to main the commit main pointed at before, or on a pull
  request into ``release`` the head's merge base with main (#19466: gates judge only commits
  not already on main, so a promotion is not re-judged against the weeks-old release tip) --
  else ``HEAD^1``. A pull_request run checks out the merge ref, whose first parent is the base tip.
  The checkout needs ``fetch-depth: 2``.
- elsewhere: ``git merge-base HEAD <AUTOBOT_RATCHET_BASE_REF, default origin/main>``.

A PR run that spans a raise can be cancelled, so the backstop is main's own push run: its base
is ``github.event.before``, always an ancestor, so a raise that slipped through turns main red on
the push that lands it (#19283 review). A pull_request's ``before`` is the previous PR head --
orphaned by a rebase -- which is why ci.yml passes it only for pushes.

A table that moved path is read from its first path present at each base, so a rename PR lists
the old path after the new one (``base_table(root, ("new.py", "old.py"), NAME)``).

If the base cannot be read, :class:`BaseUnavailable` is raised. It is never treated as
"nothing rose": a ratchet that cannot see its base has proved nothing.
"""

from __future__ import annotations

import ast
import os
import subprocess
from pathlib import Path

from autobot_shared.paths import scrubbed_git_env

BASE_REF_ENV = "AUTOBOT_RATCHET_BASE_REF"
BASE_SHA_ENV = "AUTOBOT_RATCHET_BASE_SHA"


class BaseUnavailable(RuntimeError):
    """The base commit (or a file at it) could not be read; the ratchet refuses to judge."""


def _git(root: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        ["git", "-C", str(root), *args], capture_output=True, text=True, timeout=60, env=scrubbed_git_env()
    )


def base_commit(root: Path) -> str:
    """The commit this tree is ratcheted against (see the module docstring)."""
    if os.environ.get("GITHUB_ACTIONS") == "true":
        given = os.environ.get(BASE_SHA_ENV, "").strip()
        if given.strip("0"):  # a new branch's push carries before=000...0, which names no commit
            return _commit(root, given, BASE_SHA_ENV)
        out = _git(root, "rev-parse", "--verify", "--quiet", "HEAD^1")
        if out.returncode != 0:
            raise BaseUnavailable(
                "HEAD^1 is missing, so the ratchet base cannot be read. The CI checkout needs "
                "`fetch-depth: 2` (#19283); refusing rather than reporting 'nothing rose'."
            )
        return out.stdout.strip()
    ref = os.environ.get(BASE_REF_ENV, "origin/main")
    out = _git(root, "merge-base", "HEAD", ref)
    if out.returncode != 0:
        raise BaseUnavailable(
            f"`git merge-base HEAD {ref}` failed ({out.stderr.strip()}); fetch {ref} or set {BASE_REF_ENV}."
        )
    return out.stdout.strip()


def _commit(root: Path, sha: str, source: str) -> str:
    """*sha* resolved to a commit in this clone, or BaseUnavailable naming where it came from."""
    out = _git(root, "rev-parse", "--verify", "--quiet", f"{sha}^{{commit}}")
    if out.returncode != 0:
        raise BaseUnavailable(f"{source}={sha} is not a commit in this clone; ci.yml must fetch it first.")
    return out.stdout.strip()


def base_text(root: Path, rel: str, sha: str | None = None) -> str | None:
    """*rel*'s content at the base (or at *sha*), or None if the file did not exist there."""
    sha = sha or base_commit(root)
    out = _git(root, "show", f"{sha}:{rel}")
    if out.returncode == 0:
        return out.stdout
    # git's two phrasings for "this path is not in that commit"; anything else is a read failure.
    if "does not exist in" in out.stderr or "exists on disk, but not in" in out.stderr:
        return None
    raise BaseUnavailable(f"cannot read {rel} at the base {sha[:10]}: {out.stderr.strip()}")


def literal_in(source: str, name: str) -> object:
    """The literal assigned to module-level *name* in *source* (``NAME = {...}`` or annotated)."""
    for node in ast.parse(source).body:
        targets = (
            node.targets if isinstance(node, ast.Assign) else [node.target] if isinstance(node, ast.AnnAssign) else []
        )
        if any(isinstance(t, ast.Name) and t.id == name for t in targets) and node.value is not None:
            return ast.literal_eval(node.value)
    raise BaseUnavailable(f"no literal {name} = ... in the base source")


def base_table(root: Path, rels: tuple[str, ...], name: str) -> dict[str, int]:
    """The literal *name* at the base: the ratchet's reference.

    *rels* is the table's path, then any path it had before a move; the first one the base has
    is read. A base with none of them gives ``{}``, so every entry reads as an addition.
    """
    sha = base_commit(root)
    src = next((s for s in (base_text(root, rel, sha) for rel in rels) if s is not None), None)
    return literal_in(src, name) if src is not None else {}


def raised_entries(now: dict[str, int], base: dict[str, int]) -> dict[str, tuple[int | None, int]]:
    """Entries that rose against the base, ``{key: (base value or None if new, now)}``."""
    return {k: (base.get(k), v) for k, v in now.items() if k not in base or v > base[k]}


def base_tree_texts(root: Path, prefix: str, sha: str | None = None) -> dict[str, str]:
    """``{path: text}`` for every file under *prefix* at the base (or at *sha*), in two git calls."""
    sha = sha or base_commit(root)
    listing = _git(root, "ls-tree", "-r", "-z", "--name-only", sha, "--", prefix)
    if listing.returncode != 0:
        raise BaseUnavailable(f"cannot list {prefix} at the base {sha[:10]}: {listing.stderr.strip()}")
    paths = [p for p in listing.stdout.split("\0") if p]
    if not paths:
        return {}
    batch = subprocess.run(
        ["git", "-C", str(root), "cat-file", "--batch"],
        input="".join(f"{sha}:{p}\n" for p in paths).encode("utf-8"),
        capture_output=True,
        timeout=120,
        env=scrubbed_git_env(),
    )
    if batch.returncode != 0:
        raise BaseUnavailable(f"cannot read {prefix} at the base {sha[:10]}: {batch.stderr.decode(errors='replace')}")
    texts, data, pos = {}, batch.stdout, 0
    for path in paths:
        header_end = data.index(b"\n", pos)
        header = data[pos:header_end].split()
        if len(header) < 3 or header[1] != b"blob":
            raise BaseUnavailable(f"unexpected object for {path} at the base: {data[pos:header_end]!r}")
        size = int(header[2])
        texts[path] = data[header_end + 1 : header_end + 1 + size].decode("utf-8", errors="replace")
        pos = header_end + 1 + size + 1
    return texts
