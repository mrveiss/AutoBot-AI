# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM frontend publish contract, stated once (#15724).

The contract exists in **three** implementations and cannot be reduced to one:
a shell script on a freshly bootstrapped node cannot invoke an Ansible task, an
Ansible role should not shell out to a script that may not be on the node yet,
and the backend's self-sync path runs in-process with no shell at all. The
duplication is structural.

#15724 describes two. The third -- ``services/slm_frontend_build.py`` -- was
found while writing this: it satisfies the same contract in Python, spelling
the atomic flip as ``os.replace`` over a staged symlink rather than ``mv -T``.
That is precisely the "third implementation in a third language" the issue asks
to be caught, and it already existed.

What was *not* structural is that each side carried its own assertion list.
`slm_frontend_atomic_publish_15610_test.py` and `slm_frontend_shell_publish_test.py`
each restated the same five properties in their own words, both passed, and
nothing compared them. If the idiom changes -- as #15610 replaced the
two-directory-rename shape -- one guard is updated with it and the other keeps
asserting the old contract and keeps passing. The property nobody checked was
*the agreement itself*.

So the contract lives here, once, and the guards read it.

**Every clause is a positive assertion**: a pattern that must be PRESENT in each
implementation. That is deliberate. A negative clause -- "must not contain
`mv <dir> <dir>`" -- passes when the sweep reads the wrong file, when a path
moves, or when the file is empty. A positive clause fails in all three cases.
Every check found to be structurally incapable of failing has been a negative
one.

The stakes are why this is worth the machinery: vite empties its output
directory before writing, so a publisher that drifts back to building into the
served directory takes the site down, and a failed build behind an ungated
publish leaves it down (#15430, #15462, #15557, #15610).
"""

from dataclasses import dataclass
from pathlib import Path
from typing import Dict, Tuple

REPO_ROOT = Path(__file__).resolve().parents[1]


@dataclass(frozen=True)
class Clause:
    """One property of the publish contract, and how each language spells it."""

    name: str
    why: str
    #: implementation id -> regex that must match that implementation's source
    patterns: Dict[str, str]


#: The known implementations. Adding a third in a third language is caught by
#: `test_no_unlisted_publisher_exists` rather than silently accommodated: a new
#: publisher that nobody adds here is a fourth copy of the contract with no
#: guard at all, which is the state #15557 was filed for.
IMPLEMENTATIONS: Dict[str, Path] = {
    "ansible": REPO_ROOT / "autobot-slm-backend/ansible/roles/_shared/tasks/build_publish_slm_frontend.yml",
    "shell": REPO_ROOT / "autobot-infrastructure/autobot-slm-frontend/templates/build-publish-slm-frontend.sh",
    "python": REPO_ROOT / "autobot-slm-backend/services/slm_frontend_build.py",
}

#: Below this the discovery sweep collapsed rather than the tree being clean.
#: Bound to implementations *discovered*, never to clauses violated -- a floor
#: that tracked findings would relax itself as the code improved (#15762).
MIN_IMPLEMENTATIONS = 3

CLAUSES: Tuple[Clause, ...] = (
    Clause(
        name="builds with build:slm",
        why="build:slm pins VITE_API_URL=/slm; a plain `vite build` serves the SLM UI with the wrong API base.",
        patterns={
            "ansible": r"npm run build:slm",
            "shell": r"npm run build:slm",
            "python": r'"build:slm"',
        },
    ),
    Clause(
        name="builds into a fresh directory",
        why=(
            "vite empties its output directory before writing. Building into the served directory "
            "takes the site down for the length of the build, and leaves it down if the build fails."
        ),
        patterns={
            "ansible": r"--outDir dist-\{\{ _slm_frontend_build_id\.stdout \}\} --emptyOutDir",
            "shell": r'--outDir "\$\{build_dir\}" --emptyOutDir',
            "python": r'"--outDir",\s*\n\s*f"\{_BUILD_PREFIX\}\{build_id\}",\s*\n\s*"--emptyOutDir"',
        },
    ),
    Clause(
        name="refuses to publish without a non-empty index.html",
        why=(
            "nginx serves /slm/ with try_files ... /slm/index.html and autoindex off, so a missing "
            "or zero-byte index.html answers 403 for every path under /slm/ (#15430, #15462)."
        ),
        patterns={
            "ansible": r"index\.html",
            "shell": r'\[\[ ! -s "\$\{build_dir\}/index\.html" \]\]',
            "python": r"built_index\.is_file\(\) or built_index\.stat\(\)\.st_size == 0",
        },
    ),
    Clause(
        name="flips the served pointer atomically",
        why=(
            "`ln -sfn <target> current` unlinks the old symlink before creating the new one, so a "
            "request landing in that window 404s. Staging through .current.next and `mv -T` makes "
            "the swap a single rename(2) (#15610)."
        ),
        patterns={
            "ansible": r"ln -sfn .+\.current\.next",
            "shell": r"ln -sfn .+\.current\.next",
            "python": r'staged = root / f"\.\{link_name\}\.next"',
        },
    ),
    Clause(
        name="completes the flip with mv -T",
        why="`mv` without -T on an existing symlink-to-directory moves *into* it rather than replacing it.",
        patterns={
            "ansible": r"mv -T \.current\.next current",
            "shell": r"mv -T \.current\.next current",
            # Python has no `mv`; `os.replace` IS rename(2), which is what the
            # clause is actually about. Matching the shell spelling here would
            # have exempted this implementation from the clause entirely.
            "python": r"os\.replace\(staged, root / link_name\)",
        },
    ),
)
