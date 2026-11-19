"""Inline-generic counting in the frontend API-contract ratchet reads code, not prose (#15771, #17377).

Split out of ``frontend_api_contract_ratchet_test`` to keep that module under the line ceiling.
"""

from __future__ import annotations

from pathlib import Path

import pytest
from repo_tests.frontend_api_contract_ratchet_test import _inline_generic_count


@pytest.mark.parametrize(
    ("label", "name", "source", "expected"),
    [
        ("code", "a.ts", "const r = api.get<Shape>('/x')\n", 1),
        ("line comment quoting it", "a.ts", "// was api.get<Shape>('/x'), now derived\n", 0),
        ("block comment quoting it", "a.ts", "/* api.get<Shape>('/x') */\nconst a = 1\n", 0),
        ("code beside a comment", "a.ts", "// api.get<A>()\nconst r = api.post<B>('/y')\n", 1),
        ("trailing comment after code", "a.ts", "const a = 1 // was api.get<Shape>('/x')\n", 0),
        ("code and a trailing comment", "a.ts", "const r = api.get<A>('/x') // not api.get<B>('/y')\n", 1),
        ("generic only inside a string literal", "a.ts", "const s = \"api.get<Shape>('/x')\"\n", 1),
        ("slashes inside a string are not a comment", "a.ts", "const u = 'http://h'; api.get<Shape>('/x')\n", 1),
        (
            "vue script block",
            "a.vue",
            "<script setup lang=\"ts\">\nconst r = api.get<Shape>('/x') // note\n</script>\n",
            1,
        ),
        ("vue template html comment", "a.vue", "<template><!-- was api.get<Shape>('/x') --></template>\n", 0),
        (
            "vue html comment beside script call",
            "a.vue",
            "<template><!-- api.get<A>('/x') --></template>\n<script setup lang=\"ts\">\nconst r = api.get<B>('/y')\n</script>\n",
            1,
        ),
    ],
)
def test_the_inline_generic_count_reads_code_and_not_prose(
    tmp_path: Path, label: str, name: str, source: str, expected: int
) -> None:
    """#15771: documenting a removal must not keep the removed construct counted; strings stay counted."""
    (tmp_path / name).write_text(source, encoding="utf-8")
    assert _inline_generic_count(tmp_path) == expected, label
