# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #19566: one combined hook regex returns what one ``\\bhook\\b`` per hook did."""

import re

import pytest

from code_analysis.src.frontend_analyzer import _LIFECYCLE_HOOK_RES, FrontendAnalyzer

# The pre-#19566 per-hook lists, verbatim: the oracle the combined regex must agree with.
_ORACLE_HOOKS = {
    "vue": [
        "created", "mounted", "updated", "destroyed", "beforeCreate", "beforeMount",
        "beforeUpdate", "beforeDestroy", "onMounted", "onUpdated", "onUnmounted",
    ],
    "react": [
        "componentDidMount", "componentDidUpdate", "componentWillUnmount",
        "useEffect", "useState", "useCallback", "useMemo",
    ],
}  # fmt: skip

_FIXTURES = [
    "export default { created() {}, mounted() {}, beforeDestroy() {} }",
    "onMounted(() => {}); onUnmounted(() => {}); const x = onMountedX; mountedHook()",
    "beforeCreated(); this.updated = 1; destroyed_flag; created$; _mounted",
    "useEffect(() => {}, []); const [a, b] = useState(0); useEffectual(); useMemoized",
    "class A extends Component { componentDidMount() {} componentWillUnmount() {} }",
    "mounted mounted mounted created",
    "",
]


def _oracle(content: str, framework: str) -> list:
    return [h for h in _ORACLE_HOOKS.get(framework, []) if re.search(rf"\b{h}\b", content)]


@pytest.mark.parametrize("framework", ["vue", "react", "angular"])
@pytest.mark.parametrize("content", _FIXTURES)
def test_combined_regex_matches_the_per_hook_oracle(framework, content):
    assert FrontendAnalyzer()._extract_lifecycle_hooks(content, framework) == _oracle(content, framework)


def test_known_fixture_results():
    analyzer = FrontendAnalyzer()
    assert analyzer._extract_lifecycle_hooks(_FIXTURES[1], "vue") == ["onMounted", "onUnmounted"]
    assert analyzer._extract_lifecycle_hooks(_FIXTURES[3], "react") == ["useEffect", "useState"]


def test_hook_regexes_are_compiled_once_at_import():
    assert set(_LIFECYCLE_HOOK_RES) == {"vue", "react"}
    assert all(isinstance(rx, re.Pattern) for rx in _LIFECYCLE_HOOK_RES.values())
