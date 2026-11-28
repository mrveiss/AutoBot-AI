# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Behaviour parity for the Atlassian and Drive connector cores (#18557 slice 3; parent #17312).

``confluence.py``/``jira.py`` now share ``atlassian_base.py`` and ``gdrive.py``/``onedrive.py`` share
``drive_base.py``.  ``fixtures/atlassian_drive_parity_18557.json`` was RECORDED by running the
pre-refactor modules (``git show origin/main:<file>``) through ``observe_*`` below against a faked HTTP
layer; these tests replay the same scenarios on the current modules and require identical output:
request method / URL / auth / json / timeout / egress policy, response parsing, error handling,
source-id round trips, config parsing, schemas and the discover/fetch/detect flows.  No network.

One deliberate normalisation: ``json`` is omitted from a recorded request when it is ``None``
(the old Confluence ``_get`` did not pass the keyword, the shared transport passes ``json=None``,
which aiohttp treats as absent) -- the bytes on the wire are identical.
"""

import json
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import aiohttp
import pytest

from knowledge.connectors import atlassian_base, confluence, gdrive, jira, onedrive
from knowledge.connectors.base import RetryableError, instance_host_egress
from knowledge.connectors.models import ConnectorConfig

FIXTURE = Path(__file__).parent / "fixtures" / "atlassian_drive_parity_18557.json"
SINCE = datetime(2026, 1, 1, tzinfo=timezone.utc)
_CREDS = {"username": "bot@example.com", "password": "fake-token-not-real"}  # pragma: allowlist secret
CONF_BASE = "https://x.atlassian.net/wiki"
JIRA_BASE = "https://x.atlassian.net"

CONF_ROUTES = {
    ("GET", CONF_BASE + "/rest/api/space?limit=1"): (200, {"results": []}),
    ("GET", CONF_BASE + "/rest/api/content?spaceKey=S&type=page&limit=25&start=0&expand=version"): (
        200,
        {"results": [{"id": "111", "title": "Runbook", "version": {"when": "2026-01-01T00:00:00.000+00:00"}}]},
    ),
    ("GET", CONF_BASE + "/rest/api/content/111?expand=body.storage,space,version"): (
        200,
        {
            "title": "Runbook",
            "space": {"key": "S"},
            "version": {"when": "2026-02-01T00:00:00.000+00:00"},
            "_links": {"webui": "/spaces/S/pages/111"},
            "body": {"storage": {"value": "<p>Hello <b>wiki</b></p>"}},
        },
    ),
    ("GET", CONF_BASE + "/rest/api/content/111?expand=version"): (
        200,
        {"version": {"when": "2026-03-01T00:00:00.000+00:00"}},
    ),
}
JIRA_ISSUE = {
    "key": "ABC-1",
    "fields": {
        "summary": "Broken",
        "updated": "2026-02-01T00:00:00.000+00:00",
        "status": {"name": "Open"},
        "project": {"key": "ABC"},
        "description": {"type": "doc", "content": [{"type": "text", "text": "details"}]},
        "comment": {"comments": [{"author": {"displayName": "Ann"}, "body": "looks bad"}]},
    },
}
JIRA_ROUTES = {
    ("GET", JIRA_BASE + "/rest/api/3/myself"): (200, {"accountId": "a"}),
    ("POST", JIRA_BASE + "/rest/api/3/search"): (200, {"issues": [JIRA_ISSUE], "total": 1}),
    ("GET", JIRA_BASE + "/rest/api/3/issue/ABC-1"): (200, JIRA_ISSUE),
}


class _Resp:
    def __init__(self, status, body):
        self.status, self._body = status, body

    async def json(self, content_type=None):
        return self._body


class _Ctx:
    def __init__(self, resp):
        self._resp = resp

    async def __aenter__(self):
        return self._resp

    async def __aexit__(self, *exc):
        return False


class FakeHttp:
    """Records every ``tracked_request`` call and answers from a route table."""

    def __init__(self, routes, status_override=None, raises=None):
        self.routes, self.status_override, self.raises, self.calls = routes, status_override, raises, []

    def tracked_request(self, method, url, **kw):
        auth, timeout = kw.get("auth"), kw.get("timeout")
        extra = {k: v for k, v in kw.items() if k not in {"auth", "timeout", "json", "guard_egress"}}
        self.calls.append(
            {
                "method": method,
                "url": url,
                "auth": [auth.login, auth.password] if auth else None,
                "json": kw.get("json"),
                "timeout_total": timeout.total if timeout else None,
                "egress_is_instance_host": kw.get("guard_egress") == instance_host_egress(),
                "extra": extra,
            }
        )
        if self.raises:
            raise self.raises
        status, body = self.status_override or self.routes.get((method, url), (404, {}))
        return _Ctx(_Resp(status, body))


def _cfg(kind, extra):
    return ConnectorConfig(connector_id="cid", connector_type=kind, name=kind, config={**_CREDS, **extra})


def _dump(obj):
    """JSON-safe view of SourceInfo/ContentResult/ChangeInfo without wall-clock fields."""
    if isinstance(obj, list):
        return [_dump(o) for o in obj]
    if obj is None:
        return None
    data = dict(vars(obj))
    data.pop("timestamp", None)
    return json.loads(json.dumps(data, default=str, sort_keys=True))


async def _flows(conn, source_id):
    conn._store_ts, conn._load_ts = AsyncMock(), AsyncMock(return_value="2026-01-15T00:00:00.000+00:00")
    out = {"test_connection": await conn.test_connection()}
    out["discover"] = _dump(await conn.discover_sources())
    out["fetch"] = _dump(await conn.fetch_content(source_id))
    out["fetch_malformed"] = _dump(await conn.fetch_content("bad:id"))
    out["changes_none"] = _dump(await conn.detect_changes(None))
    out["changes_since"] = _dump(await conn.detect_changes(SINCE))
    out["stored_ts"] = [list(c.args) for c in conn._store_ts.call_args_list]
    return out


async def _transport(cls, http_mod, base, path, post_path=None):
    """Status handling of the shared transport: 200, 404, 429, 503 and a connection error."""
    out = {}
    for label, kw in {
        "ok": {},
        "404": {"status_override": (404, {"e": 1})},
        "429": {"status_override": (429, {})},
        "503": {"status_override": (503, {})},
        "conn": {"raises": aiohttp.ClientError("boom")},
    }.items():
        conn = cls(_cfg(cls.connector_type, {"base_url": base + "/"}))
        fake = FakeHttp({("GET", base + path): (200, {"ok": True})}, **kw)
        with patch.object(http_mod, "get_http_client", return_value=fake):
            try:
                out[label] = await conn._get(path)
            except RetryableError as exc:
                out[label] = {"retryable": str(exc), "status": exc.status_code}
        out[label + "_calls"] = fake.calls
    if post_path:
        fake = FakeHttp({("POST", base + post_path): (200, {"ok": 2})})
        conn = cls(_cfg(cls.connector_type, {"base_url": base}))
        with patch.object(http_mod, "get_http_client", return_value=fake):
            out["post"] = await conn._post(post_path, {"jql": "x"})
        out["post_calls"] = fake.calls
    return out


async def observe_atlassian(conf_cls, jira_cls, conf_mod, jira_mod, conf_http, jira_http, ids):
    """Everything the two Atlassian connectors send and parse (build/parse fns come from the modules)."""
    out = {}
    conf = conf_cls(_cfg("confluence", {"base_url": CONF_BASE + "/", "space_keys": ["S"]}))
    jc = jira_cls(_cfg("jira", {"base_url": JIRA_BASE + "/", "project_keys": ["ABC"]}))
    for name, c in (("confluence", conf), ("jira", jc)):
        out[name + "_init"] = [c._email, c._api_token, c._base_url, c.tier, c.max_concurrency, c.connector_type]
    fake = FakeHttp(CONF_ROUTES)
    with patch.object(conf_http, "get_http_client", return_value=fake):
        out["confluence_flows"] = await _flows(conf, ids["confluence"])
    out["confluence_calls"] = fake.calls
    fake = FakeHttp(JIRA_ROUTES)
    with patch.object(jira_http, "get_http_client", return_value=fake):
        out["jira_flows"] = await _flows(jc, ids["jira"])
    out["jira_calls"] = fake.calls
    out["confluence_transport"] = await _transport(conf_cls, conf_http, CONF_BASE, "/rest/api/space?limit=1")
    out["jira_transport"] = await _transport(jira_cls, jira_http, JIRA_BASE, "/rest/api/3/myself", "/rest/api/3/search")
    out["ids"] = [
        conf_mod._build_source_id("c", "9"),
        jira_mod._build_source_id("c", "A-1"),
        *[conf_mod._parse_page_id(s) for s in ("confluence:c:page:9", "confluence:c:issue:9", "a:b", "a:b:page:c:d")],
        *[jira_mod._parse_issue_key(s) for s in ("jira:c:issue:A-1", "jira:c:page:A-1", "a:b", "a:b:issue:c:d")],
    ]
    return out


GDRIVE_FILES = [
    {
        "id": "f1",
        "name": "a.pdf",
        "mimeType": "application/pdf",
        "size": "10",
        "modifiedTime": "2026-02-01T00:00:00+00:00",
    },
    {
        "id": "f2",
        "name": "b.exe",
        "mimeType": "application/x-msdownload",
        "size": "1",
        "modifiedTime": "2026-02-01T00:00:00+00:00",
    },
    {"id": "f3", "name": "c.md", "mimeType": "text/markdown", "size": "3", "modifiedTime": "2026-03-01T00:00:00+00:00"},
]
ONEDRIVE_FILES = [
    {"id": "o1", "name": "a.docx", "size": 10, "lastModifiedDateTime": "2026-02-01T00:00:00+00:00", "webUrl": "u1"},
    {"id": "o2", "name": "b.exe", "size": 1, "lastModifiedDateTime": "2026-02-01T00:00:00+00:00"},
    {"id": "o3", "name": "c.md", "size": 3, "lastModifiedDateTime": "2026-03-01T00:00:00+00:00"},
]


async def _drive_flows(conn, files):
    conn._store_ts, conn._load_ts = AsyncMock(), AsyncMock(return_value="2026-02-15T00:00:00+00:00")
    conn._list_all_files = AsyncMock(return_value=files)
    return {
        "discover": _dump(await conn.discover_sources()),
        "changes_none": _dump(await conn.detect_changes(None)),
        "changes_since": _dump(await conn.detect_changes(SINCE)),
    }


def _drive_state(c):
    names = ("_token", "_source_type", "_drive_id", "_sync_subfolders", "_max_file_size", "_supported_extensions")
    return {n: getattr(c, n) for n in names}


async def observe_drive(gd_cls, od_cls):
    """Config parsing, schemas, concurrency and the discover/change flows of both drive connectors."""
    out = {}
    for name, cls, files, extra in (
        ("gdrive", gd_cls, GDRIVE_FILES, {"folder_id": "fo", "api_base": "https://d.example/v3/"}),
        ("onedrive", od_cls, ONEDRIVE_FILES, {"site_id": "s", "folder_path": "/x"}),
    ):
        default = cls(ConnectorConfig(connector_id="cid", connector_type=name, name=name, config={}))
        custom_cfg = {"token": "t", "drive_id": "d", "sync_subfolders": False, "max_file_size_mb": 5}
        custom = cls(_cfg(name, {**custom_cfg, "supported_extensions": [".pdf", ".md", ".docx"], **extra}))
        out[name] = {
            "default": _drive_state(default),
            "custom": _drive_state(custom),
            "auth": cls.auth_schema().__name__,
            "schema": cls.output_schema(),
            "schema_key_order": list(cls.output_schema()["properties"]),
            "tier_type": [cls.tier, cls.connector_type, default.max_concurrency],
            "conc": [_conc(cls, None), _conc(cls, 9)],
            "flows": await _drive_flows(custom, files),
        }
    return out


def _conc(cls, value):
    cfg = ConnectorConfig(connector_id="c", connector_type="x", name="x", config={}, max_concurrency=value)
    return cls(cfg).max_concurrency


def _norm(obj):
    return json.loads(json.dumps(obj, default=str, sort_keys=True))


@pytest.fixture(scope="module")
def recorded():
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


@pytest.mark.asyncio
async def test_atlassian_requests_and_parsing_match_the_recorded_pre_refactor_behaviour(recorded):
    ids = {"confluence": "confluence:cid:page:111", "jira": "jira:cid:issue:ABC-1"}
    got = await observe_atlassian(
        confluence.ConfluenceConnector, jira.JiraConnector, confluence, jira, atlassian_base, atlassian_base, ids
    )
    expected = recorded["atlassian"]
    for key in expected:
        assert _norm(got[key]) == _norm(expected[key]), key


@pytest.mark.asyncio
async def test_drive_config_schema_and_flows_match_the_recorded_pre_refactor_behaviour(recorded):
    got = await observe_drive(gdrive.GoogleDriveConnector, onedrive.OneDriveConnector)
    assert _norm(got) == _norm(recorded["drive"])


def test_the_replay_is_not_vacuous(recorded):
    """Control: the recording holds real requests, a 429/503 path, a client error and non-empty discovery."""
    atl = recorded["atlassian"]
    assert atl["jira_transport"]["post_calls"][0]["method"] == "POST"
    assert atl["jira_transport"]["post_calls"][0]["json"] == {"jql": "x"}
    assert atl["confluence_transport"]["429"]["status"] == 429
    assert atl["jira_transport"]["503"]["retryable"] == "Jira server error 503"
    assert atl["confluence_transport"]["conn"]["status_code"] == 0
    assert len(atl["confluence_flows"]["discover"]) == 1 and len(atl["jira_flows"]["discover"]) == 1
    assert len(recorded["drive"]["gdrive"]["flows"]["discover"]) == 2
    assert all(c["egress_is_instance_host"] for c in atl["jira_calls"] + atl["confluence_calls"])
