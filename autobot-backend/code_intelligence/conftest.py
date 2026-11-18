# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Local pytest configuration for code_intelligence tests.

Issue #9856: The top-level conftest stubs code_intelligence and
code_intelligence.security_analyzer as MagicMocks to avoid importing the
heavy code_intelligence/__init__.py chain. That stub must be replaced with
the real modular package for security_analyzer_test.py to exercise actual
detection logic.

This conftest runs after autobot-backend/conftest.py (parent-first order)
and loads the real modules into sys.modules before any test in this
directory imports them.

Issue #13111 generalised that repair: every code_intelligence submodule that the
top-level conftest stubs AND that owns a colocated ``<name>_test.py`` is real-loaded
here, because otherwise the test file's own ``from code_intelligence.<name> import ...``
resolves to the MagicMock stub and the whole file asserts against mock attributes.

Every mutation below goes through ``testkit.module_stubs.StubSet`` and is undone in
``pytest_unconfigure`` (#13596). Previously this file hand-rolled the same
primitives with no restore at all.

NOTE (session-wide until unconfigure): the sys.modules mutations below affect the
entire pytest session, not just tests inside code_intelligence/.  Any test
outside this directory that lazily imports one of the real-loaded submodules
will exec the real file rather than the top-level stub.  This is safe today
because the only module-level importers outside code_intelligence/ are api/*.py,
and pytest collects api/ BEFORE code_intelligence/ — those modules have already
bound the stub by the time this conftest runs.  That ordering is also why
merge_conflict_resolver (which api/merge_conflict_resolution.py binds at import
time) is real-loaded in the TOP-LEVEL conftest instead of here.
"""

import sys
from pathlib import Path

from testkit.module_stubs import StubSet

_backend_root = Path(__file__).parent.parent
_ci_dir = _backend_root / "code_intelligence"

_stubs = StubSet()

# Repair the code_intelligence stub: give it a real __path__ so that
# sub-module imports resolve to real files on disk.  We deliberately do NOT
# exec code_intelligence/__init__.py (it drags in the full backend stack).
# adopt_package keeps the session's existing object (other modules hold it) and
# records the previous __path__ so it is put back.
_stubs.adopt_package("code_intelligence", _ci_dir)

# Ensure code_intelligence.security and code_intelligence.shared are real.
# Evict the top-level conftest's stubs so the normal import machinery loads the
# packages from disk via the repaired __path__. The normal machinery, not a file
# spec, because a package __init__.py needs __package__ == its own dotted name for
# relative imports ("from .analyzer import ...") and a populated
# spec.submodule_search_locations.
#
# code_intelligence.security.analyzer imports code_intelligence.shared.analysis_base
# (#12686); the top-level conftest's leaf-only stub for .shared (empty __path__)
# would hide it, so it is evicted too.
_stubs.evict("code_intelligence.security", only_stubs=True)
_stubs.evict("code_intelligence.shared", only_stubs=True)
_stubs.import_real("code_intelligence.security")


def _is_conftest_stub(mod: object) -> bool:
    """True when *mod* is one of the top-level conftest's MagicMock package stubs.

    #13233: ``_make_pkg_stub`` installs a PEP 562 module-level ``__getattr__`` that
    returns a MagicMock singleton for ANY attribute the stub does not really have —
    dunders included. So ``getattr(stub, "__file__", None)`` yields that MagicMock
    and never ``None``, which makes the obvious ``getattr(...) is None`` stub test
    report "this is already a real module" for every stub. Reading ``__dict__``
    directly is the only lookup ``__getattr__`` cannot intercept: a real module
    always carries ``__file__`` there, a stub never does.
    """
    return vars(mod).get("__file__") is None if hasattr(mod, "__dict__") else True


def _load_real_submodule(leaf: str) -> None:
    """Real-load ``code_intelligence.<leaf>`` over the top-level conftest's stub.

    ``StubSet.real_load`` binds the module on the parent. That bind is load-bearing:
    ``from code_intelligence.X import Y`` and ``patch("code_intelligence.X.Y")`` both
    resolve through ``getattr(sys.modules["code_intelligence"], "X")``, and the
    stubbed parent's catch-all ``__getattr__`` hands back a MagicMock singleton
    without it.
    """
    _stubs.real_load(f"code_intelligence.{leaf}", _ci_dir / f"{leaf}.py", reuse_if_loaded=False)


# Replace the stub for the shim module with the real one.
_load_real_submodule("security_analyzer")

# Replace the code_intelligence.performance_analyzer stub with the real module
# (#12362). The top-level conftest stubs it as a MagicMock (heavy __init__
# chain avoidance) alongside security_analyzer/bug_predictor, but — unlike
# those two — it was never real-loaded here, so every standalone test in
# performance_analyzer_test.py silently exercised MagicMock attributes
# instead of the real PerformanceAnalyzer. Mirrors the security_analyzer
# real-load above.
_load_real_submodule("performance_analyzer")

# Replace the code_intelligence.bug_predictor stub with the real module (#12421).
# The top-level conftest stubs it as a MagicMock (heavy __init__ chain avoidance),
# so STANDALONE `from code_intelligence.bug_predictor import BugPredictor` in
# bug_predictor_test.py otherwise resolves mock attributes and every test errors.
# It only real-loaded incidentally when bug_predictor_source_scoping_test.py's
# private synthetic-alias load ran first — an order-dependent trap (same class as
# #12114). Real-load here (after __path__ is repaired above) so bug_predictor.py's
# `from code_intelligence.analytics_infrastructure import SemanticAnalysisMixin`
# resolves the real (import-light) module and BugPredictor inherits the mixin.
# Mirrors the security_analyzer real-load above.
_load_real_submodule("bug_predictor")

# code_intelligence.code_generation real package (#13111) — the former llm_code_generator.py was a
# pure facade (retired in #18552) over this package's entire public API, so while the top-level
# conftest's leaf-only stub (empty __path__) is bound, every symbol
# llm_code_generator_test.py imports is a MagicMock. Drop the package stub so the real
# __init__.py loads (its submodules resolve now that code_intelligence.__path__ is
# repaired above); the package is import-light — stdlib plus a try/except-guarded
# `from services.llm_service import get_llm_service`, and services.llm_service is itself
# stubbed by the top-level conftest.
#
# The already-real code_intelligence.code_generation.diff entry is deliberately LEFT in
# sys.modules: __init__.py's `from .diff import DiffGenerator` short-circuits on it, so
# tools/parallel/executor.py — which imported that module object back at top-level-conftest
# time — keeps referencing the SAME DiffGenerator class object. Re-executing diff.py would
# mint a second class and break isinstance identity for the earlier importer (#12839).
# _is_conftest_stub — NOT `getattr(..., "__file__", None) is None` — decides what to drop:
# the stub's catch-all __getattr__ answers "__file__" with a MagicMock, so the getattr form
# kept the stub, importlib.import_module handed it straight back, and the facade
# re-exported 25 MagicMocks (#13233).
_cg_pkg = sys.modules.get("code_intelligence.code_generation")
if _cg_pkg is not None and _is_conftest_stub(_cg_pkg):
    _stubs.evict("code_intelligence.code_generation", descendants=False)
_cg_diff = sys.modules.get("code_intelligence.code_generation.diff")
if _cg_diff is not None and _is_conftest_stub(_cg_diff):
    _stubs.evict("code_intelligence.code_generation.diff", descendants=False)
_real_cg = _stubs.import_real("code_intelligence.code_generation")
if _is_conftest_stub(_real_cg):
    # Fail loudly rather than let code_generation consumers see MagicMocks again (#13233):
    # a stub here silently turns every assertion in llm_code_generator_test.py into a
    # comparison against mock attributes, which reads as 68 ordinary test failures.
    raise RuntimeError(
        "code_intelligence.code_generation is still a conftest stub after real-load; "
        "code_generation consumers would see MagicMocks (#13233)"
    )
setattr(sys.modules["code_intelligence"], "code_generation", _real_cg)
if "code_intelligence.code_generation.diff" in sys.modules:
    setattr(_real_cg, "diff", sys.modules["code_intelligence.code_generation.diff"])

# Remaining self-poisoned submodules (#13111). Each of these is stubbed as a MagicMock
# package by the top-level conftest so that api/*.py can import it without dragging in
# code_intelligence/__init__.py — but each ALSO owns a colocated <name>_test.py, and that
# test file's `from code_intelligence.<name> import ...` resolved to the stub, so the
# whole file asserted against MagicMock attributes rather than real behaviour.
#
# Order is load-bearing: anti_pattern_detector must precede code_evolution_miner, whose
# module-level `from code_intelligence.anti_pattern_detector import AntiPatternDetector`
# would otherwise capture the stub and leave CodeEvolutionMiner.__init__ holding a mock
# detector. All of these are import-light in the test environment (verified statically:
# stdlib + autobot_shared.logging_manager — patched to a stdlib logger by the top-level
# conftest — plus in-repo code_intelligence subpackages, utils.line_index and
# constants.threshold_constants; no chromadb/torch/network imports on any path).
for _leaf in [
    "anti_pattern_detector",
    "code_evolution_miner",
    "code_fingerprinting",
    "code_review_engine",
    "llm_pattern_analyzer",
    "log_pattern_miner",
    "precommit_analyzer",
    "redis_optimizer",
    # #19566: vue_analyzer has a colocated test; base_analyzer (stdlib + logging +
    # status_enums only) must precede it so VueAnalyzer subclasses the real base.
    "base_analyzer",
    "vue_analyzer",
]:
    _load_real_submodule(_leaf)

# merge_conflict_resolver is NOT in the list above: it is real-loaded by the TOP-LEVEL
# conftest instead, because api/merge_conflict_resolution.py binds its symbols at import
# time and api/ is collected before code_intelligence/ (#13111). Bind it onto the
# namespace here anyway so patch("code_intelligence.merge_conflict_resolver.X") resolves.
_real_mcr = sys.modules.get("code_intelligence.merge_conflict_resolver")
if _real_mcr is not None:
    setattr(sys.modules["code_intelligence"], "merge_conflict_resolver", _real_mcr)


def pytest_unconfigure(config) -> None:  # noqa: ARG001
    """Undo exactly what this file changed: modules, parent bindings and __path__."""
    _stubs.restore()
