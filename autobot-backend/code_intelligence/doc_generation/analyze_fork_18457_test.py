# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#18457: analyze_module / analyze_package have ONE module-level definition.

``code_intelligence.doc_generator`` used to carry a second pair of
``analyze_module`` / ``analyze_package`` convenience functions. They now
re-export the ``module_analyzer`` ones, so every former caller is served by
the single canonical definition.

The ``code_intelligence`` package is stubbed by the top-level conftest, so the
re-export is asserted on the source (AST) rather than on imported objects.
"""

import ast
from pathlib import Path

from code_intelligence.doc_generation import module_analyzer

_NAMES = ("analyze_module", "analyze_package")
_DOC_GENERATOR = Path(__file__).resolve().parents[1] / "doc_generator.py"


def _tree() -> ast.Module:
    return ast.parse(_DOC_GENERATOR.read_text(encoding="utf-8"))


def test_doc_generator_defines_no_second_copy():
    defined = {n.name for n in _tree().body if isinstance(n, ast.FunctionDef)}
    assert not defined.intersection(_NAMES)


def test_doc_generator_reexports_the_canonical_functions():
    imported = {
        alias.name
        for n in _tree().body
        if isinstance(n, ast.ImportFrom) and n.module == "code_intelligence.doc_generation.module_analyzer"
        for alias in n.names
    }
    assert set(_NAMES) <= imported


def test_canonical_functions_serve_former_doc_generator_callers(tmp_path):
    src = tmp_path / "sample_mod.py"
    src.write_text('"""Sample."""\n\ndef f():\n    """Doc."""\n', encoding="utf-8")
    default = module_analyzer.analyze_module(str(src))
    with_kwargs = module_analyzer.analyze_module(str(src), include_private=True)
    assert default is not None and with_kwargs is not None
    assert [f.name for f in default.functions] == ["f"]


def test_shared_analyzer_accumulates_no_state_across_calls(tmp_path):
    """The shared module-level analyzer must not grow per call (leak guard)."""
    src = tmp_path / "sample_mod.py"
    src.write_text('"""Sample."""\n', encoding="utf-8")
    shared = module_analyzer._analyzer
    before = {k: len(v) for k, v in vars(shared).items() if hasattr(v, "__len__")}
    for _ in range(25):
        module_analyzer.analyze_module(str(src))
    after = {k: len(v) for k, v in vars(shared).items() if hasattr(v, "__len__")}
    assert before == after
    assert not hasattr(shared, "_analyzed_files")
