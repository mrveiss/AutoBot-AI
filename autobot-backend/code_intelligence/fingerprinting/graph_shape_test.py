# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The fingerprint must move whenever the persisted graph moves (#13509).

`CodeIndexer` re-embeds every node in a file whose content hash moved, so a
reformat costs the same as a rewrite. This fingerprint is the second-stage check
that makes the difference, and it has exactly two jobs:

- it does **not** change when only line numbers move (the saving)
- it **does** change when any other persisted field changes (the correctness)

The correctness half is what the first implementation got wrong. It hashed the
module's AST interface, which cannot see nested definitions and cannot see call
edges at all — so a renamed closure or a changed call target left the
fingerprint equal while the extracted graph differed, and the skip path then
served the old graph forever. Hashing the extractor's own output instead makes
the invariant mechanical: everything persisted is covered except ``line``.

The tests below therefore work on extractor-shaped dicts, and the ones that
matter most are the two that the AST version passed while being wrong.
"""

from code_intelligence.fingerprinting.graph_shape import (
    GRAPH_SHAPE_FINGERPRINT_VERSION,
    compute_graph_shape_fingerprint,
    shape_matches,
)


def _node(node_id, name, kind="function", path="pkg/m.py", line=1, parent=None):
    return {"id": node_id, "name": name, "kind": kind, "source_path": path, "line": line, "parent": parent}


def _edge(source, target_name, line=1, path="pkg/m.py"):
    return {
        "source": source,
        "target_name": target_name,
        "module_path": "pkg.m",
        "current_class": None,
        "kind": "calls",
        "source_path": path,
        "line": line,
    }


BASE = {
    "nodes": [_node("pkg.m.fetch", "fetch", line=4), _node("pkg.m.S", "S", kind="class", line=10)],
    "edges": [_edge("pkg.m.fetch", "getenv", line=5)],
}


def _fp(extracted):
    value = compute_graph_shape_fingerprint(extracted)
    assert value is not None, "fixture should be fingerprintable"
    return value


class TestStableWhenOnlyLinesMove:
    def test_moving_every_line_does_not_change_it(self):
        """The saving. A reformat shifts lines and nothing else."""
        shifted = {
            "nodes": [{**n, "line": n["line"] + 40} for n in BASE["nodes"]],
            "edges": [{**e, "line": e["line"] + 40} for e in BASE["edges"]],
        }

        assert _fp(shifted) == _fp(BASE)

    def test_reordering_definitions_does_not_change_it(self):
        reordered = {"nodes": list(reversed(BASE["nodes"])), "edges": BASE["edges"]}

        assert _fp(reordered) == _fp(BASE)


class TestChangesWhenTheGraphChanges:
    def test_renaming_a_nested_function_changes_it(self):
        """Bug 1: the AST version could not see nested definitions.

        The extractor emits a node for a closure just as it does for a top-level
        def, so renaming one changes the node set. A top-level AST scan reported
        "unchanged" and the new node was never inserted.
        """
        nested = {"nodes": BASE["nodes"] + [_node("pkg.m.outer.inner", "inner")], "edges": BASE["edges"]}
        renamed = {"nodes": BASE["nodes"] + [_node("pkg.m.outer.renamed", "renamed")], "edges": BASE["edges"]}

        assert _fp(nested) != _fp(renamed)

    def test_changing_a_call_target_changes_it(self):
        """Bug 2: the AST version could not see call edges at all.

        `os.getenv` -> `os.environ.get` is a pure body edit with no interface
        change, and it rewrites the persisted edge set.
        """
        rewritten = {"nodes": BASE["nodes"], "edges": [_edge("pkg.m.fetch", "get", line=5)]}

        assert _fp(rewritten) != _fp(BASE)

    def test_adding_a_call_changes_it(self):
        added = {"nodes": BASE["nodes"], "edges": BASE["edges"] + [_edge("pkg.m.fetch", "sleep")]}

        assert _fp(added) != _fp(BASE)

    def test_removing_every_call_changes_it(self):
        assert _fp({"nodes": BASE["nodes"], "edges": []}) != _fp(BASE)

    def test_adding_a_node_changes_it(self):
        added = {"nodes": BASE["nodes"] + [_node("pkg.m.other", "other")], "edges": BASE["edges"]}

        assert _fp(added) != _fp(BASE)

    def test_changing_a_node_kind_changes_it(self):
        """A function becoming a class keeps the id but changes the embedded text."""
        changed = {"nodes": [{**BASE["nodes"][0], "kind": "class"}, BASE["nodes"][1]], "edges": BASE["edges"]}

        assert _fp(changed) != _fp(BASE)

    def test_changing_a_nodes_parent_changes_it(self):
        changed = {"nodes": [{**BASE["nodes"][0], "parent": "pkg.m.S"}, BASE["nodes"][1]], "edges": BASE["edges"]}

        assert _fp(changed) != _fp(BASE)

    def test_moving_a_file_changes_it(self):
        moved = {
            "nodes": [{**n, "source_path": "pkg/moved.py"} for n in BASE["nodes"]],
            "edges": BASE["edges"],
        }

        assert _fp(moved) != _fp(BASE)


class TestFailsOpen:
    def test_a_non_dict_extraction_yields_none(self):
        assert compute_graph_shape_fingerprint(None) is None
        assert compute_graph_shape_fingerprint("nodes") is None

    def test_a_malformed_extraction_yields_none(self):
        assert compute_graph_shape_fingerprint({"nodes": "not-a-list", "edges": []}) is None
        assert compute_graph_shape_fingerprint({"nodes": []}) is None

    def test_a_non_dict_node_yields_none(self):
        assert compute_graph_shape_fingerprint({"nodes": ["oops"], "edges": []}) is None

    def test_none_never_matches(self):
        """The whole safety property in one assertion."""
        good = _fp(BASE)
        assert shape_matches(None, good) is False
        assert shape_matches(good, None) is False
        assert shape_matches(None, None) is False

    def test_a_non_string_fingerprint_never_matches(self):
        good = _fp(BASE)
        assert shape_matches({"unexpected": "shape"}, good) is False
        assert shape_matches(good, 12345) is False

    def test_an_unknown_version_never_matches(self):
        good = _fp(BASE)
        stale = good.replace(f"v{GRAPH_SHAPE_FINGERPRINT_VERSION}:", "v0:")

        assert shape_matches(stale, good) is False

    def test_two_equal_fingerprints_of_an_unknown_version_still_do_not_match(self):
        """Pins the version guard itself, not just digest inequality.

        The test above passes on the digests differing, so it holds even with the
        prefix check deleted. This is the case only the guard catches: identical
        strings carrying a version this build does not understand.
        """
        stale = "v0:" + "a" * 64

        assert shape_matches(stale, stale) is False

    def test_a_version_bump_invalidates_every_stored_fingerprint(self):
        """AC: bumping the version forces full re-analysis on the next run."""
        import code_intelligence.fingerprinting.graph_shape as mod

        stored = _fp(BASE)
        original = mod.GRAPH_SHAPE_FINGERPRINT_VERSION
        try:
            mod.GRAPH_SHAPE_FINGERPRINT_VERSION = original + 1
            recomputed = compute_graph_shape_fingerprint(BASE)
            assert recomputed is not None
            assert shape_matches(stored, recomputed) is False, "a bumped version must not match"
        finally:
            mod.GRAPH_SHAPE_FINGERPRINT_VERSION = original


class TestIdenticalInputMatches:
    def test_the_same_extraction_matches_itself(self):
        """Without this the fingerprint would never save anything."""
        assert shape_matches(_fp(BASE), _fp(BASE)) is True

    def test_the_version_is_carried_in_the_value(self):
        assert _fp(BASE).startswith(f"v{GRAPH_SHAPE_FINGERPRINT_VERSION}:")
