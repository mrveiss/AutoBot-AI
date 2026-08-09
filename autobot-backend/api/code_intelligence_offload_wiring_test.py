# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The process-offload conversion must not drop state the response needs (#12866).

Moving a scan into another process leaves the local scanner object un-run, and
these endpoints summarise *through* that object. Two ways that goes wrong, both
silent:

* the scanner is gone entirely and a later line still names it — ``F821``, a
  500 on the endpoint. Exactly what happened to ``_run_redis_health_analysis``:
  the conversion removed ``optimizer = RedisOptimizer(...)`` while
  ``category_breakdown`` still read ``optimizer.get_summary()``. flake8 caught
  it; nothing here did, because no test called the helper.
* the scanner survives but is never given the child's findings, so
  ``get_summary()`` reports an empty scan of a tree that was fully scanned.
  Nothing raises — the response is well-formed and wrong.

So these call the converted helpers for real, with the scan stubbed, and assert
the summarised fields actually reflect the findings.
"""

from __future__ import annotations

from unittest.mock import patch

import pytest

pytestmark = pytest.mark.asyncio


class _Finding:
    """Minimal stand-in for a RedisOptimizer result."""

    def __init__(self, file_path: str, severity, opt_type: str):
        self.file_path = file_path
        self.severity = severity
        self.optimization_type = opt_type
        self.type = opt_type


def _redis_findings():
    from code_intelligence.redis_optimizer import OptimizationSeverity

    return [
        _Finding("a.py", OptimizationSeverity.HIGH, "pipeline"),
        _Finding("a.py", OptimizationSeverity.LOW, "ttl"),
        _Finding("b.py", OptimizationSeverity.HIGH, "pipeline"),
    ]


class _FakeOptimizer:
    """A RedisOptimizer whose summary is genuinely derived from its findings.

    The real class is a ``MagicMock`` in this harness (conftest stubs the
    code_intelligence package). Asserting against it is vacuous: every attribute
    access returns a truthy mock, so ``assert result["category_breakdown"]``
    passes whether or not the findings were ever handed over. That is the #13111
    / #13162 harness-bug shape, and it hid this exact regression on the first
    attempt at this test.
    """

    def __init__(self, project_root=None):
        self.project_root = project_root
        self.results = []

    def get_summary(self):
        by_type = {}
        for finding in self.results:
            by_type[finding.type] = by_type.get(finding.type, 0) + 1
        return {"by_type": by_type}


async def test_redis_health_analysis_summarises_the_offloaded_findings():
    """The regression that shipped: the helper named a scanner it no longer built.

    ``category_breakdown`` reads ``optimizer.get_summary()``. The conversion
    removed ``optimizer = RedisOptimizer(...)`` and flake8 caught the F821 — but
    only after CI ran, because nothing here called the helper. Rebuilding the
    scanner is not enough either: it must be handed the child's findings, or the
    field is a well-formed empty dict.
    """
    import api.code_intelligence as mod

    findings = _redis_findings()

    with patch.object(mod, "RedisOptimizer", _FakeOptimizer):
        with patch.object(mod, "run_isolated", return_value=findings) as scan:
            result = await mod._run_redis_health_analysis("/tmp/example")

    assert scan.await_count == 1, "the scan must go through the process-offload helper"

    assert result["status"] == "success"
    assert result["total_optimizations"] == 3
    assert result["files_with_issues"] == 2

    # Derived from the findings, so an un-fed optimizer produces {} and fails here.
    assert result["category_breakdown"] == {"pipeline": 2, "ttl": 1}, (
        "category_breakdown does not reflect the findings — the local optimizer was "
        "never given what the child produced, so get_summary() summarised nothing"
    )


async def test_redis_analysis_offloads_a_directory_scan_by_class_not_instance():
    """A constructed scanner is not guaranteed picklable; the class and kwargs are."""
    import api.code_intelligence as mod
    from code_intelligence.redis_optimizer import RedisOptimizer

    findings = _redis_findings()

    with patch.object(mod, "run_isolated", return_value=findings) as scan:
        with patch("os.path.isfile", return_value=False):
            out = await mod._run_redis_analysis("/tmp/example", "/tmp/example", ["venv"])

    assert out == findings
    cls, init_kwargs, method = scan.await_args.args[:3]
    assert cls is RedisOptimizer
    assert init_kwargs == {"project_root": "/tmp/example"}
    assert method == "analyze_directory"
    assert scan.await_args.kwargs["exclude_patterns"] == ["venv"]


async def test_single_file_redis_analysis_still_reaches_analyze_file():
    """A bounded single-file scan must not be silently turned into a tree walk."""
    import api.code_intelligence as mod

    with patch.object(mod, "run_isolated", return_value=[]) as scan:
        with patch("os.path.isfile", return_value=True):
            await mod._run_redis_analysis("/tmp/example", "/tmp/example/one.py", None)

    assert scan.await_args.args[2] == "analyze_file"


async def test_every_converted_site_still_resolves_its_names():
    """A cheap tripwire for the F821 class that reached CI.

    Compiling the module is not enough — an undefined name inside a function body
    only raises when that line runs. This walks the AST of the converted helpers
    and checks every name they load is either bound locally, a parameter, or a
    module global.
    """
    import ast
    import builtins
    import inspect

    import api.code_intelligence as mod

    for func in (mod._run_redis_health_analysis, mod._run_redis_analysis):
        tree = ast.parse(inspect.getsource(func).lstrip())
        fn = tree.body[0]

        bound = {a.arg for a in fn.args.args} | {a.arg for a in fn.args.kwonlyargs}
        for node in ast.walk(fn):
            if isinstance(node, ast.Name) and isinstance(node.ctx, ast.Store):
                bound.add(node.id)
            elif isinstance(node, (ast.Import, ast.ImportFrom)):
                bound.update((a.asname or a.name).split(".")[0] for a in node.names)
            elif isinstance(node, ast.comprehension):
                for target in ast.walk(node.target):
                    if isinstance(target, ast.Name):
                        bound.add(target.id)

        loaded = {n.id for n in ast.walk(fn) if isinstance(n, ast.Name) and isinstance(n.ctx, ast.Load)}
        unresolved = loaded - bound - set(vars(mod)) - set(dir(builtins))

        assert not unresolved, (
            f"{func.__name__} loads names nothing binds: {sorted(unresolved)} — "
            "the offload conversion removed a scanner a later line still uses"
        )
