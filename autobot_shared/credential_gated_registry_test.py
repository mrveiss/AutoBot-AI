# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared credential-gated registry base (#11664)."""

import logging

from autobot_shared.credential_gated_registry import (
    CredentialGatedRegistry,
    gated_registry_singleton,
)


class TestCredentialGatedRegistry:
    def test_get_entry_absent_returns_none(self):
        registry = CredentialGatedRegistry()
        assert registry._get_entry("missing") is None

    def test_store_entry_returns_true_when_new(self):
        registry = CredentialGatedRegistry()
        assert registry._store_entry("a", object()) is True

    def test_store_entry_returns_false_and_warns_on_replace(self, caplog):
        registry = CredentialGatedRegistry()
        registry._store_entry("a", object(), kind="widget")
        with caplog.at_level(logging.WARNING):
            assert registry._store_entry("a", object(), kind="widget") is False
        assert "Replacing existing widget: a" in caplog.text

    def test_entry_names_preserve_insertion_order(self):
        registry = CredentialGatedRegistry()
        registry._store_entry("b", 1)
        registry._store_entry("a", 2)
        assert registry._entry_names() == ["b", "a"]

    def test_get_entry_returns_stored_value(self):
        registry = CredentialGatedRegistry()
        sentinel = object()
        registry._store_entry("x", sentinel)
        assert registry._get_entry("x") is sentinel


class TestGatedRegistrySingleton:
    def test_returns_same_instance_and_populates_once(self):
        calls = []
        get = gated_registry_singleton(CredentialGatedRegistry, calls.append)
        first = get()
        assert get() is first
        assert calls == [first]

    def test_populate_failure_is_swallowed_and_logged(self, caplog):
        def boom(_registry):
            raise RuntimeError("no creds")

        get = gated_registry_singleton(CredentialGatedRegistry, boom)
        with caplog.at_level(logging.WARNING):
            registry = get()
        assert isinstance(registry, CredentialGatedRegistry)
        assert "auto-registration failed" in caplog.text

    def test_post_populate_runs_after_populate(self):
        order = []
        get = gated_registry_singleton(
            CredentialGatedRegistry,
            lambda _r: order.append("populate"),
            post_populate=lambda _r: order.append("post"),
        )
        get()
        assert order == ["populate", "post"]

    def test_reset_seam_reconstructs(self):
        get = gated_registry_singleton(CredentialGatedRegistry, lambda _r: None)
        first = get()
        get.reset()
        assert get() is not first
