# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The /browser/mcp/status contract, and the refusal text (#15228).

Two client-model-disagrees-with-route defects, same family as #15116 and
#15118:

* the SLM frontend read a top-level ``status`` this route does not send, and
  compared it against ``connected`` / ``ready``, which this route never emits.
  Either half alone pinned the indicator red. The producing side is here; the
  consuming side is ``autobot-slm-frontend/src/utils/browserVmStatus.ts``, and
  the cross-language test below fails if one moves without the other;
* every refusal from ``POST /mcp/navigate`` said ``URL not in whitelist`` — a
  mechanism #13236 step 5 deleted — for three unrelated causes.
"""

import json
import pathlib
import re
from unittest.mock import AsyncMock, patch

import pytest
from fastapi import HTTPException

from api import browser_mcp
from services.browser_url_guard import UrlDecision
from services.fleet_registry import SOURCE_FALLBACK, SOURCE_REGISTRY, FleetSnapshot

_REPO_ROOT = pathlib.Path(__file__).resolve().parents[4]
_TS_CONTRACT = _REPO_ROOT / "autobot-slm-frontend/src/utils/browserVmStatus.ts"
_BROWSER_TOOL = _REPO_ROOT / "autobot-slm-frontend/src/views/tools/admin/BrowserTool.vue"
_EN_LOCALE = _REPO_ROOT / "autobot-slm-frontend/src/locales/en.json"


def _snapshot(hosts=(), source=SOURCE_REGISTRY, reason=None):
    return FleetSnapshot(frozenset(hosts), source, len(hosts), reason)


def _fleet(**kwargs):
    return patch("api.browser_mcp.fleet_snapshot", AsyncMock(return_value=_snapshot(**kwargs)))


# ------------------------------------------------------- the status payload


@pytest.mark.asyncio
async def test_status_reports_the_vm_state_under_browser_vm():
    """The field's name and nesting are the contract, not an implementation detail."""
    with patch("api.browser_mcp.get_http_client", side_effect=RuntimeError("VM down")):
        with _fleet(hosts=("10.77.4.21",)):
            payload = await browser_mcp.get_browser_mcp_status()

    assert "status" not in payload, "a top-level status is what the client wrongly read"
    assert payload["browser_vm"]["status"] in browser_mcp.BROWSER_VM_STATUS_VALUES


@pytest.mark.asyncio
async def test_status_names_where_fleet_membership_came_from():
    """A degraded exception set must never be served as the live fleet."""
    with patch("api.browser_mcp.get_http_client", side_effect=RuntimeError("VM down")):
        with _fleet(hosts=("10.1.1.1",), source=SOURCE_FALLBACK, reason="registry unreadable"):
            payload = await browser_mcp.get_browser_mcp_status()

    assert payload["security"]["fleet_membership_source"] == SOURCE_FALLBACK
    assert payload["security"]["fleet_nodes"] == 1
    # loopback set (3) + the one fleet host
    assert payload["security"]["internal_host_exceptions"] == 4


@pytest.mark.asyncio
async def test_status_counts_the_registry_not_a_fixed_seven():
    """The count moves with the registry, which a seven-name tuple cannot do."""
    with patch("api.browser_mcp.get_http_client", side_effect=RuntimeError("VM down")):
        with _fleet(hosts=tuple(f"10.77.4.{n}" for n in range(1, 12))):
            payload = await browser_mcp.get_browser_mcp_status()

    assert payload["security"]["fleet_nodes"] == 11
    assert payload["security"]["fleet_membership_source"] == SOURCE_REGISTRY


# ------------------------------------------------------- the refusal message


@pytest.mark.asyncio
async def test_navigate_answers_with_the_classified_reason():
    """The 403 body is the classifier's sentence, not a fixed string."""
    message = "Refused: 'ftp' is not a browsable scheme."
    request = browser_mcp.BrowserNavigateRequest(url="ftp://example.org/x")

    with patch("api.browser_mcp.check_rate_limit", AsyncMock(return_value=True)):
        with patch(
            "api.browser_mcp.classify_url",
            AsyncMock(return_value=UrlDecision(False, "unsupported_scheme", message)),
        ):
            with pytest.raises(HTTPException) as excinfo:
                await browser_mcp.navigate_mcp(request)

    assert excinfo.value.status_code == 403
    assert excinfo.value.detail == message


def test_no_refusal_or_docstring_advertises_a_whitelist():
    """#15228 AC: the module docstring stops advertising whitelist enforcement.

    The source may still *mention* the word where it explains the removal —
    what may not survive is a docstring claiming the mechanism, or a message
    handed to an operator naming it. So this checks the docstring and every
    ``detail=`` on this module rather than grepping the file blindly.
    """
    assert "whitelist" not in (browser_mcp.__doc__ or "").lower()

    source = pathlib.Path(browser_mcp.__file__).read_text(encoding="utf-8")
    for detail in re.findall(r"detail=(?:f?\"[^\"]*\")", source):
        assert "whitelist" not in detail.lower(), detail


# ------------------------------------------------- the cross-language contract


def _ts_status_map() -> dict:
    """The vocabulary the SLM frontend maps, parsed from its one contract file."""
    text = _TS_CONTRACT.read_text(encoding="utf-8")
    body = text.split("BROWSER_VM_STATUS_MAP = {", 1)[1].split("} as const", 1)[0]
    return dict(re.findall(r"(\w+):\s*'([^']+)'", body))


def test_the_frontend_maps_exactly_the_values_this_route_emits():
    """Fails if either side's vocabulary changes alone.

    ``connected`` and ``ready`` — the two values the old client tested for —
    are absent from this route's vocabulary, which is precisely why the
    indicator could never go green.
    """
    assert set(_ts_status_map()) == set(browser_mcp.BROWSER_VM_STATUS_VALUES)
    assert "connected" not in browser_mcp.BROWSER_VM_STATUS_VALUES
    assert "ready" not in browser_mcp.BROWSER_VM_STATUS_VALUES


def test_the_frontend_reads_the_field_this_route_nests_the_status_under():
    text = _TS_CONTRACT.read_text(encoding="utf-8")
    assert "BROWSER_VM_FIELD = 'browser_vm'" in text


def test_the_browser_tool_reads_the_contract_helper_not_the_raw_body():
    """A second reader of this payload is how the two sides drifted apart."""
    vue = _BROWSER_TOOL.read_text(encoding="utf-8")
    assert "readBrowserVmStatus" in vue
    # Comments are stripped first: this file explains the defect it fixed, and
    # naming it there must not read as committing it.
    code = "\n".join(line for line in vue.splitlines() if not line.strip().startswith("//"))
    assert "data.status" not in code, "reading the top-level field is the #15228 defect"


def test_every_status_the_frontend_can_show_has_a_translation():
    """No hardcoded UI strings: the raw status word used to be rendered as-is."""
    locale = json.loads(_EN_LOCALE.read_text(encoding="utf-8"))
    labels = locale["tools"]["admin"]["browserTool"]["status"]
    expected = set(_ts_status_map().values()) | {"unknown", "connecting"}
    assert set(labels) == expected
