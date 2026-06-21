#!/usr/bin/env python3
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Unit tests for check_no_orphan_refs.py (Issue #5349).

Validates the detection contract against the two bug shapes that
motivated the check (#5277 and #5340) plus common live-ref patterns
that must NOT be flagged.
"""

from __future__ import annotations

import importlib.util
import sys
from pathlib import Path

# Import the target script as a module.
_SCRIPT = Path(__file__).parent / "check_no_orphan_refs.py"
_spec = importlib.util.spec_from_file_location("check_no_orphan_refs", _SCRIPT)
assert _spec and _spec.loader
_mod = importlib.util.module_from_spec(_spec)
sys.modules["check_no_orphan_refs"] = _mod
_spec.loader.exec_module(_mod)


class TestFindDecls:
    def test_finds_ref_declaration(self):
        source = "const foo = ref<number>(0)\n"
        assert _mod._find_decls(source) == [("foo", 1)]

    def test_finds_shallow_ref(self):
        source = "const foo = shallowRef(null)\n"
        assert _mod._find_decls(source) == [("foo", 1)]

    def test_finds_reactive(self):
        source = "const foo = reactive({})\n"
        assert _mod._find_decls(source) == [("foo", 1)]

    def test_ignores_regular_const(self):
        source = "const foo = 42\n"
        assert _mod._find_decls(source) == []

    def test_line_numbers_correct(self):
        source = "\n\nconst foo = ref(0)\n"
        assert _mod._find_decls(source) == [("foo", 3)]


class TestIsReturned:
    def test_listed_in_return_object(self):
        source = """
        export function useX() {
          const foo = ref(0)
          return { foo }
        }
        """
        assert _mod._is_returned(source, "foo") is True

    def test_aliased_in_return_object(self):
        source = """
        return {
          foo: fooInternal,
          bar,
        }
        """
        assert _mod._is_returned(source, "foo") is True
        assert _mod._is_returned(source, "bar") is True

    def test_not_in_return(self):
        source = """
        return {
          other,
        }
        """
        assert _mod._is_returned(source, "foo") is False


class TestIsUsedInFile:
    def test_read_counts_as_use(self):
        source = "const foo = ref(0)\nreturn { foo }\nconsole.log(foo.value)\n"
        assert _mod._is_used_in_file(source, "foo") is True

    def test_write_counts_as_use(self):
        source = "const foo = ref(0)\nreturn { foo }\nfoo.value = 1\n"
        assert _mod._is_used_in_file(source, "foo") is True

    def test_declared_and_returned_only_is_orphan(self):
        # This is the #5340 pattern: declaration + return, nothing else.
        source = "const foo = ref(0)\nreturn { foo }\n"
        assert _mod._is_used_in_file(source, "foo") is False


class TestDetectionContract:
    """End-to-end: #5340 pattern is flagged, live refs are not."""

    def test_5340_pattern_flagged(self, tmp_path: Path):
        composable = tmp_path / "useX.ts"
        composable.write_text("const refactoringSuggestions = ref([])\n" "return { refactoringSuggestions }\n")
        orphans = _mod._scan_file(composable, tmp_path)
        assert len(orphans) == 1
        assert orphans[0].name == "refactoringSuggestions"

    def test_populated_ref_not_flagged(self, tmp_path: Path):
        composable = tmp_path / "useY.ts"
        composable.write_text(
            "const data = ref([])\n" "async function load() { data.value = await fetch() }\n" "return { data, load }\n"
        )
        orphans = _mod._scan_file(composable, tmp_path)
        assert orphans == []

    def test_v_model_target_not_flagged(self, tmp_path: Path):
        # A v-model target is usually read somewhere (e.g. passed to a
        # watcher or used in a computed()). Our heuristic treats ANY
        # reference beyond decl+return as "live".
        composable = tmp_path / "useZ.ts"
        composable.write_text(
            "const selectedCategory = ref('all')\n"
            "const filtered = computed(() => items.filter(i => i.cat === selectedCategory.value))\n"
            "return { selectedCategory, filtered }\n"
        )
        orphans = _mod._scan_file(composable, tmp_path)
        assert orphans == []

    def test_internal_ref_not_in_return_not_flagged(self, tmp_path: Path):
        composable = tmp_path / "useW.ts"
        composable.write_text("const internal = ref(0)\n" "function tick() { internal.value++ }\n" "return { tick }\n")
        orphans = _mod._scan_file(composable, tmp_path)
        # `internal` is not in the return — out of scope for this check.
        assert orphans == []

    def test_cross_file_di_write_not_flagged(self, tmp_path: Path):
        # Dependency-injection pattern: one composable declares the ref,
        # another writes to it via its deps argument. Script must not
        # flag this as orphan.
        composable = tmp_path / "useA.ts"
        composable.write_text("const exporting = ref(false)\n" "return { exporting }\n")
        consumer = tmp_path / "useB.ts"
        consumer.write_text("function go(deps) { deps.exporting.value = true }\n")
        orphans = _mod._scan_file(composable, tmp_path)
        assert orphans == []

    def test_cross_file_vue_template_write_not_flagged(self, tmp_path: Path):
        # External .vue template write pattern: consumer component
        # writes ``obj.silenceThreshold.value = x`` in an event handler.
        composable = tmp_path / "useVoice.ts"
        composable.write_text("const silenceThreshold = ref(1500)\n" "return { silenceThreshold }\n")
        consumer = tmp_path / "Panel.vue"
        consumer.write_text('<input @input="voice.silenceThreshold.value = Number($event.target.value)" />')
        orphans = _mod._scan_file(composable, tmp_path)
        assert orphans == []


if __name__ == "__main__":
    # Simple smoke test without pytest.
    passed = 0
    failed = 0
    for cls_name in dir(sys.modules[__name__]):
        cls = getattr(sys.modules[__name__], cls_name)
        if not (isinstance(cls, type) and cls_name.startswith("Test")):
            continue
        instance = cls()
        for method_name in dir(instance):
            if not method_name.startswith("test_"):
                continue
            method = getattr(instance, method_name)
            # Skip tests that need pytest's tmp_path fixture.
            import inspect

            if "tmp_path" in inspect.signature(method).parameters:
                continue
            try:
                method()
                passed += 1
            except AssertionError as e:
                failed += 1
                print(f"FAIL {cls_name}.{method_name}: {e}", file=sys.stderr)
    print(f"{passed} passed, {failed} failed (tests requiring pytest skipped)")
    sys.exit(0 if failed == 0 else 1)
