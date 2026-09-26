# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#17551 — the Redis config may never be wildcard-bound, unprotected AND unauthenticated.

No single directive in `roles/redis/templates/redis-stack.conf.j2` is wrong.
`bind 0.0.0.0` is ordinary, `protected-mode no` is the documented way to permit
it, and the `requirepass` block omits itself rather than emitting a blank
directive when there is no password. **Only the conjunction is the defect**, so
a guard that reads the three separately cannot see it — which is why three
reviewer notes covered the restart and the missing password independently and
none of them caught this.

It was inert while nothing read the file: the packaged unit started the daemon
with a path the role never renders to. #17434 points the daemon at the rendered
config, so the restart that finally applies it is the restart that would first
have exposed the store. That is why this guard ships in #17434's own change.

`redis_password` resolves to `vault_redis_password | default('')` and nothing in
this repository assigns `vault_redis_password`; the SLM-generated secret is
adopted into `redis_client_password` (the CLIENT credential) and is read after
this template renders in any case. That split is #16627's subject, not this
file's — here the only question is whether the rendered file can ever be open.
"""

from __future__ import annotations

import pathlib
import re

import pytest

jinja2 = pytest.importorskip("jinja2")
pytest.importorskip("jinja2.meta")
import jinja2.meta  # noqa: E402

_TEMPLATE = pathlib.Path("autobot-slm-backend/ansible/roles/redis/templates/redis-stack.conf.j2")


class _Stat:
    """Stands in for a registered `stat` result; TLS stays off in these cases."""

    stat = type("_S", (), {"exists": False})()


#: The values the role supplies that this guard does not vary. Deliberately
#: complete: `_render` asserts it covers every variable the template declares,
#: so a new variable fails this test rather than quietly taking a default and
#: changing what is being measured.
_BASE: dict[str, object] = {
    "redis_port": 6379,
    "redis_memory_limit": "6gb",
    "redis_maxclients": 10000,
    "redis_timeout": 300,
    "redis_tcp_keepalive": 60,
    "redis_persistence": True,
    "redis_tls_enabled": False,
    "redis_tls_disable_plain_port": False,
    "redis_tls_cert_dir": "/etc/autobot/certs",
    "redis_tls_port": 6380,
    "redis_tls_auth_clients": "optional",
    "tls_server_cert": _Stat(),
    "tls_server_key": _Stat(),
    "tls_ca_cert": _Stat(),
}


def repo_root() -> pathlib.Path:
    """Repo root derived from this file, never from the caller's cwd."""
    return pathlib.Path(__file__).resolve().parents[1]


def render(**overrides: object) -> str:
    """Render the role's config template with Ansible's `bool` filter supplied."""
    env = jinja2.Environment(  # noqa: S701 - a config file, not HTML
        undefined=jinja2.StrictUndefined,
        keep_trailing_newline=True,
    )
    env.filters["bool"] = lambda v: str(v).strip().lower() in {"1", "true", "yes", "on"}
    text = (repo_root() / _TEMPLATE).read_text(encoding="utf-8")

    declared = jinja2.meta.find_undeclared_variables(env.parse(text))
    context = {**_BASE, **overrides}
    missing = sorted(declared - set(context))
    assert not missing, (
        f"the template declares variables this guard does not supply: {missing}. "
        "Add them to _BASE deliberately -- a variable left to default silently "
        "changes what this test measures."
    )
    return env.from_string(text).render(**context)


def _directive(rendered: str, name: str) -> str | None:
    """The value of a top-level directive, or None when it is not emitted."""
    match = re.search(rf"^{re.escape(name)}\s+(\S+)", rendered, re.MULTILINE)
    return match.group(1) if match else None


def is_open_to_the_network(rendered: str) -> bool:
    """The conjunction, asserted as one fact rather than three.

    Open means: reachable off-box (a wildcard bind with protected-mode off) AND
    accepting anyone (no requirepass). Any one of the three turned the other way
    closes it, which is why none of them can be checked alone.
    """
    wildcard = _directive(rendered, "bind") == "0.0.0.0"
    unprotected = _directive(rendered, "protected-mode") == "no"
    unauthenticated = _directive(rendered, "requirepass") is None
    return wildcard and unprotected and unauthenticated


class TestTheRenderedConfigIsNeverOpen:
    """The load-bearing assertion, across every password state the role produces."""

    @pytest.mark.parametrize(
        "password",
        ["", None, "   ", 0, False],
        ids=["empty", "undefined-default", "whitespace", "zero", "false"],
    )
    def test_no_password_never_yields_an_open_store(self, password: object) -> None:
        rendered = render(redis_password=password)
        assert not is_open_to_the_network(rendered), (
            "rendered an unauthenticated store on every interface " f"with redis_password={password!r} (#17551)"
        )
        assert _directive(rendered, "protected-mode") == "yes", (
            "with no password the store must keep protected-mode ON -- that is the "
            "directive's purpose, and it is what makes the wildcard bind safe"
        )

    def test_a_password_permits_the_open_bind_it_is_there_to_protect(self) -> None:
        """Contrast pair: the guard must not simply pin protected-mode to yes."""
        rendered = render(redis_password="a-real-secret")
        assert _directive(rendered, "protected-mode") == "no"
        assert _directive(rendered, "requirepass") == "a-real-secret"
        assert not is_open_to_the_network(rendered), "authenticated, so not open"

    def test_the_detector_can_actually_see_an_open_config(self) -> None:
        """A negative control: without it, `not is_open(...)` proves nothing."""
        contrived = "bind 0.0.0.0\nprotected-mode no\nport 6379\n"
        assert is_open_to_the_network(contrived), "the detector cannot detect the defect"

    def test_the_password_reaches_this_template_through_an_unset_indirection(self) -> None:
        """Why this guard is not hypothetical, checked without a tree sweep.

        `redis_password` is not a value, it is an indirection to a vault key.
        Asserting "nothing assigns that key anywhere" would need a glob over the
        ansible tree, and `repo_tests/_glob_declared_uncovered.py` says in as
        many words not to add an entry there to make a new uncovered dependency
        pass. The premise is recorded in #17551 with its evidence instead; what
        is checked here is the part this file actually depends on -- that the
        indirection is still an indirection, so an empty resolution is reachable.
        """
        declaration = (repo_root() / "autobot-slm-backend/ansible/roles/redis/vars/main.yml").read_text(
            encoding="utf-8"
        )
        assert re.search(r"^redis_password:.*vault_redis_password", declaration, re.MULTILINE), (
            "redis_password no longer resolves through vault_redis_password -- re-read "
            "#16627 and #17551 and decide whether this guard still describes reality"
        )
        assert "default('')" in declaration or 'default("")' in declaration, (
            "the empty-string fallback is gone; if the vault key is now required, " "this guard's premise changed"
        )
