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
    # #13535 moved redis's read into code_only.yml for the same reason #13460
    # moved ai-stack's: the database role had no delivery path at all, so this
    # fix could not reach a database host.
    "redis": ("tasks/code_only.yml", "chromadb_auth_token"),
    # #13460 moved ai-stack's read into code_only.yml, alongside the chroma unit
    # it feeds, so the builtin updater delivers both together. Rendering that
    # unit without the read would redeploy chroma with auth SILENTLY DISABLED —
    # which is precisely why this test follows the read rather than the file.
    "ai-stack": ("tasks/code_only.yml", "chromadb_auth_token"),
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
    assert "lookup('password'" in str(
        facts["chromadb_auth_token"]
    ), "the token must be generated, not defaulted to a constant"


def test_existing_installations_are_backfilled():
    """The template task is skipped when the secrets file already exists.

    Without a back-fill, every host provisioned before #12513 would keep running
    chroma unauthenticated forever — which is the reported state.
    """
    tasks = yaml.safe_load(_SLM_TASKS.read_text(encoding="utf-8"))
    backfill = next(
        (t for t in _iter_mappings(tasks) if _TOKEN_KEY in str(t.get("name", "")) and "Add" in str(t.get("name", ""))),
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


# ---------------------------------------------------------------------------
# Post-deploy round two (#12513): the token was provisioned and chroma still
# answered an unauthenticated create_collection with 200.
#
# The credential was written into the unit as `Environment=`, wrapped in
# `{% if chromadb_auth_token %}`, and the unit's only env-file input on the
# database role was `EnvironmentFile=-/opt/autobot/autobot-db-stack/.env` — a
# path nothing in this repository writes, made OPTIONAL by the leading `-`. So
# both routes for the credential were no-ops and systemd reported success:
# `systemctl cat autobot-chromadb | grep -c CHROMA_SERVER_AUTHN` → 0.
#
# The tests below pin the three properties that make that unrepresentable:
# one provisioned path, equal on both sides; a MANDATORY EnvironmentFile; and the
# file written before anything starts the unit.
# ---------------------------------------------------------------------------

_WRITE_ENV = _ANSIBLE / "_shared" / "tasks" / "write_chromadb_authn_env.yml"

#: Roles that render the chroma unit → (task file that must render the env file,
#: relative path of the unit template).
_UNIT_OWNERS = {
    "redis": ("tasks/code_only.yml", "templates/autobot-chromadb.service.j2"),  # #13535
    "ai-stack": ("tasks/code_only.yml", "templates/autobot-chromadb.service.j2"),
}

#: chromadb's own pydantic Settings field names, uppercased — that is how it
#: reads the environment (chromadb/config.py: chroma_server_authn_provider /
#: chroma_server_authn_credentials). Guessing these is the whole failure mode.
_SERVER_KEYS = ("CHROMA_SERVER_AUTHN_PROVIDER", "CHROMA_SERVER_AUTHN_CREDENTIALS")

_ENV_FILE_VAR = "chromadb_authn_env_file"


def _role_defaults(role: str) -> dict:
    return yaml.safe_load((_ANSIBLE / "roles" / role / "defaults" / "main.yml").read_text(encoding="utf-8"))


def _tasks(path: Path) -> list:
    return yaml.safe_load(path.read_text(encoding="utf-8")) or []


def _env_file_lines(unit_text: str) -> list:
    return [ln.strip() for ln in unit_text.splitlines() if ln.strip().startswith("EnvironmentFile=")]


def test_the_env_file_task_emits_the_keys_chromadb_actually_reads():
    """The keys must be chromadb's Settings field names, not plausible ones."""
    copy_task = next(
        (t for t in _iter_mappings(_tasks(_WRITE_ENV)) if (t.get("ansible.builtin.copy") or t.get("copy"))),
        None,
    )
    assert copy_task is not None, f"{_WRITE_ENV} no longer renders the env file"

    spec = copy_task.get("ansible.builtin.copy") or copy_task["copy"]
    content = str(spec.get("content", ""))
    for key in _SERVER_KEYS:
        assert f"{key}=" in content, f"the rendered env file omits {key}; chroma would enforce nothing"

    assert "chromadb.auth.token_authn.TokenAuthenticationServerProvider" in content, (
        "the server provider must be chromadb's token_authn class — the same module that "
        "ships the TokenAuthClientProvider the backend sets, so the two cannot drift"
    )
    # Empty credentials with a provider configured is a chroma boot crash, so the
    # keys stay conditional even though the FILE is unconditional.
    assert "chromadb_auth_token" in content and "{% if" in content, (
        "the authn keys must be gated on a non-empty token — a provider with empty "
        "credentials crashes chroma at startup"
    )
    assert spec.get("mode") == "0600", (
        "the credential file must not be readable beyond root; systemd reads "
        "EnvironmentFile as PID 1 before dropping privileges, so 0600 root:root suffices"
    )


def test_the_env_file_is_written_unconditionally():
    """A conditional file plus a mandatory EnvironmentFile would brick startup."""
    copy_task = next(
        (t for t in _iter_mappings(_tasks(_WRITE_ENV)) if (t.get("ansible.builtin.copy") or t.get("copy"))),
        None,
    )
    assert copy_task.get("when") is None, (
        "the env file must be rendered on every run, token or not — the units declare it "
        "as a MANDATORY EnvironmentFile, so a skipped render is a failed start"
    )


@pytest.mark.parametrize("role", sorted(_UNIT_OWNERS))
def test_unit_environmentfile_path_equals_the_provisioned_path(role):
    """The exact mismatch #13462 hit: token written where the unit does not read."""
    _, unit_rel = _UNIT_OWNERS[role]
    unit = (_ANSIBLE / "roles" / role / unit_rel).read_text(encoding="utf-8")

    declared = [ln for ln in _env_file_lines(unit) if _ENV_FILE_VAR in ln]
    assert declared == [f"EnvironmentFile={{{{ {_ENV_FILE_VAR} }}}}"], (
        f"roles/{role} unit must load the credential from {{{{ {_ENV_FILE_VAR} }}}} verbatim; "
        f"found {declared or _env_file_lines(unit)}"
    )

    spec = next(
        (
            t.get("ansible.builtin.copy") or t.get("copy")
            for t in _iter_mappings(_tasks(_WRITE_ENV))
            if (t.get("ansible.builtin.copy") or t.get("copy"))
        ),
        None,
    )
    assert spec["dest"].strip() == f"{{{{ {_ENV_FILE_VAR} }}}}", (
        "the provisioning task must write the very variable the unit reads, not a " "path that merely looks like it"
    )

    default = _role_defaults(role).get(_ENV_FILE_VAR)
    assert default, f"roles/{role}/defaults/main.yml does not define {_ENV_FILE_VAR}"
    assert default.startswith("/"), "the credential path must be absolute"


def test_both_unit_owners_resolve_to_one_credential_file():
    paths = {role: _role_defaults(role)[_ENV_FILE_VAR] for role in _UNIT_OWNERS}
    assert len(set(paths.values())) == 1, (
        f"the two chroma-owning roles point at different credential files ({paths}) — "
        "a node that changes owner would silently lose its server credential"
    )


@pytest.mark.parametrize("role", sorted(_UNIT_OWNERS))
def test_environmentfile_is_mandatory_not_optional(role):
    """`EnvironmentFile=-` is why a missing credential ran unauthenticated."""
    _, unit_rel = _UNIT_OWNERS[role]
    unit = (_ANSIBLE / "roles" / role / unit_rel).read_text(encoding="utf-8")

    for line in _env_file_lines(unit):
        assert not line.startswith("EnvironmentFile=-"), (
            f"roles/{role} declares an OPTIONAL env file ({line}) — systemd tolerates it "
            "missing, so chroma starts with no authentication and nothing reports a failure"
        )


@pytest.mark.parametrize("role", sorted(_UNIT_OWNERS))
def test_the_credential_never_lands_in_the_world_readable_unit(role):
    _, unit_rel = _UNIT_OWNERS[role]
    unit = (_ANSIBLE / "roles" / role / unit_rel).read_text(encoding="utf-8")

    inline = [ln for ln in unit.splitlines() if ln.strip().startswith("Environment=") and "CHROMA_SERVER_AUTHN" in ln]
    assert not inline, (
        f"roles/{role} inlines the chroma credential into a unit deployed 0644 — every "
        f"local user could read it: {inline}"
    )


@pytest.mark.parametrize("role", sorted(_UNIT_OWNERS))
def test_the_env_file_is_rendered_before_the_unit_is(role):
    """Mandatory EnvironmentFile + late provisioning = a bricked fresh install."""
    tasks_rel, _ = _UNIT_OWNERS[role]
    tasks = _tasks(_ANSIBLE / "roles" / role / tasks_rel)

    def index(predicate):
        return next((i for i, t in enumerate(tasks) if predicate(t)), None)

    write_at = index(lambda t: "write_chromadb_authn_env.yml" in str(t.get("ansible.builtin.include_tasks", "")))
    read_at = index(lambda t: "read_chromadb_auth_token.yml" in str(t.get("ansible.builtin.include_tasks", "")))
    unit_at = index(
        lambda t: "autobot-chromadb.service.j2"
        in str((t.get("ansible.builtin.template") or t.get("template") or {}).get("src", ""))
    )

    assert write_at is not None, f"roles/{role}/{tasks_rel} never renders the credential file"
    assert unit_at is not None, f"roles/{role}/{tasks_rel} no longer renders the chroma unit"
    assert read_at < write_at, "the token must be read before the file that carries it is written"
    assert write_at < unit_at, (
        f"roles/{role}/{tasks_rel} renders the unit before the env file it mandates — a "
        "restart between the two would fail to start chroma at all"
    )

    start_at = index(
        lambda t: "autobot-chromadb"
        in str((t.get("ansible.builtin.systemd") or t.get("systemd") or {}).get("name", ""))
    )
    if start_at is not None:
        assert write_at < start_at, "chroma is started before its mandatory env file exists"


def test_ai_stack_starts_chroma_only_after_including_the_render():
    """ai-stack keeps the render in code_only.yml; main.yml must include it first."""
    tasks = _tasks(_ANSIBLE / "roles" / "ai-stack" / "tasks" / "main.yml")
    include_at = next(
        (i for i, t in enumerate(tasks) if "code_only.yml" in str(t.get("ansible.builtin.include_tasks", ""))),
        None,
    )
    start_at = next(
        (
            i
            for i, t in enumerate(tasks)
            if "autobot-chromadb" in str((t.get("ansible.builtin.systemd") or t.get("systemd") or {}).get("name", ""))
            and str((t.get("ansible.builtin.systemd") or t.get("systemd") or {}).get("state", "")) == "started"
        ),
        None,
    )
    assert include_at is not None and start_at is not None
    assert include_at < start_at, (
        "roles/ai-stack/tasks/main.yml starts chroma before code_only.yml renders the "
        "mandatory env file — the service would fail to start on a fresh node"
    )


def test_redis_starts_chroma_only_after_including_the_render():
    """redis keeps the render in code_only.yml; main.yml must include it first.

    The start task stayed in ``tasks/chromadb.yml`` when #13535 split the render
    out, so the ordering that makes the mandatory EnvironmentFile safe is now a
    property of ``main.yml``: the include has to come before the import that
    starts the service, or a fresh database node comes up with chroma unable to
    start at all.
    """
    tasks = _tasks(_ANSIBLE / "roles" / "redis" / "tasks" / "main.yml")
    include_at = next(
        (i for i, t in enumerate(tasks) if "code_only.yml" in str(t.get("ansible.builtin.include_tasks", ""))),
        None,
    )
    chromadb_at = next(
        (i for i, t in enumerate(tasks) if "chromadb.yml" in str(t.get("ansible.builtin.import_tasks", ""))),
        None,
    )
    assert include_at is not None, "roles/redis/tasks/main.yml no longer includes code_only.yml"
    assert chromadb_at is not None, "roles/redis/tasks/main.yml no longer imports chromadb.yml"
    assert include_at < chromadb_at, (
        "roles/redis/tasks/main.yml imports chromadb.yml (which starts the service) "
        "before code_only.yml renders the mandatory env file — chroma would fail to "
        "start on a fresh database node"
    )


def test_the_client_reads_the_same_credential_through_ssot_config():
    """Server authn without a wired client is an outage, not a fix."""
    auth = (Path(__file__).resolve().parents[2] / "autobot-backend" / "utils" / "chromadb_auth.py").read_text(
        encoding="utf-8"
    )
    assert (
        "_ssot_config.misc.chromadb_auth_token" in auth
    ), "the client credential must come from ssot_config, not a second env lookup"
    assert (
        "chromadb.auth.token_authn.TokenAuthClientProvider" in auth
    ), "the client provider must be token_authn's, matching the server provider"

    ssot = (Path(__file__).resolve().parents[2] / "autobot_shared" / "ssot_config.py").read_text(encoding="utf-8")
    assert f'alias="{_TOKEN_KEY}"' in ssot, (
        f"ssot_config.misc.chromadb_auth_token must alias {_TOKEN_KEY} — the same key "
        "slm-secrets.env and backend.env carry, or the client sends nothing"
    )

    backend_env = (_ANSIBLE / "roles" / "backend" / "templates" / "backend.env.j2").read_text(encoding="utf-8")
    assert f"{_TOKEN_KEY}={{{{ backend_chromadb_auth_token }}}}" in backend_env, (
        "backend.env must carry the token or the client has nothing to send once the " "server starts enforcing"
    )
