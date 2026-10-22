# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Slice 3 (connectors) of #18557: the Atlassian and Drive connector pairs share ONE core (parent #17312).

``confluence.py``/``jira.py`` delegate to ``knowledge/connectors/atlassian_base.py`` and
``gdrive.py``/``onedrive.py`` to ``knowledge/connectors/drive_base.py``.  A detector reads each caller's
syntax tree and reports a definition the core already provides -- the signature of the old copy coming
back.  Every detector has a contrast test: an inline old-copy string that MUST be detected and a
delegating caller that must NOT be.

Kept per provider on purpose (recorded on #18557): ``fetch_content`` of the drive pair (~0.6 similar,
provider-specific export/extraction), ``_classify_change`` of the Atlassian pair (Confluence re-reads the
page version over HTTP, Jira reads it from the search hit) and the drive HTTP helpers.
"""

from __future__ import annotations

import ast

from repo_tests._paths import repo_root

ROOT = repo_root()
CONNECTORS = "autobot-backend/knowledge/connectors/"
ATLASSIAN_CORE = {"_request", "_get"}
ATLASSIAN_CALLERS = {CONNECTORS + "confluence.py": "ConfluenceConnector", CONNECTORS + "jira.py": "JiraConnector"}
DRIVE_CORE = {"discover_sources", "auth_schema", "output_schema", "max_concurrency"}
DRIVE_CALLERS = {CONNECTORS + "gdrive.py": "GoogleDriveConnector", CONNECTORS + "onedrive.py": "OneDriveConnector"}


def _read(rel: str) -> str:
    return (ROOT / rel).read_text(encoding="utf-8")


def defined_functions(source: str) -> set[str]:
    """Names of every function/method defined anywhere in *source*."""
    return {n.name for n in ast.walk(ast.parse(source)) if isinstance(n, (ast.FunctionDef, ast.AsyncFunctionDef))}


def called_attributes(source: str) -> set[str]:
    """Names of every ``x.name(...)`` method called in *source*."""
    return {
        n.func.attr
        for n in ast.walk(ast.parse(source))
        if isinstance(n, ast.Call) and isinstance(n.func, ast.Attribute)
    }


def assigned_self_attributes(source: str) -> set[str]:
    """Names of every ``self.name = ...`` target in *source*."""
    return {
        t.attr
        for n in ast.walk(ast.parse(source))
        if isinstance(n, (ast.Assign, ast.AnnAssign))
        for t in (n.targets if isinstance(n, ast.Assign) else [n.target])
        if isinstance(t, ast.Attribute) and isinstance(t.value, ast.Name) and t.value.id == "self"
    }


def base_names(source: str, cls: str) -> set[str]:
    """Simple names of the bases of class *cls* in *source*."""
    for n in ast.walk(ast.parse(source)):
        if isinstance(n, ast.ClassDef) and n.name == cls:
            return {b.id for b in n.bases if isinstance(b, ast.Name)}
    return set()


def old_atlassian_copy(source: str) -> set[str]:
    """What an inline copy of the Atlassian core looks like: its transport, credential parsing, id split."""
    found = defined_functions(source) & ATLASSIAN_CORE
    if "tracked_request" in called_attributes(source):
        found.add("tracked_request")
    if {"_email", "_api_token"} & assigned_self_attributes(source):
        found.add("credential_parsing")
    if "split" in called_attributes(source):
        found.add("source_id_split")
    return found


OLD_ATLASSIAN_COPY = """
class JiraConnector(AbstractConnector):
    def __init__(self, config):
        self._email = config.config.get("username", "")
        self._api_token = config.config.get("password", "")

    async def _request(self, method, path):
        async with get_http_client().tracked_request(method, path) as resp:
            return resp

def _parse_issue_key(source_id):
    return source_id.split(":")[3]
"""
DELEGATING_ATLASSIAN = """
class JiraConnector(AtlassianConnector):
    vendor_name = "Jira"
    async def _post(self, path, json_data):
        return await self._request("POST", path, json_data=json_data)

def _parse_issue_key(source_id):
    return parse_atlassian_source_id("issue", source_id)
"""


def test_atlassian_detector_flags_an_old_copy_and_passes_a_delegate():
    assert old_atlassian_copy(OLD_ATLASSIAN_COPY) == {
        "_request",
        "tracked_request",
        "credential_parsing",
        "source_id_split",
    }
    assert not old_atlassian_copy(DELEGATING_ATLASSIAN)


def test_atlassian_callers_hold_none_of_the_shared_core():
    for rel, cls in ATLASSIAN_CALLERS.items():
        source = _read(rel)
        assert not old_atlassian_copy(source), rel
        assert base_names(source, cls) == {"AtlassianConnector"}, rel


def test_atlassian_base_owns_the_core():
    source = _read(CONNECTORS + "atlassian_base.py")
    assert ATLASSIAN_CORE <= defined_functions(source)
    assert "tracked_request" in called_attributes(source)
    assert {"build_atlassian_source_id", "parse_atlassian_source_id"} <= defined_functions(source)


def old_drive_copy(source: str) -> set[str]:
    """Drive-core definitions present in a caller (each one is the old inline copy returning)."""
    return defined_functions(source) & DRIVE_CORE


OLD_DRIVE_COPY = """
class OneDriveConnector(AbstractConnector):
    @classmethod
    def auth_schema(cls):
        return BearerAuth

    async def discover_sources(self):
        return [self._file_to_source_info(f) for f in await self._list_all_files()]
"""
DELEGATING_DRIVE = """
class OneDriveConnector(DriveConnector):
    drive_label = "OneDrive"
    async def detect_changes(self, since=None):
        return await self._detect_changes_via_file_listing(since)
"""


def test_drive_detector_flags_an_old_copy_and_passes_a_delegate():
    assert old_drive_copy(OLD_DRIVE_COPY) == {"auth_schema", "discover_sources"}
    assert not old_drive_copy(DELEGATING_DRIVE)


def test_drive_callers_hold_none_of_the_shared_core():
    for rel, cls in DRIVE_CALLERS.items():
        source = _read(rel)
        assert not old_drive_copy(source), rel
        assert base_names(source, cls) == {"DriveConnector"}, rel
        assert {"_token", "_max_file_size", "_supported_extensions"}.isdisjoint(assigned_self_attributes(source)), rel


def test_drive_base_owns_the_core_and_extends_the_existing_abstract_base():
    source = _read(CONNECTORS + "drive_base.py")
    assert DRIVE_CORE <= defined_functions(source)
    assert base_names(source, "DriveConnector") == {"AbstractConnector"}
    assert base_names(_read(CONNECTORS + "atlassian_base.py"), "AtlassianConnector") == {"AbstractConnector"}
