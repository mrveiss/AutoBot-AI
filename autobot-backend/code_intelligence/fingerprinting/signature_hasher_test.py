# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The signature fingerprint must be stable under body edits (#13509).

`CodeIndexer` re-embeds every node in a file whose content hash moved, so a
reformat costs the same as a rewrite — and our own PostToolUse hook reformats
every `.py` we touch. This fingerprint is the second-stage check that makes the
difference, so what matters is exactly two properties:

- it does **not** change when only bodies or formatting change (the saving)
- it **does** change when the interface changes (the correctness)

and, above both, that every failure path is read as "re-analyse" rather than
"unchanged" — a false positive here serves a stale graph indefinitely, while a
false negative costs one re-embed.
"""

from code_intelligence.fingerprinting.signature_hasher import (
    SIGNATURE_FINGERPRINT_VERSION,
    compute_signature_fingerprint,
    signature_matches,
)

BASE = '''
import os
from typing import List


@decorator
def fetch(user_id: int, *, retries: int = 3) -> List[str]:
    """Docstring."""
    result = []
    for _ in range(retries):
        result.append(os.getenv("X"))
    return result


class Service:
    def run(self, payload: dict) -> bool:
        return bool(payload)
'''


def _fp(src: str) -> str:
    fp = compute_signature_fingerprint(src)
    assert fp is not None, "fixture should be parseable"
    return fp


class TestStableUnderBodyChanges:
    def test_reformatting_does_not_change_the_fingerprint(self):
        reformatted = BASE.replace("    result = []", "    result = []  # noqa").replace(
            '"""Docstring."""', '"""Docstring changed entirely."""'
        )

        assert _fp(reformatted) == _fp(BASE)

    def test_rewriting_a_body_does_not_change_the_fingerprint(self):
        rewritten = BASE.replace(
            '    result = []\n    for _ in range(retries):\n        result.append(os.getenv("X"))\n    return result',
            "    return [os.getenv('X')] * retries",
        )
        assert rewritten != BASE

        assert _fp(rewritten) == _fp(BASE)

    def test_a_method_body_change_does_not_change_the_fingerprint(self):
        assert _fp(BASE.replace("return bool(payload)", "return len(payload) > 0")) == _fp(BASE)


class TestChangesWhenTheInterfaceChanges:
    def test_adding_a_parameter_changes_it(self):
        assert _fp(
            BASE.replace("user_id: int, *, retries: int = 3", "user_id: int, *, retries: int = 3, dry: bool = False")
        ) != _fp(BASE)

    def test_changing_the_return_annotation_changes_it(self):
        assert _fp(BASE.replace("-> List[str]:", "-> List[bytes]:")) != _fp(BASE)

    def test_renaming_a_function_changes_it(self):
        assert _fp(BASE.replace("def fetch(", "def fetch_all(")) != _fp(BASE)

    def test_adding_an_import_changes_it(self):
        assert _fp(BASE.replace("import os", "import os\nimport sys")) != _fp(BASE)

    def test_removing_a_decorator_changes_it(self):
        assert _fp(BASE.replace("@decorator\n", "")) != _fp(BASE)

    def test_adding_a_method_changes_it(self):
        assert _fp(
            BASE.replace(
                "        return bool(payload)",
                "        return bool(payload)\n\n    def stop(self) -> None:\n        pass",
            )
        ) != _fp(BASE)

    def test_changing_a_method_signature_changes_it(self):
        assert _fp(
            BASE.replace("def run(self, payload: dict) -> bool:", "def run(self, payload: dict, force: bool) -> bool:")
        ) != _fp(BASE)


class TestFailsOpen:
    def test_unparseable_source_yields_none(self):
        assert compute_signature_fingerprint("def broken(:\n") is None

    def test_none_never_matches(self):
        """The whole safety property in one assertion."""
        good = _fp(BASE)
        assert signature_matches(None, good) is False
        assert signature_matches(good, None) is False
        assert signature_matches(None, None) is False

    def test_a_non_string_fingerprint_never_matches(self):
        good = _fp(BASE)
        assert signature_matches({"unexpected": "shape"}, good) is False
        assert signature_matches(good, 12345) is False

    def test_an_unknown_version_never_matches(self):
        """A stored hash from another definition is not comparable."""
        good = _fp(BASE)
        stale = good.replace(f"v{SIGNATURE_FINGERPRINT_VERSION}:", "v0:")

        assert signature_matches(stale, good) is False

    def test_two_equal_fingerprints_of_an_unknown_version_still_do_not_match(self):
        """Pins the version guard itself, not just digest inequality.

        The other version tests pass on the digest differing, so they hold even
        with the prefix check deleted — found by mutating it away and seeing
        nothing fail. This is the case only the guard catches: identical strings
        carrying a version this build does not understand. Comparing them as
        equal would treat a fingerprint computed under different rules as
        authoritative.
        """
        stale = "v0:" + "a" * 64

        assert signature_matches(stale, stale) is False

    def test_a_version_bump_invalidates_every_stored_fingerprint(self):
        """AC: bumping the version forces full re-analysis on the next run."""
        import code_intelligence.fingerprinting.signature_hasher as mod

        stored = _fp(BASE)
        original = mod.SIGNATURE_FINGERPRINT_VERSION
        try:
            mod.SIGNATURE_FINGERPRINT_VERSION = original + 1
            recomputed = compute_signature_fingerprint(BASE)
            assert recomputed is not None
            assert signature_matches(stored, recomputed) is False, "a bumped version must not match"
        finally:
            mod.SIGNATURE_FINGERPRINT_VERSION = original


class TestIdenticalInputMatches:
    def test_the_same_source_matches_itself(self):
        """Without this the fingerprint would be useless — it would never save anything."""
        assert signature_matches(_fp(BASE), _fp(BASE)) is True

    def test_the_version_is_carried_in_the_value(self):
        assert _fp(BASE).startswith(f"v{SIGNATURE_FINGERPRINT_VERSION}:")
