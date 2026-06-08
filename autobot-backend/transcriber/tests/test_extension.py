# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
# Author: mrveiss

from extensions.builtin.transcriber_extension import TranscriberExtension, get_transcriber_router


def test_transcriber_extension_name():
    ext = TranscriberExtension()
    assert ext.name == "transcriber"


def test_get_transcriber_router_returns_router():
    from fastapi import APIRouter

    router = get_transcriber_router()
    assert isinstance(router, APIRouter)
