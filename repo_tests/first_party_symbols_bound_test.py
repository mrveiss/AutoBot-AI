# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A first-party symbol must actually be bound in the module it is imported from (#13539).

`api/heartbeat.py:38` does `from autobot_shared.auth.permissions import is_admin_role`.
On 2026-08-04 a user hit `ImportError: cannot import name 'is_admin_role' from
'autobot_shared.auth.permissions'` -- naming a file that, at the moment the error
fired, genuinely did **not** define that symbol yet: the update rewrites `.py` files
under a *running* interpreter, and any module imported for the first time in that
window binds against whatever was on disk at that instant. `is_admin_role` and its
first consumer landed in the same rewrite second, so a process whose
`autobot_shared.auth.permissions` was already in `sys.modules` from *before* that
second saw a provider without the symbol its own, newly-written consumer expected.

`repo_tests/first_party_imports_resolve_test.py` says in its own docstring that it
*"deliberately checks only that the module resolves, not that the imported name
exists inside it. Resolving names would mean importing the module."* That is true
for a dynamically-imported module, but a **static** name check costs nothing --
this file is exactly what that sibling declines to do, done at the AST level with
no interpreter and no side effects, so it runs on every PR (design: V4 in
`docs/developer/RELEASE_FLIP_DESIGN_13539.md` §8). The AST mechanics live in the
sibling module `cross_module_symbol_binding.py`, split out to stay under the
python-file-size ratchet.

Scope, precisely stated:

* Swept: `from X import a, b` and `import X.y[.z...]`, reachable from module scope
  through `if` / `try` / `for` / `while` / `with` (the same control-flow-transparent
  walk used to decide what a *provider* binds), in every `.py` file under the trees
  this repository's own `pytest.ini` `pythonpath` directive governs: `autobot-
  backend/`, `autobot_shared/`, `repo_tests/`, `tools/`, `pipeline-scripts/`,
  `.claude/skills/claims-audit/`, `libs/autobot-sdk-python/`, `scripts/`, and files
  directly at the repo root.
* NOT swept: imports nested inside a `def`/`class`/`lambda` body. A deferred import
  fails at *call* time against whatever is in `sys.modules` *then*, which is a
  different bug population (#14839, already the sibling's territory) than
  #13539's "first touch after the tree was just rewritten" mechanism, which is
  specific to module-scope imports executing at process-import time. Restricting
  to module scope also matches the measured population: widening this sweep to
  function bodies pulled in 504 hits from ONE file
  (`api/api_endpoint_migrations_test.py`, frozen pending audit under #5359/#15173,
  `pytestmark = pytest.mark.skip` at module scope) whose deferred imports reference
  a since-split API layout and never execute -- noise that would make this gate
  worthless within a day of landing.
* NOT swept: other top-level service directories (`autobot-slm-backend`,
  `autobot-npu-worker`, `autobot-infrastructure`, `autobot-tts-worker`, ...). Each is
  its own deployable with its own import roots, established by its own conftest.py
  rather than this repo's root `pytest.ini` `pythonpath` -- `autobot-slm-backend/
  conftest.py` pre-populates `sys.modules['api']` specifically to stop its `api`
  package from colliding with `autobot-backend/api` (#3499), proof that resolving
  a bare first-party name the same way across service boundaries is actively wrong,
  not merely unproven. Extending V4 there needs per-service root discovery, which is
  future work -- a finding of this task, not silently done here.

Resolution order, and why it is not `pytest.ini`'s literal text order: `autobot-
backend/conftest.py` inserts `project_root`, then `shared_root`, then `backend_root`
onto `sys.path`, in that order, each at position 0 -- landing `backend_root` at the
front on purpose ("Insert shared_root before backend_root so that backend_root ends
up at position 0 ... This ensures bare `models.*` imports in autobot-backend code
resolve to autobot-backend/models/, not the similarly-named package in
autobot_shared/"). `cross_module_symbol_binding.pythonpath_roots()` mirrors that
documented, load-bearing order rather than `pytest.ini`'s line order: `autobot-
backend` first, `autobot_shared` second, everything else as `pytest.ini` lists it.
Getting this wrong is not cosmetic -- with the naive `pytest.ini` order, `autobot-
backend/tools/terminal_tool.py` doing `from tools import ...` resolves against the
*unrelated* top-level `tools/` (lint/codemod) package and reports a false violation.

The five design constraints from #13539's V4 spec, and the rule this file applies
to each:

1. **Dynamic bindings.** A provider containing `globals().update(...)` anywhere,
   a module-level `def __getattr__` (PEP 562), or `from Y import *` at module scope
   is treated as **wholly opaque**: every name imported from it is accepted, no
   matter what the static walk found. A false positive blocking every PR that
   touches such a module is a far worse outcome than missing a genuine typo inside
   one -- see the sibling's module docstring for the same call on optional imports.
2. **Re-exports.** `from .x import y` inside `X/__init__.py` binds `y` in `X`'s
   namespace like any other `ImportFrom` -- no special case needed. Separately,
   and more subtly: for any package `X`, `from X import a` succeeds at runtime
   whenever `X/a.py` (or `X/a/__init__.py`) exists as a **submodule**, even if
   `X/__init__.py` never imports or mentions `a` -- Python's import system falls
   back to `import X.a` when attribute lookup on the already-imported package
   fails. Every direct submodule of a package is therefore treated as
   automatically bound.
3. **Conditional / `TYPE_CHECKING` imports.** Two independent sides, both handled
   by not walking into the `if TYPE_CHECKING:` **body** while still walking its
   `else:`/`elif` branch (the one that actually executes):
   - *Provider side*: a name bound only inside `if TYPE_CHECKING:` is invisible to
     this check, so a consumer "importing" it is flagged -- correctly, since that
     name does not exist at runtime either.
   - *Consumer side*: an import statement itself sitting inside
     `if TYPE_CHECKING:` never executes at runtime, so it is exempt outright, the
     same way an `ImportError`/`ModuleNotFoundError`-guarded import is (the
     sibling's `_optional_import_nodes` rationale, reused here with the same
     deliberate exclusion of bare `except Exception`).
4. **Existing violations.** Found exactly one, in-tree, real:
   `autobot-backend/models/settings.py:24` imported `Models` from
   `constants.model_constants`, which does not define it (nor does its own
   re-export source, `autobot_shared.ssot_constants`) -- `LLMSettings` referenced
   `Models.ORCHESTRATOR` / `Models.DEFAULT`, neither of which exists under any
   name. Nothing in the tree imports `models.settings`, so this was latent dead
   code rather than a live outage; fixed in place (`ModelConstants.ORCHESTRATOR_
   MODEL` / `ModelConstants.DEFAULT_OLLAMA_MODEL`, the re-exported names that
   actually exist) rather than baselined -- a baseline entry would have hidden a
   bug this check exists to surface.
5. **Performance.** Measured on this branch: ~4.6k files swept, ~10k `ImportFrom`
   sites and ~100 dotted `Import` sites checked, in under 25 seconds cold
   (dominated by `ast.parse`'s own `compile()` call) -- see
   `test_the_sweep_actually_reached_the_tree`'s docstring for the exact numbers
   this was authored against.
"""

from __future__ import annotations

import ast

import pytest

from repo_tests import cross_module_symbol_binding as xmod

_KNOWN_BROKEN: dict[tuple[str, str, str], str] = {}
_MIN_FILES_SWEPT = 3000
_MIN_FROM_SITES_CHECKED = 5000
_MIN_DOTTED_SITES_CHECKED = 30
_MIN_FIRST_PARTY_NAMES = 50


def test_the_sweep_actually_reached_the_tree() -> None:
    """Discovery floors, measured on this branch: 4564 files swept, 10056
    `ImportFrom` sites checked, 96 dotted `Import` sites checked, 90+ first-party
    top-level names. An empty walk would report a clean tree having asserted
    nothing — these floors are well below the measured numbers on purpose, so a
    sweep that quietly stops matching fails loudly instead of passing vacuously.
    """
    names = xmod.first_party_names()
    _, stats = xmod.sweep()
    assert len(names) > _MIN_FIRST_PARTY_NAMES, f"only {len(names)} first-party names — the root walk is wrong"
    assert "autobot_shared" in names, "autobot_shared root not discovered — resolution would miss #13539's own case"
    assert stats["files"] > _MIN_FILES_SWEPT, f"only swept {stats['files']} files — the sweep has stopped matching"
    assert stats["from_checked"] > _MIN_FROM_SITES_CHECKED, f"only checked {stats['from_checked']} from-sites"
    assert stats["dotted_checked"] > _MIN_DOTTED_SITES_CHECKED, f"only checked {stats['dotted_checked']} dotted sites"


def test_every_cross_module_symbol_is_bound() -> None:
    """#13539's V4: a first-time import must not raise for a symbol the provider
    file provably does not define — caught statically, before it ever reaches a
    running process mid-update.
    """
    findings, stats = xmod.sweep()
    assert stats["files"] > _MIN_FILES_SWEPT, f"only swept {stats['files']} files — this would pass vacuously"
    offenders = [f for f in findings if not any(f.startswith(f"{rel}:") for rel, _, _ in _KNOWN_BROKEN)]
    assert not offenders, (
        "these imports name a symbol that is not bound at module level in the "
        "module the error would point at (#13539) — the failure looks like a "
        "packaging problem but is a name that was never there:\n  " + "\n  ".join(offenders)
    )


def test_the_detector_binds_every_accepted_form_and_rejects_a_planted_typo() -> None:
    """Self-test: one provider exercising every accepted binding form (def,
    class, assignment incl. unpacking, import re-export, `__all__`, and a
    submodule), plus a planted typo that must be rejected.
    """
    provider = ast.parse(
        "\n".join(
            [
                "def a_function(): pass",
                "class AClass: pass",
                "an_assignment = 1",
                "first, second = 1, 2",
                "from os import path as an_alias",
                "__all__ = ['an_all_only_name']",
            ]
        )
    )
    bound: set[str] = set()
    xmod.walk_bindings(provider.body, bound)
    for name in ("a_function", "AClass", "an_assignment", "first", "second", "an_alias", "an_all_only_name"):
        assert name in bound, f"{name} should be accepted as a module-level binding and was not"
    assert "a_typo_nobody_defined" not in bound, "the detector accepted a name nothing binds"


def test_type_checking_body_is_excluded_but_its_else_is_not() -> None:
    provider = ast.parse(
        "\n".join(
            [
                "from typing import TYPE_CHECKING",
                "if TYPE_CHECKING:",
                "    from foo import OnlyForTypeCheckers",
                "else:",
                "    RuntimeFallback = None",
            ]
        )
    )
    bound: set[str] = set()
    xmod.walk_bindings(provider.body, bound)
    assert "OnlyForTypeCheckers" not in bound, "a TYPE_CHECKING-only name must not count as a real runtime binding"
    assert "RuntimeFallback" in bound, "the TYPE_CHECKING else branch runs at runtime and must still be walked"


def test_consumer_type_checking_and_optional_imports_are_exempt() -> None:
    consumer = ast.parse(
        "\n".join(
            [
                "from typing import TYPE_CHECKING",
                "if TYPE_CHECKING:",
                "    from nowhere import Anything",
                "try:",
                "    from nowhere import SomethingElse",
                "except ImportError:",
                "    SomethingElse = None",
            ]
        )
    )
    sites = xmod.import_sites(consumer.body)
    assert len(sites) == 3, "expected the TYPE_CHECKING module import plus the two guarded sites"
    by_guard = sorted(guarded for _, guarded in sites)
    assert by_guard == [False, True, True], (
        "expected exactly one unguarded site (the top-level `from typing import "
        "TYPE_CHECKING` itself, which really does execute) and two guarded ones "
        "(the TYPE_CHECKING-only import and the ImportError-guarded import)"
    )


def test_a_dynamic_provider_is_wholesale_exempt() -> None:
    star_import = ast.parse("from anything import *")
    getattr_provider = ast.parse("def __getattr__(name):\n    return None\n")
    globals_provider = ast.parse("globals().update({'x': 1})\n")
    for tree in (star_import, getattr_provider, globals_provider):
        bound: set[str] = set()
        xmod.walk_bindings(tree.body, bound)
        assert xmod.module_is_dynamic(tree, bound), f"expected {ast.dump(tree)[:60]}... to be treated as dynamic"


def test_a_package_submodule_is_bound_even_without_an_init_reexport() -> None:
    """`from X import a` succeeds whenever `X/a.py` exists, independent of
    whatever `X/__init__.py` does or does not import — the Python import system's
    own fallback, not something this check can opt out of (constraint 2)."""
    resolved = xmod.resolve_module("repo_tests")
    assert resolved is not None and resolved.name == "__init__.py"
    submodules = xmod.submodule_names(resolved)
    assert "first_party_imports_resolve_test" in submodules, (
        "a real sibling module was not detected as an implicitly-bound submodule of repo_tests"
    )


@pytest.mark.parametrize("entry,issue", sorted(_KNOWN_BROKEN.items()))
def test_each_exemption_is_still_broken(entry: tuple[str, str, str], issue: str) -> None:  # pragma: no cover - empty
    """An exemption that no longer applies exempts nothing, silently — see the
    identical rationale in `first_party_imports_resolve_test.py`. Parametrized
    over an empty dict on purpose: this collects zero tests today (constraint 4
    in the module docstring), and stays ready the day an entry is genuinely
    unavoidable.
    """
    rel, module, name = entry
    path = xmod.REPO_ROOT / rel
    assert path.is_file(), f"{rel} moved or was deleted — update or drop this exemption ({issue})"
    provider_path = xmod.resolve_module(module)
    assert provider_path is not None, f"{module} no longer resolves — the exemption for {rel} ({issue}) is obsolete"
    bound, dynamic, submodules = xmod.provider_info(provider_path)
    assert not dynamic and name not in bound and name not in submodules, (
        f"{name} is now bound in {module}, so the exemption for {rel} ({issue}) is obsolete — remove it"
    )
