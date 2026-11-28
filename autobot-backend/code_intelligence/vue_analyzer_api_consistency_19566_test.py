# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #19566: one combined regex per Vue API style agrees with the per-pattern ``any``."""

import re

import pytest

from code_intelligence.vue_analyzer import _COMPOSITION_API_RE, _OPTIONS_API_RE, VueAnalyzer

# The pre-#19566 indicator lists, verbatim: the oracle the combined regexes must agree with.
_COMPOSITION = [
    r"\bsetup\s*\(",
    r"\bref\s*\(",
    r"\breactive\s*\(",
    r"\bcomputed\s*\(",
    r"\bwatch\s*\(",
    r"\bwatchEffect\s*\(",
    r"\bonMounted\s*\(",
    r"\bonUnmounted\s*\(",
]
_OPTIONS = [
    r"\bdata\s*\(\s*\)\s*\{", r"\bmethods\s*:\s*\{", r"\bcomputed\s*:\s*\{",
    r"\bwatch\s*:\s*\{", r"\bmounted\s*\(\s*\)\s*\{", r"\bcreated\s*\(\s*\)\s*\{",
]  # fmt: skip

_FIXTURES = [
    "const a = ref(0); const b = computed(() => a.value)",
    "export default { data() { return {} }, methods: { go() {} } }",
    "setup() { watchEffect(() => {}) } methods : {",
    "watchEffect (fn); mounted ( ) {",
    "myref(0); xsetup(); computedValue(); watchers: {}; created() ;",
    "data ( )\n{ } watch:{ } onUnmounted\t(",
    "reactive\n(state) created(){",
    "",
]


@pytest.mark.parametrize("content", _FIXTURES)
def test_combined_regexes_match_the_per_pattern_oracle(content):
    assert (_COMPOSITION_API_RE.search(content) is not None) == any(re.search(p, content) for p in _COMPOSITION)
    assert (_OPTIONS_API_RE.search(content) is not None) == any(re.search(p, content) for p in _OPTIONS)


@pytest.mark.parametrize(
    ("content", "flagged"),
    [(_FIXTURES[0], False), (_FIXTURES[1], False), (_FIXTURES[2], True), (_FIXTURES[3], True), (_FIXTURES[4], False)],
)
def test_mixed_api_issue_is_raised_exactly_when_both_styles_appear(content, flagged):
    analyzer = VueAnalyzer()
    analyzer._check_api_consistency(content, base_line=1)
    assert any(i.title == "Mixed API styles" for i in analyzer.issues) is flagged
