# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Issue #19566: template regexes are compiled once and score exactly as before.

``_FIXTURE_GOLDEN`` was captured from the pre-#19566 code (one uncompiled
``re.search`` / ``re.findall`` per template pattern, per class), so a drift in
any pattern type, confidence or indicator fails here.
"""

import asyncio
import re
import textwrap

import pytest

from api.analytics_architecture import PATTERN_TEMPLATES, ArchitectureAnalyzer

_FIXTURES = {
    "factory_singleton.py": """
        import threading
        class WidgetFactory:
            _instance = None
            _lock = threading.Lock()
            def create_widget(self):
                return Widget()
            def make(self):
                return cls()
            @classmethod
            def get_instance(cls):
                if cls._instance is None:
                    cls._instance = cls()
                return cls._instance
        """,
    "observer_service.py": """
        import redis
        class EventPublisher:
            def subscribe(self, fn):
                self._listeners.append(fn)
            def notify(self):
                for fn in self._listeners:
                    fn()
                self._bus.notify()
        class CacheService:
            async def run(self):
                await self.fetch()
                return self._client.get("k")
        """,
    "router_module.py": """
        from fastapi import APIRouter, Depends
        router = APIRouter()
        @router.get("/a")
        async def read_a(dep=Depends(get_dep)):
            return Thing()
        @router.post("/b")
        async def write_b():
            return None
        """,
}

_FIXTURE_GOLDEN = {
    "factory_singleton.py": [
        (
            "factory",
            "WidgetFactory",
            0.8,
            (
                "class_name:Factory",
                "method:create_widget",
                "method:make",
                "code_pattern:return\\s+\\w+\\(",
                "code_pattern:cls\\(",
            ),
        )
    ],
    "observer_service.py": [
        (
            "autobot_service",
            "CacheService",
            0.5,
            ("class_name:Service", "code_pattern:async\\s+def\\s+\\w+", "code_pattern:await\\s+self\\."),
        ),
        (
            "observer",
            "EventPublisher",
            0.8,
            (
                "class_name:Publisher",
                "method:subscribe",
                "method:notify",
                "code_pattern:for\\s+\\w+\\s+in\\s+self\\._\\w+s:",
                "code_pattern:\\.notify\\(",
            ),
        ),
        ("service_layer", "CacheService", 0.45, ("class_name:Service", "method:run")),
    ],
    "router_module.py": [
        (
            "autobot_router",
            None,
            1.0,
            (
                "pattern:router\\s*=\\s*APIRouter\\(",
                "pattern:@router\\.\\w+\\(",
                "import:fastapi",
                "import:fastapi.APIRouter",
                "import:fastapi.APIRouter",
                "import:fastapi.Depends",
            ),
        ),
        ("autobot_service", None, 0.6, ("pattern:async\\s+def\\s+\\w+",)),
        ("dependency_injection", None, 0.5, ("pattern:Depends\\(", "import:fastapi.Depends")),
    ],
}


def _analyze(tmp_path, name, body):
    path = tmp_path / name
    path.write_text(textwrap.dedent(body).lstrip(), encoding="utf-8")
    analysis = asyncio.run(ArchitectureAnalyzer(str(tmp_path))._analyze_file(str(path), list(PATTERN_TEMPLATES)))
    return sorted(
        (m.pattern_type.value, m.class_name, round(m.confidence, 6), tuple(m.indicators_found))
        for m in analysis.patterns_found
    )


@pytest.mark.parametrize("name", sorted(_FIXTURES))
def test_fixture_results_match_the_pre_19566_golden(tmp_path, name):
    assert _analyze(tmp_path, name, _FIXTURES[name]) == _FIXTURE_GOLDEN[name]


def test_every_template_regex_is_compiled_once_at_import():
    for template in PATTERN_TEMPLATES.values():
        assert [rx.pattern for rx in template.code_res] == template.code_patterns
        assert [rx.pattern for rx in template.method_res] == template.method_indicators
        assert all(rx.flags & re.IGNORECASE for rx in template.method_res)
