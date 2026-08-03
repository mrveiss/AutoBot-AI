# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Regression test for #13259: POST /skills/catalog/{name}/install dropped its
payload.

response_model=DataResponse[SkillCatalogInstallData] validated the flat
{"success", "id", "name", "version", "trust_level"} dict against the
envelope, discarding everything but `success`. The fix declares
response_model=SkillCatalogInstallData directly.
"""

import uuid
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from sqlalchemy.ext.asyncio import create_async_engine

from api.skills import router
from skills.models import SkillPackage, SkillsBase


def _make_client() -> TestClient:
    app = FastAPI()
    app.include_router(router, prefix="/api/skills")
    return TestClient(app)


class TestInstallCatalogSkillResponsePayload:
    @pytest.mark.asyncio
    async def test_returns_the_real_installed_package_fields_on_the_wire(self):
        engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        async with engine.begin() as conn:
            await conn.run_sync(SkillsBase.metadata.create_all)

        fake_pkg = SkillPackage(
            id=str(uuid.uuid4()),
            name="demo-skill",
            version="2.0.0",
            skill_md="# demo",
            trust_level="monitored",
        )

        mock_importer = AsyncMock()
        mock_importer.import_http_catalog.return_value = [{"skill_md": "# demo"}]
        mock_importer.install_from_catalog.return_value = fake_pkg

        client = _make_client()
        try:
            with (
                patch("skills.external_importer.ExternalSkillImporter", return_value=mock_importer),
                patch("skills.db.get_skills_engine", return_value=engine),
            ):
                response = client.post(
                    "/api/skills/catalog/demo-skill/install",
                    json={"catalog_url": "https://catalog.invalid/skills"},
                )
        finally:
            await engine.dispose()

        assert response.status_code == 200
        body = response.json()
        assert body["name"] == "demo-skill"
        assert body["version"] == "2.0.0"
        assert body["trust_level"] == "monitored"
        assert body["success"] is True
