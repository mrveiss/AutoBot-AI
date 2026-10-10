# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Tests for the shared drift-script CLI plumbing (#18158)."""

from __future__ import annotations

import logging
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))

from drift_cli import MISSING_CREDENTIALS_MESSAGE, base_parser, resolve_credentials  # noqa: E402


def test_base_parser_defaults(monkeypatch):
    monkeypatch.delenv("GITHUB_REPOSITORY", raising=False)
    args = base_parser("First line\nsecond").parse_args([])
    assert args.repo == ""
    assert args.json is False


def test_base_parser_repo_defaults_from_env(monkeypatch):
    monkeypatch.setenv("GITHUB_REPOSITORY", "owner/name")
    assert base_parser("x").parse_args([]).repo == "owner/name"
    assert base_parser("x").parse_args(["--repo", "o/other"]).repo == "o/other"


def test_base_parser_json_flag_and_opt_out():
    assert base_parser("x").parse_args(["--json"]).json is True
    assert not hasattr(base_parser("x", with_json=False).parse_args([]), "json")


def test_missing_token_returns_none_and_logs(monkeypatch, caplog):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.delenv("GITHUB_TOKEN", raising=False)
    with caplog.at_level(logging.ERROR):
        assert resolve_credentials("o/r") is None
    assert MISSING_CREDENTIALS_MESSAGE in caplog.text


def test_missing_repo_returns_none(monkeypatch):
    monkeypatch.setenv("GH_TOKEN", "t")
    assert resolve_credentials("") is None


def test_github_token_fallback_and_gh_token_precedence(monkeypatch):
    monkeypatch.delenv("GH_TOKEN", raising=False)
    monkeypatch.setenv("GITHUB_TOKEN", "fallback")
    assert resolve_credentials("o/r") == "fallback"
    monkeypatch.setenv("GH_TOKEN", "primary")
    assert resolve_credentials("o/r") == "primary"
