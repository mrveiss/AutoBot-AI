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
from code_intelligence.fingerprinting.types import CodeFragment

SOURCE = """
def module_level(a):
    return a + 1


class Service:
    def handle(self, request):
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
    # The detector records whatever path it was handed; the id namespace is
    # project-relative, so re-point the fragments at the repo-relative path.
    for fragment in found:
        fragment.file_path = rel_path
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
