# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Developer Speedup — code templates catalog.

Curated, reusable code templates surfaced by ``GET /api/dev-speedup/templates``
and rendered in the Developer Speedup view (#902). Each entry matches the
frontend ``CodeTemplate`` shape:
``id, name, description, language, template, variables, category``.

``{{variable}}`` placeholders are filled in by the client; ``variables`` lists
the placeholder names so the UI can render input fields.
"""

from typing import Any, Dict, List

CODE_TEMPLATES: List[Dict[str, Any]] = [
    {
        "id": "py-fastapi-router",
        "name": "FastAPI Router",
        "description": "A FastAPI APIRouter with a single GET endpoint.",
        "language": "python",
        "category": "backend",
        "variables": ["resource", "Resource"],
        "template": (
            "from fastapi import APIRouter\n\n"
            "router = APIRouter()\n\n\n"
            '@router.get("/{{resource}}")\n'
            "async def list_{{resource}}():\n"
            '    """List {{Resource}} items."""\n'
            '    return {"items": []}\n'
        ),
    },
    {
        "id": "py-pytest-case",
        "name": "Pytest Test Case",
        "description": "An async pytest test with arrange/act/assert structure.",
        "language": "python",
        "category": "testing",
        "variables": ["unit", "behavior"],
        "template": (
            "import pytest\n\n\n"
            "@pytest.mark.asyncio\n"
            "async def test_{{unit}}_{{behavior}}():\n"
            "    # Arrange\n"
            "    subject = None\n"
            "    # Act\n"
            "    result = subject\n"
            "    # Assert\n"
            "    assert result is not None\n"
        ),
    },
    {
        "id": "py-pydantic-model",
        "name": "Pydantic Model",
        "description": "A Pydantic v2 response model with typed fields.",
        "language": "python",
        "category": "backend",
        "variables": ["Model", "field"],
        "template": (
            "from pydantic import BaseModel\n\n\n"
            "class {{Model}}(BaseModel):\n"
            '    """{{Model}} payload."""\n\n'
            "    {{field}}: str\n"
        ),
    },
    {
        "id": "vue-composable",
        "name": "Vue Composable",
        "description": "A Vue 3 composable returning reactive state and a fetcher.",
        "language": "typescript",
        "category": "frontend",
        "variables": ["name", "Resource"],
        "template": (
            "import { ref } from 'vue'\n"
            "import ApiClient from '@/utils/ApiClient'\n"
            "import { getApiBase } from '@/config/ssot-config'\n\n"
            "export function use{{Resource}}() {\n"
            "  const items = ref<unknown[]>([])\n\n"
            "  async function fetch{{Resource}}(): Promise<void> {\n"
            "    const data = await ApiClient.get<{ items: unknown[] }>("
            "`${getApiBase()}/{{name}}`)\n"
            "    items.value = data.items || []\n"
            "  }\n\n"
            "  return { items, fetch{{Resource}} }\n"
            "}\n"
        ),
    },
    {
        "id": "vue-sfc",
        "name": "Vue Single-File Component",
        "description": "A minimal Vue 3 SFC with <script setup> and typed props.",
        "language": "vue",
        "category": "frontend",
        "variables": ["title"],
        "template": (
            "<template>\n"
            '  <section class="panel">\n'
            "    <h2>{{ title }}</h2>\n"
            "  </section>\n"
            "</template>\n\n"
            '<script setup lang="ts">\n'
            "defineProps<{ title: string }>()\n"
            "</script>\n"
        ),
    },
]
