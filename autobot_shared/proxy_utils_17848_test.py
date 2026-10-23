# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""``get_client_ip`` reads an appended X-Forwarded-For chain from the right (#17848).

nginx appends the peer it saw (``$proxy_add_x_forwarded_for``), so the LEFTMOST
entry is whatever the client sent. The old helper returned it once the proxy was
trusted, handing every client behind the proxy its own rate-limit key.
"""

from types import SimpleNamespace

import pytest

from autobot_shared.proxy_utils import client_from_forwarded_chain, get_client_ip

_NGINX = "10.0.0.5"
_EDGE = "10.0.0.9"
_CLIENT = "198.51.100.7"
_SPOOF = "203.0.113.9"


def _request(peer: str, forwarded: str | None = None) -> SimpleNamespace:
    headers = {"x-forwarded-for": forwarded} if forwarded is not None else {}
    return SimpleNamespace(client=SimpleNamespace(host=peer), headers=headers)


def test_a_spoofed_leftmost_entry_through_the_trusted_proxy_is_not_selected() -> None:
    request = _request(_NGINX, f"{_SPOOF}, {_CLIENT}")
    assert get_client_ip(request, trusted_proxies=[_NGINX]) == _CLIENT


def test_contrast_the_leftmost_rule_returned_the_spoof() -> None:
    """The pre-fix selection, on the same chain, is the attacker's value."""
    assert f"{_SPOOF}, {_CLIENT}".split(",")[0].strip() == _SPOOF


def test_the_real_nginx_case_gives_the_client() -> None:
    assert get_client_ip(_request(_NGINX, _CLIENT), trusted_proxies=[_NGINX]) == _CLIENT


@pytest.mark.parametrize("forwarded", [_SPOOF, f"{_SPOOF}, {_CLIENT}", "garbage"])
def test_an_untrusted_peer_cannot_change_the_key(forwarded: str) -> None:
    assert get_client_ip(_request(_CLIENT, forwarded), trusted_proxies=[_NGINX]) == _CLIENT


def test_multi_hop_edge_and_inner_proxy_are_both_skipped() -> None:
    chain = f"{_SPOOF}, {_CLIENT}, {_EDGE}"
    assert get_client_ip(_request(_NGINX, chain), trusted_proxies=[_NGINX, _EDGE]) == _CLIENT


def test_a_spoofed_trusted_address_on_the_left_is_still_skipped_past() -> None:
    chain = f"{_EDGE}, {_CLIENT}"
    assert get_client_ip(_request(_NGINX, chain), trusted_proxies=[_NGINX, _EDGE]) == _CLIENT


def test_a_cidr_trusted_range() -> None:
    assert get_client_ip(_request(_NGINX, f"{_SPOOF}, {_CLIENT}"), trusted_proxies=["10.0.0.0/24"]) == _CLIENT


def test_no_header_or_empty_chain_gives_the_peer() -> None:
    assert get_client_ip(_request(_NGINX), trusted_proxies=[_NGINX]) == _NGINX
    assert get_client_ip(_request(_NGINX, " , "), trusted_proxies=[_NGINX]) == _NGINX


def test_an_all_trusted_chain_gives_its_origin() -> None:
    assert client_from_forwarded_chain(f"{_EDGE}, {_NGINX}", ()) == _NGINX


def test_the_divergent_readers_now_use_the_shared_rule(monkeypatch) -> None:
    """#17848 AC5: a2a, openai_compat (and anthropic_compat through it), chat_embed."""
    import importlib

    a2a = importlib.import_module("api.a2a")
    oai = importlib.import_module("api.openai_compat")
    embed = importlib.import_module("api.chat_embed")
    spoofed_direct = _request(_CLIENT, _SPOOF)
    assert a2a._remote_addr(spoofed_direct) == _CLIENT
    assert oai._remote_addr(spoofed_direct) == _CLIENT
    monkeypatch.setattr(embed, "_TRUSTED_PROXIES", frozenset({_NGINX}))
    assert embed._get_client_ip(_request(_NGINX, f"{_SPOOF}, {_CLIENT}")) == _CLIENT
