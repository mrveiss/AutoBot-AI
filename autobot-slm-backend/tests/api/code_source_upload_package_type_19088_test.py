# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""upload-package takes only a bare .tar.gz / .tgz name (#19088)."""

from __future__ import annotations

import pytest
from fastapi import HTTPException

from api import code_source


class FakeUpload:
    def __init__(self, filename):
        self.filename = filename

    async def read(self):
        raise AssertionError("a refused upload must not be read")


@pytest.mark.asyncio
@pytest.mark.parametrize("name", ["x.exe", "x.zip", "a/b.tar.gz", "..\\x.tgz", "x.tar", ".tar.gz", "", None])
async def test_upload_package_refuses_a_bad_name(name):
    with pytest.raises(HTTPException) as info:
        await code_source.upload_package(db=None, _={}, role_name="r", commit_hash="abc", package=FakeUpload(name))
    assert info.value.status_code == 400
