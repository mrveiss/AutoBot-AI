# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The `base_agent` re-export contract (#15950).

`base_agent_types` was extracted from `base_agent` to get that module under its
size ceiling. Forty existing sites import those names from `base_agent`, so the
re-export is load-bearing -- and it is also the exact shape a tidy-up deletes,
because to a linter it reads as an unused import. `# noqa: F401` silences the
linter; this pins the behaviour, which the noqa does not.

Asserted against the set of names the types module actually defines, not against
a hand-written list. A literal list here would drift the moment someone adds a
type, and would then pass while the new name was unreachable from where every
caller looks for it.
"""

from __future__ import annotations

import ast
import pathlib


def _public_names(module_path: pathlib.Path) -> set[str]:
    """Every class, function and module-level constant the file defines."""
    tree = ast.parse(module_path.read_text(encoding="utf-8"))
    names = {n.name for n in tree.body if isinstance(n, (ast.ClassDef, ast.FunctionDef))}
    names |= {t.id for n in tree.body if isinstance(n, ast.Assign) for t in n.targets if isinstance(t, ast.Name)}
    return {n for n in names if not n.startswith("_")}


def test_every_extracted_name_is_still_importable_from_base_agent():
    """The extraction must be invisible to every existing import site."""
    import agents.base_agent as base_agent

    types_module = pathlib.Path(base_agent.__file__).with_name("base_agent_types.py")
    missing = sorted(n for n in _public_names(types_module) if not hasattr(base_agent, n))

    assert not missing, (
        f"{missing} moved to base_agent_types and is no longer reachable from base_agent. "
        "Restore the re-export: existing callers import these from base_agent."
    )


def test_the_reexport_is_not_empty():
    """A guard that passes because it found nothing to check is not a guard.

    If the types module were renamed or emptied, `_public_names` would return an
    empty set and the test above would pass while asserting nothing.
    """
    import agents.base_agent as base_agent

    types_module = pathlib.Path(base_agent.__file__).with_name("base_agent_types.py")
    assert len(_public_names(types_module)) >= 5, "the extracted module should define the agent exchange types"
