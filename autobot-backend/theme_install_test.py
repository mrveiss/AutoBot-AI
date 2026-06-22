# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
import io
import json
import zipfile

import pytest
from fastapi import HTTPException, UploadFile

import theme_install


def _theme_zip(theme_id="aqua", css=None) -> UploadFile:
    css = css or f'[data-theme-variant="{theme_id}"] {{ --bg-primary: #eef; }}'
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w") as zf:
        zf.writestr("theme.json", json.dumps({"id": theme_id, "name": "Aqua", "author": "me", "version": "1.0.0"}))
        zf.writestr("theme.css", css)
    buf.seek(0)
    return UploadFile(filename=f"{theme_id}.zip", file=buf)


@pytest.fixture(autouse=True)
def _tmp_themes(tmp_path, monkeypatch):
    monkeypatch.setattr(theme_install, "themes_dir", lambda: tmp_path)


@pytest.mark.asyncio
async def test_install_then_list_then_uninstall():
    desc = await theme_install.install_theme_from_zip(_theme_zip("aqua"))
    assert desc.id == "aqua"
    assert [t.id for t in theme_install.list_installed_themes()] == ["aqua"]
    assert theme_install.theme_css_path("aqua").is_file()
    theme_install.uninstall_theme("aqua")
    assert theme_install.list_installed_themes() == []


@pytest.mark.asyncio
async def test_install_rejects_unscoped_css():
    with pytest.raises(HTTPException):
        await theme_install.install_theme_from_zip(_theme_zip("bad", css="body { color: red }"))


@pytest.mark.asyncio
async def test_duplicate_install_conflicts():
    await theme_install.install_theme_from_zip(_theme_zip("dup"))
    with pytest.raises(HTTPException) as exc:
        await theme_install.install_theme_from_zip(_theme_zip("dup"))
    assert exc.value.status_code == 409
