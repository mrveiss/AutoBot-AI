# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""One node identity across every subsystem that parses source (#13470).

The issue's verification criterion is a *join*: an id produced by one extractor
has to equal the id another produces for the same function, or no finding from
either can be related to the other. Four subsystems parse the same files;
`code_indexer` and `call_graph` were converged onto `autobot_shared.code_graph`
already, and the clone fingerprinter was not.

The blocker was not the id function — it was that the fingerprinter discarded
class scope. Its extraction used a flat ``ast.walk``, so a method arrived with a
bare ``entity_name``, indistinguishable from a module-level function of the same
name and unable to produce the class-qualified canonical id. An id computed from
that is not merely different from the graph's; it is *wrong*, and quietly so.
"""

import ast

import pytest

from autobot_shared.code_graph import compute_node_id, module_path_from_rel_path
from code_intelligence.fingerprinting.detector import CloneDetector
from autobot_shared.code_graph.identity import _PROJECT_ROOT as PROJECT_ROOT
from code_intelligence.fingerprinting.detector import CloneDetector as _CD  # noqa: F401
from code_intelligence.fingerprinting.types import CodeFragment

SOURCE = """
def module_level(a):
    def helper(b):
        return b
    if a:
        def conditional(c):
            return c
    try:
        def guarded(d):
            return d
    except ValueError:
        def recovered(e):
            return e
    for _ in range(1):
        def looped(f):
            return f
    with open("x") as fh:
        def managed(g):
            return g
    return helper


async def module_level_async(a):
    async def inner_async(b):
        return b
    return inner_async


class Service:
    def handle(self, request):
        def local_helper(x):
            return x

        class LocalClass:
            def local_method(self):
                return 1

        return module_level(request)

    class Inner:
        def nested(self):
            return 1
"""

REL_PATH = "services/example/service.py"


def _fragments(tmp_path, source: str = SOURCE, rel_path: str = REL_PATH):
    """Extract fragments the way the detector does, keyed by ``(parent_class, name)``.

    Keyed on the pair deliberately: keying on the bare name loses exactly the case
    under test, since a method and a module-level function can share one.
    """
    path = tmp_path / "service.py"
    path.write_text(source, encoding="utf-8")
    detector = CloneDetector(min_fragment_lines=1)
    found = detector._extract_fragments_from_file(str(path))
    for fragment in found:
        fragment.file_path = rel_path
    return {(f.parent_class, f.entity_name): f for f in found}


def _fragments_from_repo_file(source: str):
    """Extract from a file inside the project root, path untouched.

    The point is that nothing rewrites ``file_path`` afterwards. The previous
    version of this helper did exactly that, which is how it hid the fact that
    production ids carried the deploy root as a prefix and joined with nothing.
    """
    target = PROJECT_ROOT / "autobot-backend" / "code_intelligence" / "_identity_probe_13470.py"
    target.write_text(source, encoding="utf-8")
    try:
        detector = CloneDetector(min_fragment_lines=1)
        found = detector._extract_fragments_from_file(str(target))
    finally:
        target.unlink(missing_ok=True)
    return {(f.parent_class, f.entity_name): f for f in found}


# ------------------------------------------------------------- the join itself


def test_a_method_id_matches_what_the_code_graph_computes(tmp_path):
    """The verification criterion of #13470, on the case that used to break.

    ``code_indexer`` builds a method's id from (name, module path, parent class).
    If the fingerprinter cannot supply the parent class, its id silently belongs
    to a different function.
    """
    handle = _fragments(tmp_path)[("Service", "handle")]
    graph_id = compute_node_id("handle", module_path_from_rel_path(REL_PATH), "Service")

    assert handle.node_id == graph_id


def test_a_module_level_function_id_matches_too(tmp_path):
    fragment = _fragments(tmp_path)[(None, "module_level")]
    graph_id = compute_node_id("module_level", module_path_from_rel_path(REL_PATH), None)

    assert fragment.node_id == graph_id


def test_a_method_and_a_same_named_function_do_not_collide(tmp_path):
    """The ambiguity a bare name creates, stated as a property.

    Without the class, ``Service.handle`` and a module-level ``handle`` produce
    the same id — so a clone reported against one would be joined to the other.
    """
    source = SOURCE + "\n\ndef handle(request):\n    return request\n"
    fragments = _fragments(tmp_path, source=source)

    method = fragments[("Service", "handle")]
    free_function = fragments[(None, "handle")]

    assert method.node_id != free_function.node_id
    assert method.node_id.endswith(".Service.handle")


# ------------------------------------------------------ class scope is recorded


def test_the_enclosing_class_is_recorded(tmp_path):
    fragments = _fragments(tmp_path)

    assert fragments[("Service", "handle")].parent_class == "Service"
    assert fragments[(None, "module_level")].parent_class is None


def test_a_nested_class_binds_its_own_methods(tmp_path):
    """Scope is tracked through nesting, not just one level deep."""
    fragments = _fragments(tmp_path)

    assert fragments[("Inner", "nested")].parent_class == "Inner"


def test_every_definition_is_still_found(tmp_path):
    """The scope-aware walk must not lose fragments the flat walk found.

    ``ast.walk`` visited every node; recursing over children has to reach the
    same set, or this becomes a coverage regression dressed as a fix.
    """
    flat = {
        node.name
        for node in ast.walk(ast.parse(SOURCE))
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef))
    }

    assert {name for _, name in _fragments(tmp_path)} == flat


# ---------------------------------------------------------- edges of identity


def test_a_fragment_with_no_entity_name_has_no_id():
    """A fragment that names nothing cannot be identified, and does not pretend to."""
    anonymous = CodeFragment(file_path=REL_PATH, start_line=1, end_line=2, source_code="x = 1")

    assert anonymous.node_id == ""


def test_the_id_reaches_the_serialised_finding(tmp_path):
    """A finding nobody can join is the state this issue exists to end."""
    from code_intelligence.fingerprinting.types import Fingerprint, FingerprintType

    fragment = _fragments(tmp_path)[("Service", "handle")]
    payload = Fingerprint(
        hash_value="abc", fingerprint_type=FingerprintType.AST_STRUCTURAL, fragment=fragment
    ).to_dict()

    assert payload["node_id"] == fragment.node_id
    assert payload["node_id"], "the serialised finding carries no id at all"


@pytest.mark.parametrize("rel_path", ["services/a/b.py", "autobot-backend/api/x.py"])
def test_the_id_namespace_follows_the_project_relative_path(tmp_path, rel_path):
    fragment = _fragments(tmp_path, rel_path=rel_path)[(None, "module_level")]

    assert fragment.node_id == compute_node_id("module_level", module_path_from_rel_path(rel_path), None)


# ------------------------------ the join, against the other extractor's output


JOIN_SOURCE = """
def module_level(a):
    return a + 1


class Service:
    def handle(self, request):
        return module_level(request)

    class Inner:
        def nested(self):
            return 1
"""


def _graph_ids(source: str, rel_path: str) -> set:
    """Node ids ``code_indexer`` produces for *source* — the other side of the join."""
    from services.knowledge.code_indexer import extract_python

    extracted = extract_python(rel_path, source.encode("utf-8"))
    return {node["id"] for node in extracted["nodes"]}


@pytest.mark.skipif(
    __import__("importlib").util.find_spec("tree_sitter_python") is None,
    reason="tree-sitter-python not installed",
)
def test_the_two_extractors_agree_on_every_id(tmp_path):
    """The issue's actual verification criterion, asserted against real output.

    The earlier version of this file compared the fingerprinter's id to a second
    application of the same formula — which cannot disagree, and which is why a
    nested *class* silently produced an id the graph did not have. Intersecting
    two real id sets found it immediately.
    """
    rel_path = "services/example/service.py"
    fingerprint_ids = {f.node_id for f in _fragments(tmp_path, source=JOIN_SOURCE, rel_path=rel_path).values()}
    graph_ids = _graph_ids(JOIN_SOURCE, rel_path)

    assert fingerprint_ids, "the fingerprinter produced no ids at all"
    assert graph_ids, "the graph extractor produced no ids at all"
    assert fingerprint_ids == graph_ids, (
        f"only in fingerprinter: {sorted(fingerprint_ids - graph_ids)}\n"
        f"only in graph:         {sorted(graph_ids - fingerprint_ids)}"
    )


def test_a_nested_class_is_qualified_by_its_enclosing_class(tmp_path):
    """The class branch dropped ``parent_class`` while the function branch kept it.

    So ``Service.Inner`` was recorded as ``Inner`` — the exact defect this issue
    describes, on the class kind rather than the function kind.
    """
    fragment = _fragments(tmp_path, source=JOIN_SOURCE)[("Service", "Inner")]

    assert fragment.node_id.endswith(".Service.Inner")


# ------------------------- production paths are absolute, and must still join


def test_an_absolute_path_from_the_project_root_produces_a_joinable_id():
    """The blocker: production hands the detector absolute paths.

    ``rglob`` from ``PATH.PROJECT_ROOT`` yields absolute paths, so every id this
    module shipped was prefixed with the deploy root
    (``.opt.autobot.autobot-backend…``) while the graph relativises first. They
    never joined, and nothing reported it.
    """
    fragments = _fragments_from_repo_file(JOIN_SOURCE)
    handle = fragments[("Service", "handle")]

    assert not handle.node_id.startswith("."), f"id carries an absolute prefix: {handle.node_id}"
    assert handle.node_id.startswith("autobot-backend.code_intelligence.")


def test_a_path_outside_the_project_is_left_alone_rather_than_guessed_at():
    """Declining to give an identity beats inventing one."""
    outside = CodeFragment(file_path="/etc/somewhere/mod.py", start_line=1, end_line=2, source_code="", entity_name="f")

    assert outside.node_id == ".etc.somewhere.mod.f", "a path outside the project must be left as it was"


# ------------------ the walk must not lose definitions, on shapes that have them


def test_definitions_nested_inside_functions_are_still_found(tmp_path):
    """The guard that used to be vacuous.

    Its predecessor asserted the scope-aware walk found everything ``ast.walk``
    found — using a fixture with no definition inside a function body, no
    ``if``/``try``/``for``/``with``, and nothing ``async``. It stayed green when
    the walk stopped descending into function bodies entirely.
    """
    names = {name for _, name in _fragments(tmp_path)}

    for nested in ("helper", "conditional", "guarded", "recovered", "looped", "managed", "inner_async"):
        assert nested in names, f"{nested} was lost by the walk"


def test_a_deeply_chained_expression_does_not_lose_the_whole_file(tmp_path):
    """``ast.walk`` never recursed, so the replacement must not either.

    A ``RecursionError`` here is caught by ``_extract_fragments`` and degrades to
    "this file has no fragments" — a silent, total coverage loss for that file.
    """
    chained = "def f():\n    return " + " + ".join(["1"] * 1500) + "\n"

    assert "f" in {name for _, name in _fragments(tmp_path, source=chained)}
