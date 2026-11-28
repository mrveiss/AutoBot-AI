# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The contrast half of the raw-session guard: what it must REJECT (#12979).

``raw_aiohttp_session_inventory_12979_test.py`` runs the detector against the
live tree, which is green — and a detector that has only ever been shown a
green tree has proved nothing. It could return ``()`` unconditionally and
every one of those tests would still pass.

The fixture that earns this file is ``test_prose_only_occurrences_are_not
_counted``. A text-matching guard is *satisfied by a comment carrying the same
string*, in both directions: a docstring example inflates the baseline, and —
worse — writing ``# never call aiohttp.ClientSession(`` next to a real
construction makes the file look guarded while the construction stands.
``autobot-backend/code_analysis/`` carries three such occurrences on
``origin/main`` today (a docstring example, an emitted log string and a regex
replacement template) and the sibling guard's own docstring records that
trusting ``grep -c`` there set a ceiling three too high.

A control witnesses only the shape it is written in, so there is one fixture
per *mechanism* the construction can appear through — dotted call, aliased
module, direct ``from aiohttp import ClientSession``, stored vs consumed,
pinned connector — not one per direction. Nothing here reads the repository.
"""

from __future__ import annotations

import pytest
from repo_tests._raw_aiohttp_session import client_session_sites

__all__: list[str] = []


# --- what must NOT be counted ----------------------------------------------


def test_prose_only_occurrences_are_not_counted() -> None:
    """The trap this detector exists to avoid: the string, with no call."""
    source = '''
"""Never build a bare aiohttp.ClientSession( in a request handler.

Bad::

    async with aiohttp.ClientSession() as session:
        ...
"""

# Reviewers: reject any new aiohttp.ClientSession( outside the pooled client.
TEMPLATE = "async with aiohttp.ClientSession() as session:"
HINT = f"replace aiohttp.ClientSession() with get_http_client()"
print("do not use aiohttp.ClientSession()")
'''
    assert client_session_sites(source) == ()


def test_an_attribute_access_without_a_call_is_not_a_construction() -> None:
    """A type annotation names the class; it does not build one."""
    source = (
        "import aiohttp\n"
        "\n"
        "class C:\n"
        "    def __init__(self) -> None:\n"
        "        self._s: aiohttp.ClientSession | None = None\n"
        "\n"
        "    def take(self, s: aiohttp.ClientSession) -> aiohttp.ClientSession:\n"
        "        return s\n"
    )
    assert client_session_sites(source) == ()


def test_closing_or_using_an_existing_session_is_not_a_construction() -> None:
    source = (
        "async def f(session):\n"
        "    async with session.get('https://example.invalid') as r:\n"
        "        await r.json()\n"
        "    await session.close()\n"
    )
    assert client_session_sites(source) == ()


# --- what MUST be counted, one fixture per mechanism ------------------------


def test_the_dotted_per_request_shape_is_counted_and_marked_unbound() -> None:
    source = "import aiohttp\n\nasync def f():\n    async with aiohttp.ClientSession() as s:\n        return s\n"
    (site,) = client_session_sites(source)
    assert site.lineno == 4
    assert site.bound is False, "an inline `async with` operand is the per-request shape"
    assert site.keywords == ()


def test_an_aliased_module_is_counted() -> None:
    """``import aiohttp as http`` — a matcher keyed on the name ``aiohttp`` misses this."""
    source = "import aiohttp as http\n\nasync def f():\n    async with http.ClientSession() as s:\n        return s\n"
    assert len(client_session_sites(source)) == 1


def test_a_direct_import_of_the_symbol_is_counted() -> None:
    """``from aiohttp import ClientSession`` — there is no attribute access to match."""
    source = (
        "from aiohttp import ClientSession\n\nasync def f():\n    async with ClientSession() as s:\n        return s\n"
    )
    assert len(client_session_sites(source)) == 1


def test_a_renamed_direct_import_is_counted() -> None:
    """``from aiohttp import ClientSession as Session`` — the bare-name arm's blind spot.

    Recorded as a KNOWN GAP rather than asserted green. The detector matches
    on the spelling at the call site, so an aliased symbol is invisible to it.
    No occurrence of this spelling exists in the tree (``git grep "ClientSession
    as "`` over tracked ``*.py`` is empty), so the gap costs nothing today —
    but a guard's blind spots and its exemptions are the same surface, and
    only one of them is normally written down. This is the other one.
    """
    source = (
        "from aiohttp import ClientSession as Session\n\nasync def f():\n    async with Session() as s:\n"
        "        return s\n"
    )
    assert client_session_sites(source) == (), "the known gap closed — tighten this fixture into an assertion"


def test_a_stored_session_is_counted_and_marked_bound() -> None:
    """The long-lived shape: the session outlives the statement that made it."""
    source = (
        "import aiohttp\n"
        "\n"
        "class C:\n"
        "    async def open(self) -> None:\n"
        "        self._session = aiohttp.ClientSession(timeout=None)\n"
    )
    (site,) = client_session_sites(source)
    assert site.bound is True
    assert site.keywords == ("timeout",)


def test_a_pinned_connector_is_visible_in_the_keywords() -> None:
    """``connector=`` is the signal that pooling would drop an SSRF pin (#12278)."""
    source = (
        "import aiohttp\n"
        "\n"
        "async def f(connector):\n"
        "    async with aiohttp.ClientSession(connector=connector, timeout=None) as s:\n"
        "        return s\n"
    )
    (site,) = client_session_sites(source)
    assert "connector" in site.keywords


def test_several_sites_in_one_file_are_all_reported_in_line_order() -> None:
    source = (
        "import aiohttp\n"
        "\n"
        "async def a():\n"
        "    async with aiohttp.ClientSession() as s:\n"
        "        return s\n"
        "\n"
        "async def b():\n"
        "    async with aiohttp.ClientSession() as s:\n"
        "        return s\n"
    )
    sites = client_session_sites(source)
    assert [site.lineno for site in sites] == [4, 8]


def test_unparsable_source_raises_rather_than_reporting_clean() -> None:
    """An empty result from a parser that choked is not a measurement."""
    with pytest.raises(SyntaxError):
        client_session_sites("def f(:\n    pass\n")
