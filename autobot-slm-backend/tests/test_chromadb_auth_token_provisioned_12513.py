# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""ChromaDB token auth must actually be ON, not merely implementable (#12513).

Everything the feature needs already existed before this: `CHROMA_SERVER_AUTHN_*`
in docker-compose and in both chroma systemd unit templates, `chroma_client_auth_kwargs()`
wired into every `HttpClient` construction site, an `ssot_config` field, and role
variables on `backend`, `redis` and `ai-stack`.

And every default was `""`. Nothing generated a token, so on every deployment the
provider line rendered empty, chroma enforced nothing, and any container on the
internal docker network could read and write every collection unauthenticated —
exactly what #12513 reports. A feature that is fully built and never switched on
is indistinguishable, from the outside, from one that was never built.

The property that makes it safe is that the token has **one** source. The server
credential and the client credential must be byte-identical or chroma 401s every
RAG call; two roles independently generating one would produce two values and a
total outage. So `slm_manager` generates, and `backend` / `redis` / `ai-stack`
only ever read.
"""

from __future__ import annotations

from pathlib import Path

import pytest

yaml = pytest.importorskip("yaml")

_ANSIBLE = Path(__file__).resolve().parents[1] / "ansible"
_SHARED_READ = _ANSIBLE / "_shared" / "tasks" / "read_chromadb_auth_token.yml"
_SLM_TASKS = _ANSIBLE / "roles" / "slm_manager" / "tasks" / "main.yml"
_SLM_SECRETS_TEMPLATE = _ANSIBLE / "roles" / "slm_manager" / "templates" / "slm-secrets.env.j2"

_TOKEN_KEY = "AUTOBOT_CHROMADB_AUTH_TOKEN"

#: Roles that must READ the token, and the variable each one feeds.
#: `backend` renders the client credential; the other two render the chroma unit.
_CONSUMERS = {
    "backend": ("tasks/main.yml", "backend_chromadb_auth_token"),
    "redis": ("tasks/chromadb.yml", "chromadb_auth_token"),
    "ai-stack": ("tasks/main.yml", "chromadb_auth_token"),
}


def _iter_mappings(node):
    if isinstance(node, dict):
        yield node
        for value in node.values():
            yield from _iter_mappings(value)
    elif isinstance(node, list):
        for item in node:
            yield from _iter_mappings(item)


def test_shared_read_task_exists():
    assert _SHARED_READ.is_file(), (
        f"{_SHARED_READ} missing — without one shared read, each role would have to "
        "find the token itself and they could drift onto different values"
    )


def test_secrets_template_carries_the_token():
    text = _SLM_SECRETS_TEMPLATE.read_text(encoding="utf-8")
    assert f"{_TOKEN_KEY}={{{{ chromadb_auth_token }}}}" in text, (
        "slm-secrets.env.j2 must emit the chroma token; it is the single source "
        "both the server and the client read back from"
    )


def test_slm_manager_generates_a_token_for_a_fresh_install():
    """A new deployment must come up authenticated, not opt-in."""
    tasks = yaml.safe_load(_SLM_TASKS.read_text(encoding="utf-8"))
    generate = next(
        (t for t in _iter_mappings(tasks) if "Generate security secrets" in str(t.get("name", ""))),
        None,
    )
    assert generate is not None, "the SLM secret-generation task disappeared"

    facts = generate.get("ansible.builtin.set_fact") or generate.get("set_fact") or {}
    assert "chromadb_auth_token" in facts, (
        "slm_manager must generate chromadb_auth_token alongside the other secrets — "
        "otherwise the template renders it empty and chroma runs unauthenticated"
    )
    assert "lookup('password'" in str(facts["chromadb_auth_token"]), (
        "the token must be generated, not defaulted to a constant"
    )


def test_existing_installations_are_backfilled():
    """The template task is skipped when the secrets file already exists.

    Without a back-fill, every host provisioned before #12513 would keep running
    chroma unauthenticated forever — which is the reported state.
    """
    tasks = yaml.safe_load(_SLM_TASKS.read_text(encoding="utf-8"))
    backfill = next(
        (
            t
            for t in _iter_mappings(tasks)
            if _TOKEN_KEY in str(t.get("name", "")) and "Add" in str(t.get("name", ""))
        ),
        None,
    )
    assert backfill is not None, f"no task adds {_TOKEN_KEY} to an existing secrets file"

    lineinfile = backfill.get("ansible.builtin.lineinfile") or backfill.get("lineinfile")
    assert lineinfile, "the back-fill must use lineinfile against the existing file"

    guard = " ".join(str(c) for c in (backfill.get("when") or []))
    assert "_slm_chroma_tok_check" in guard, (
        "the back-fill must be gated on the key being absent — rewriting an "
        "existing token silently rotates the credential and 401s every live client"
    )


@pytest.mark.parametrize("role,spec", sorted(_CONSUMERS.items()))
def test_consumer_roles_read_the_token_and_never_generate_one(role, spec):
    """Reading is the whole contract: a second generator means two tokens."""
    rel, var = spec
    path = _ANSIBLE / "roles" / role / rel
    text = path.read_text(encoding="utf-8")

    assert "read_chromadb_auth_token.yml" in text, (
        f"roles/{role}/{rel} must include the shared read — without it {var} keeps "
        "its empty default and this side of the pair stays unauthenticated"
    )
    assert "_chromadb_auth_token_read" in text, f"roles/{role}/{rel} never consumes the read result"

    tasks = yaml.safe_load(text)
    for task in _iter_mappings(tasks):
        facts = task.get("ansible.builtin.set_fact") or task.get("set_fact") or {}
        for name, value in facts.items():
            if "chromadb_auth_token" not in name:
                continue
            assert "lookup('password'" not in str(value), (
                f"roles/{role} generates its own chroma token — the server and client "
                "would end up on different values and every RAG call would 401"
            )


@pytest.mark.parametrize("role,spec", sorted(_CONSUMERS.items()))
def test_consumers_keep_their_existing_value_when_the_read_is_empty(role, spec):
    """A host without slm-secrets.env must fall back, not blank the credential.

    Assigning an empty read unconditionally would disable auth on one side of the
    pair while the other stayed enabled — worse than either state alone.
    """
    rel, var = spec
    tasks = yaml.safe_load((_ANSIBLE / "roles" / role / rel).read_text(encoding="utf-8"))

    adopt = [
        t
        for t in _iter_mappings(tasks)
        if var in str((t.get("ansible.builtin.set_fact") or t.get("set_fact") or {}).keys())
        and "_chromadb_auth_token_read" in str(t.get("ansible.builtin.set_fact") or t.get("set_fact"))
    ]
    assert adopt, f"roles/{role}/{rel} has no task assigning {var} from the shared read"

    for task in adopt:
        guard = task.get("when")
        guard = [guard] if isinstance(guard, str) else list(guard or [])
        assert any("length > 0" in str(c) for c in guard), (
            f"roles/{role}: {var} is assigned unconditionally — an empty read would "
            "silently turn auth off on this side"
        )
