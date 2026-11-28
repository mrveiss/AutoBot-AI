# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SSOT singleton restore plugin puts back the very instance a test replaced (#19232)."""

from __future__ import annotations

from repo_tests.ssot_config_singleton_guard import restore_singleton

import autobot_shared.ssot_config as ssot_config

# Held before any test here runs (a test that primes it would see it cleared after itself:
# the plugin restores "held nothing" just as faithfully as "held this instance").
_ORIGINAL = [ssot_config.get_config()]
_PROXY = [ssot_config.config]


def test_a_test_replaces_the_singleton():
    """Clears the cache and leaves a different instance cached."""
    ssot_config.get_config.cache_clear()
    assert ssot_config.get_config() is not _ORIGINAL[0]


def test_the_next_test_sees_the_original_instance_again():
    """The plugin's teardown re-seeded the cache with the pre-test instance, by identity."""
    assert ssot_config.get_config() is _ORIGINAL[0]
    assert ssot_config.config.llm is _ORIGINAL[0].llm


def test_a_test_reloads_the_module():
    """ssot_config_test.py does this; it rebinds config and get_config in place."""
    import importlib

    importlib.reload(ssot_config)
    assert ssot_config.config is not _PROXY[0]


def test_the_next_test_sees_the_original_proxy_again():
    assert ssot_config.config is _PROXY[0]
    assert ssot_config.get_config() is _ORIGINAL[0]


def test_restore_with_no_prior_instance_leaves_the_cache_empty():
    saved = ssot_config.get_config()
    restore_singleton(ssot_config, None)
    assert ssot_config.get_config.cache_info().currsize == 0
    restore_singleton(ssot_config, saved)
    assert ssot_config.get_config() is saved
