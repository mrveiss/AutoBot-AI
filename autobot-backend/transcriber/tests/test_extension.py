# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss

from middleware.builtin.transcriber_extension import TranscriberExtension, get_transcriber_router


def test_transcriber_extension_name():
    ext = TranscriberExtension()
    assert ext.name == "transcriber"


def test_get_transcriber_router_returns_router():
    from fastapi import APIRouter

    router = get_transcriber_router()
    assert isinstance(router, APIRouter)
