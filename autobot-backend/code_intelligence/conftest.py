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

NOTE (session-global side-effect): the sys.modules mutations below affect the
entire pytest session, not just tests inside code_intelligence/.  Any test
outside this directory that lazily imports one of the real-loaded submodules
will exec the real file rather than the top-level stub.  This is safe today
because the only module-level importers outside code_intelligence/ are api/*.py,
and pytest collects api/ BEFORE code_intelligence/ — those modules have already
bound the stub by the time this conftest runs.  That ordering is also why
merge_conflict_resolver (which api/merge_conflict_resolution.py binds at import
time) is real-loaded in the TOP-LEVEL conftest instead of here.
"""

import importlib
import importlib.util
import logging
import sys
from pathlib import Path

_logger = logging.getLogger(__name__)

_backend_root = Path(__file__).parent.parent


def _load_real(module_name: str, file_path: Path) -> None:
    """Load a module from a real file, replacing any existing stub.

    Uses spec_from_file_location for leaf modules (non-package .py files).
    For __package__ correctness: leaf modules (foo.bar.baz -> __package__ =
    "foo.bar") use rpartition; package __init__.py files must use
    importlib.import_module so the normal machinery sets __package__ correctly
    to the package's own name and wires up submodule_search_locations.
    Do NOT call _load_real for package __init__.py files.
    """
    spec = importlib.util.spec_from_file_location(module_name, str(file_path))
    if spec is None or spec.loader is None:
        _logger.warning("_load_real: cannot build spec for %s at %s", module_name, file_path)
        return
    mod = importlib.util.module_from_spec(spec)
    # For a leaf module "a.b.c", __package__ = "a.b" (correct).
    # Never pass an __init__.py here — use importlib.import_module instead.
    mod.__package__ = module_name.rpartition(".")[0] or module_name
    sys.modules[module_name] = mod
    try:
        spec.loader.exec_module(mod)  # type: ignore[union-attr]
    except Exception as exc:
        sys.modules.pop(module_name, None)
        _logger.warning("_load_real: failed to exec %s: %s", module_name, exc)
        raise


# Repair the code_intelligence stub: give it a real __path__ so that
# sub-module imports resolve to real files on disk.  We deliberately do NOT
# exec code_intelligence/__init__.py (it drags in the full backend stack),
# but the stub's __path__ must point at the real directory so that
# `import code_intelligence.security.constants` finds the real .py file.
import types as _types

_ci_mod = sys.modules.get("code_intelligence")
if _ci_mod is None or not isinstance(_ci_mod, _types.ModuleType):
    _ci_mod = _types.ModuleType("code_intelligence")
_ci_mod.__path__ = [str(_backend_root / "code_intelligence")]
_ci_mod.__package__ = "code_intelligence"
if not hasattr(_ci_mod, "__spec__") or _ci_mod.__spec__ is None:
    _ci_mod.__spec__ = importlib.util.spec_from_file_location(
        "code_intelligence",
        str(_backend_root / "code_intelligence" / "__init__.py"),
    )
sys.modules["code_intelligence"] = _ci_mod

# Ensure the code_intelligence.security sub-package and all its sub-modules are
# real.  Remove any existing stubs (from the top-level conftest) so that normal
# import machinery can load the package from disk via _ci_mod.__path__.
#
# Rationale for using importlib.import_module (not _load_real) for the package:
# spec_from_file_location sets __package__ = rpartition(".")[0], which for the
# package name "code_intelligence.security" yields "code_intelligence" — wrong.
# A package __init__.py needs __package__ == its own dotted name so that its
# relative imports ("from .analyzer import ...") resolve correctly.  The normal
# import machinery (importlib.import_module) sets this correctly and also
# populates spec.submodule_search_locations so sub-imports keep working.
for _key in list(sys.modules.keys()):
    if _key == "code_intelligence.security" or _key.startswith("code_intelligence.security."):
        del sys.modules[_key]

# code_intelligence.security.analyzer imports code_intelligence.shared.analysis_base
# (#12686). The top-level conftest installs a leaf-only stub for
# code_intelligence.shared (empty __path__) so that api/*.py's module-level
# `from code_intelligence.shared.scoring import get_grade_from_score` resolves
# without dragging in the heavier ASTCache/FileListCache imports. Drop that
# stub here too so the real package (with its real __path__, now that
# code_intelligence.__path__ is repaired above) loads for real analysis_base.
for _key in list(sys.modules.keys()):
    if _key == "code_intelligence.shared" or _key.startswith("code_intelligence.shared."):
        del sys.modules[_key]

importlib.import_module("code_intelligence.security")


def _load_real_submodule(leaf: str) -> None:
    """Real-load ``code_intelligence.<leaf>`` over the top-level conftest's stub.

    The namespace bind is load-bearing: ``from code_intelligence.X import Y`` and
    ``patch("code_intelligence.X.Y")`` both resolve through
    ``getattr(sys.modules["code_intelligence"], "X")``, and the stubbed parent's
    catch-all ``__getattr__`` hands back a MagicMock singleton without it — so the
    real module would load but every consumer would still see mocks.
    """
    name = f"code_intelligence.{leaf}"
    _load_real(name, _backend_root / "code_intelligence" / f"{leaf}.py")
    real = sys.modules.get(name)
    if real is not None:
        setattr(sys.modules["code_intelligence"], leaf, real)


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

# code_intelligence.code_generation real package (#13111) — llm_code_generator.py is a
# pure facade that re-exports this package's entire public API, so while the top-level
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
_cg_pkg = sys.modules.get("code_intelligence.code_generation")
if _cg_pkg is not None and getattr(_cg_pkg, "__file__", None) is None:
    del sys.modules["code_intelligence.code_generation"]
_cg_diff = sys.modules.get("code_intelligence.code_generation.diff")
if _cg_diff is not None and getattr(_cg_diff, "__file__", None) is None:
    del sys.modules["code_intelligence.code_generation.diff"]
_real_cg = importlib.import_module("code_intelligence.code_generation")
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
    "conversation_flow_analyzer",
    "llm_code_generator",
    "llm_pattern_analyzer",
    "log_pattern_miner",
    "precommit_analyzer",
    "redis_optimizer",
]:
    _load_real_submodule(_leaf)

# merge_conflict_resolver is NOT in the list above: it is real-loaded by the TOP-LEVEL
# conftest instead, because api/merge_conflict_resolution.py binds its symbols at import
# time and api/ is collected before code_intelligence/ (#13111). Bind it onto the
# namespace here anyway so patch("code_intelligence.merge_conflict_resolver.X") resolves.
_real_mcr = sys.modules.get("code_intelligence.merge_conflict_resolver")
if _real_mcr is not None:
    setattr(sys.modules["code_intelligence"], "merge_conflict_resolver", _real_mcr)
