# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""No compose port is published on every interface by accident, and no credential has a default (#17500, #17793).

Redis was published as ``${AUTOBOT_REDIS_PORT:-6379}:6379``, on every interface, with no
password, while Postgres and ChromaDB sat on 127.0.0.1. One copied line brings that back, so
every published port in every compose file is checked: it binds loopback, or it is a web entry
point listed in ``_ALL_INTERFACES`` with the reason it must face the network.

Credentials fell back to guessable values (``:-autobot``, ``:-admin``) when unset, so a stack
started without docker/generate-secrets.sh ran on passwords anyone could guess. Every
credential is now ``${VAR:?...}``: compose refuses to start and names the variable. Every such
variable is one docker/generate-secrets.sh writes, so the documented first run satisfies them.
"""

from __future__ import annotations

import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._compose_files import COMPOSE_FILES, load_yaml_mapping
from repo_tests._paths import repo_root

from tools.lint._comment_syntax import code_lines

_ROOT = repo_root()
_GENERATOR = _ROOT / "docker" / "generate-secrets.sh"

#: (compose file, service, container port): why it must listen on every interface.
_ALL_INTERFACES = {
    ("docker-compose.yml", "autobot-frontend", "80"): "the web UI entry point; nginx serves users on the LAN",
    ("docker-compose.yml", "autobot-frontend", "443"): "the web UI entry point over TLS",
    ("docker-compose.yml", "autobot-slm-gui", "80"): "the SLM-only profile's web entry point",
    ("docker-compose.yml", "autobot-slm-gui", "443"): "the SLM-only profile's web entry point over TLS",
}
_LOOPBACK = {"127.0.0.1", "::1", "[::1]", "localhost"}
#: A bind address variable that defaults to loopback: closed unless an operator opens it on purpose.
_LOOPBACK_DEFAULT = re.compile(r"\$\{[A-Z0-9_]+:-127\.0\.0\.1\}")
#: Credentials passed through EMPTY when unset (``${VAR:-}``): never a guessable value, and each
#: is generated, optional or fails closed where it is used. A new one needs a reason here.
_EMPTY_WHEN_UNSET = {
    "AUTOBOT_JWT_SECRET": "autobot-secrets-init generates it on first up (GH#9905); with-secrets.sh loads it",  # pragma: allowlist secret
    "SECRET_KEY": "autobot-secrets-init generates it on first up (GH#9905); with-secrets.sh loads it",  # pragma: allowlist secret
    "SLM_SECRET_KEY": "the SLM generates and persists it when unset (autobot-slm-backend/config.py)",  # pragma: allowlist secret
    "AUTOBOT_ENCRYPTION_KEY": "empty, EncryptionService raises where encryption is used -- it fails closed",  # pragma: allowlist secret
    "AUTOBOT_CHROMADB_AUTH_TOKEN": "optional ChromaDB token auth (#12513); ChromaDB binds loopback only",  # pragma: allowlist secret
    "ANTHROPIC_API_KEY": "an optional third-party provider key",  # pragma: allowlist secret
    "GH_TOKEN": "an optional third-party token",  # pragma: allowlist secret
}
_CREDENTIAL = re.compile(r"PASSWORD|SECRET|TOKEN|_KEY\b|PASSPHRASE", re.I)


#: Named so a discovery that silently lost one fails here, not only below the floor.
_KNOWN_COMPOSE_FILES = {
    "docker-compose.yml",
    "docker-compose.hardened.yml",
    "docker-compose.override.example.yml",
    "docker/mcp-bridges.yml",
    "autobot-infrastructure/shared/config/logging/loki/docker-compose-loki.yml",
    "autobot-infrastructure/shared/docker/compose/docker-compose.playwright-vnc.yml",
    "autobot-infrastructure/shared/docker/compose/docker-compose.playwright.yml",
    "autobot-infrastructure/shared/docker/compose/docker-compose.secure-sandbox.yml",
}


def _compose_files() -> list[Path]:
    """Every tracked compose file at any depth, through the shared declaration (27's review)."""
    files = [_ROOT / rel for rel in COMPOSE_FILES.examined(_ROOT)]
    missing = _KNOWN_COMPOSE_FILES - {str(f.relative_to(_ROOT)) for f in files}
    assert not missing, f"compose files the enumeration no longer reaches: {sorted(missing)}"
    return files


def _host_ip_and_target(entry) -> tuple[str | None, str]:
    """The host address a port entry binds (None = every interface) and its container port."""
    if isinstance(entry, dict):  # long syntax
        return entry.get("host_ip"), str(entry.get("target"))
    text = str(entry).split("/")[0]
    # Split on ':' outside ${...} so "127.0.0.1:${PORT:-6379}:6379" parses as three parts.
    parts, depth, cur = [], 0, ""
    for ch in text:
        depth += ch == "{"
        depth -= ch == "}"
        if ch == ":" and depth == 0:
            parts.append(cur)
            cur = ""
        else:
            cur += ch
    parts.append(cur)
    return (parts[0] if len(parts) == 3 else None), parts[-1]


def exposed_ports(compose: dict, name: str) -> list[tuple[str, str, str]]:
    """(file, service, container port) for each port published beyond loopback."""
    found = []
    for service, spec in (compose.get("services") or {}).items():
        for entry in (spec or {}).get("ports") or []:
            host_ip, target = _host_ip_and_target(entry)
            if host_ip not in _LOOPBACK and not _LOOPBACK_DEFAULT.fullmatch(host_ip or ""):
                found.append((name, service, target))
    return found


def credential_defaults(text: str) -> list[str]:
    """Every ${VAR:-x} / ${VAR-x} with a NON-empty x whose VAR names a credential."""
    return [m.group(0) for m in re.finditer(r"\$\{([A-Z0-9_]+):?-([^}]+)\}", text) if _CREDENTIAL.search(m.group(1))]


def credential_literals(compose: dict) -> list[str]:
    """service/KEY for each credential set to a literal value in a service's environment."""
    found = []
    for service, spec in (compose.get("services") or {}).items():
        env = (spec or {}).get("environment") or {}
        pairs = env.items() if isinstance(env, dict) else (str(e).split("=", 1) for e in env if "=" in str(e))
        for key, value in pairs:
            value = "" if value is None else str(value)
            if key.endswith("_FILE"):  # a path to a secret file (compose secrets), not a secret
                continue
            if _CREDENTIAL.search(key) and value.strip() and not value.strip().startswith("${"):
                found.append(f"{service}/{key}")
    return found


def empty_passthroughs(text: str) -> set[str]:
    """Credentials written ${VAR:-} / ${VAR-}: passed through empty when unset."""
    return {m.group(1) for m in re.finditer(r"\$\{([A-Z0-9_]+):?-\}", text) if _CREDENTIAL.search(m.group(1))}


def required_credentials(text: str) -> set[str]:
    return {m.group(1) for m in re.finditer(r"\$\{([A-Z0-9_]+):\?[^}]*\}", text) if _CREDENTIAL.search(m.group(1))}


def test_no_port_is_published_on_every_interface_without_a_reason() -> None:
    exposed = [
        hit
        for f in _compose_files()
        for hit in exposed_ports(yaml.safe_load(f.read_text(encoding="utf-8")) or {}, f.name)
    ]
    unexplained = sorted(set(exposed) - set(_ALL_INTERFACES))
    assert not unexplained, f"published on every interface; bind 127.0.0.1 or list it with a reason: {unexplained}"
    stale = sorted(set(_ALL_INTERFACES) - set(exposed))
    assert not stale, f"allowances for ports no longer published that way: {stale}"


def test_redis_is_loopback_only() -> None:
    compose = yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))
    ports = compose["services"]["autobot-redis"]["ports"]
    assert all(_host_ip_and_target(p)[0] in _LOOPBACK for p in ports), ports


def test_no_compose_credential_has_a_default() -> None:
    hits = {f.name: credential_defaults(f.read_text(encoding="utf-8")) for f in _compose_files()}
    assert not any(hits.values()), f"a credential falls back to a default instead of refusing to start: {hits}"


def test_no_compose_credential_is_a_literal() -> None:
    hits = {str(f.relative_to(_ROOT)): credential_literals(load_yaml_mapping(f)) for f in _compose_files()}
    assert not any(hits.values()), f"a credential is written into a compose file: {hits}"


def test_every_empty_credential_passthrough_has_a_reason() -> None:
    found = set().union(*(empty_passthroughs(f.read_text(encoding="utf-8")) for f in _compose_files()))
    assert not found - set(
        _EMPTY_WHEN_UNSET
    ), f"empty when unset, with no stated reason: {found - set(_EMPTY_WHEN_UNSET)}"
    assert (
        not set(_EMPTY_WHEN_UNSET) - found
    ), f"reasons for passthroughs that are gone: {set(_EMPTY_WHEN_UNSET) - found}"


def test_every_required_credential_is_one_generate_secrets_writes() -> None:
    required = set().union(*(required_credentials(f.read_text(encoding="utf-8")) for f in _compose_files()))
    generated = set(re.findall(r"^ensure_secret ([A-Z0-9_]+)", _GENERATOR.read_text(encoding="utf-8"), re.M))
    assert required, "no required credential found -- the detector is reading the wrong thing"
    assert (
        required <= generated
    ), f"compose requires credentials generate-secrets.sh never writes: {required - generated}"


def test_contrast_the_detectors_fire_on_the_old_shapes() -> None:
    old = {"services": {"autobot-redis": {"ports": ["${AUTOBOT_REDIS_PORT:-6379}:6379", "127.0.0.1:8001:8001"]}}}
    assert exposed_ports(old, "x.yml") == [("x.yml", "autobot-redis", "6379")]
    new = {"services": {"autobot-redis": {"ports": ["127.0.0.1:${AUTOBOT_REDIS_PORT:-6379}:6379"]}}}
    assert exposed_ports(new, "x.yml") == []
    opt_in = {"services": {"s": {"ports": ["${BIND:-127.0.0.1}:3100:3100", "${BIND:-0.0.0.0}:1:1"]}}}
    assert exposed_ports(opt_in, "x.yml") == [("x.yml", "s", "1")]
    long_form = {"services": {"s": {"ports": [{"target": 80, "published": 80}, {"target": 1, "host_ip": "127.0.0.1"}]}}}
    assert exposed_ports(long_form, "x.yml") == [("x.yml", "s", "80")]
    assert empty_passthroughs("J=${AUTOBOT_JWT_SECRET:-} K=${AUTOBOT_DB_PASSWORD:-autobot}") == {"AUTOBOT_JWT_SECRET"}
    planted = "=".join(("GF_SECURITY_ADMIN_PASSWORD", "fixture"))  # built here: no credential-shaped literal
    literal = {"services": {"grafana": {"environment": [planted, "GF_X=1"]}}}
    assert credential_literals(literal) == ["grafana/GF_SECURITY_ADMIN_PASSWORD"]
    as_map = {"services": {"s": {"environment": {"VNC_PASSWORD": "x", "OK_PASSWORD": "${OK_PASSWORD:?set}"}}}}
    assert credential_literals(as_map) == ["s/VNC_PASSWORD"]
    assert credential_defaults(
        "A=${AUTOBOT_DB_PASSWORD:-autobot} B=${SLM_ADMIN_PASSWORD-admin} C=${LOG_LEVEL:-INFO} D=${GH_TOKEN:-}"
    ) == [
        "${AUTOBOT_DB_PASSWORD:-autobot}",
        "${SLM_ADMIN_PASSWORD-admin}",
    ]
    assert required_credentials("X=${AUTOBOT_DB_PASSWORD:?run it} Y=${AUTOBOT_DOCKER_MGMT_PREFIX:?run it}") == {
        "AUTOBOT_DB_PASSWORD"
    }


def credential_values(env_text: str) -> list[str]:
    """Keys of a tracked env file that set a credential to a non-empty value."""
    return [
        m.group(1)
        for m in re.finditer(r"^([A-Z0-9_]+)=(.+)$", env_text, re.M)
        if _CREDENTIAL.search(m.group(1)) and m.group(2).strip()
    ]


def test_the_tracked_docker_env_file_sets_no_credential() -> None:
    """A tracked value satisfies compose's ${VAR:?} as well as a generated one does (#17793)."""
    assert not credential_values((_ROOT / "docker" / ".env.docker").read_text(encoding="utf-8"))
    assert credential_values("AUTOBOT_DB_USER=autobot\nAUTOBOT_DB_PASSWORD=autobot\nGH_TOKEN=\n") == [
        "AUTOBOT_DB_PASSWORD"
    ]


def _generator_in(stack: Path, volumes: str | None, secrets: str = "") -> subprocess.CompletedProcess:
    """Run the real generate-secrets.sh as if checked out at *stack*, with a stub `docker`."""
    bash = shutil.which("bash")
    if bash is None or shutil.which("openssl") is None:
        pytest.skip("bash and openssl are needed to run generate-secrets.sh")
    (stack / "docker").mkdir(parents=True)
    shutil.copy(_GENERATOR, stack / "docker" / "generate-secrets.sh")
    (stack / "docker" / ".env.secrets").write_text(secrets, encoding="utf-8")
    bin_dir = stack / "bin"
    bin_dir.mkdir()
    body = "exit 1" if volumes is None else f"printf '%s\\n' {volumes}"  # None: docker cannot answer
    (bin_dir / "docker").write_text(f"#!/bin/sh\n{body}\n", encoding="utf-8")
    (bin_dir / "docker").chmod(0o755)
    env = {"PATH": f"{bin_dir}:/usr/bin:/bin", "AUTOBOT_DOCKER_MGMT_PREFIX": "10.77.3"}
    return subprocess.run(
        [bash, str(stack / "docker" / "generate-secrets.sh")], capture_output=True, text=True, timeout=60, env=env
    )


def test_no_db_password_is_generated_over_an_existing_postgres_volume(tmp_path: Path) -> None:
    """27's review: Postgres keeps the password its volume was created with; a new one locks it out."""
    out = _generator_in(tmp_path / "stack", "stack_postgres_data")
    assert out.returncode != 0 and "the Postgres volume stack_postgres_data exists" in out.stderr, out.stderr
    assert "AUTOBOT_DB_PASSWORD" not in (tmp_path / "stack" / "docker" / ".env.secrets").read_text(encoding="utf-8")


def test_a_db_password_already_recorded_or_a_fresh_host_proceeds(tmp_path: Path) -> None:
    kept = _generator_in(tmp_path / "a" / "stack", "stack_postgres_data", "AUTOBOT_DB_PASSWORD=existing\n")
    assert kept.returncode == 0, kept.stderr
    assert "AUTOBOT_DB_PASSWORD=existing" in (tmp_path / "a" / "stack" / "docker" / ".env.secrets").read_text(
        encoding="utf-8"
    )
    fresh = _generator_in(tmp_path / "b" / "stack", "other_postgres_data")
    assert fresh.returncode == 0, fresh.stderr
    assert (
        tmp_path / "b" / "stack" / "docker" / ".env.secrets"
    ).stat().st_mode & 0o077 == 0, "secrets file not owner-only"


def usage_lines_missing_secrets(text: str) -> list[str]:
    """Commented `docker compose` usage lines that pass .env.docker but not .env.secrets."""
    lines = text.splitlines()
    joined = [
        (line + " " + lines[i + 1]) if line.rstrip().endswith("\\") and i + 1 < len(lines) else line
        for i, line in enumerate(lines)
    ]
    # Canonical comment syntax (#17941): a line the shared helper does not keep is a comment.
    code_linenos = {cl.lineno for cl in code_lines(text, name="compose.yml")}
    return [
        line.strip()
        for lineno, line in enumerate(joined, 1)
        if lineno not in code_linenos
        and line.strip()
        and "docker compose" in line
        and "--env-file docker/.env.docker" in line
        and ".env.secrets" not in line
    ]


def test_every_documented_compose_command_passes_the_secrets_file() -> None:
    """27's review: the base file's ${VAR:?} is interpolated before an overlay merges, so a usage
    line without docker/.env.secrets aborts -- the hardened overlay's header did."""
    hits = {
        str(f.relative_to(_ROOT)): usage_lines_missing_secrets(f.read_text(encoding="utf-8")) for f in _compose_files()
    }
    assert not any(hits.values()), hits
    assert usage_lines_missing_secrets("#   docker compose -f a.yml \\\n#     --env-file docker/.env.docker up -d\n")


def test_when_docker_cannot_be_asked_no_db_password_is_generated(tmp_path: Path) -> None:
    """27's review: not knowing whether a volume exists must refuse, not assume a fresh host."""
    out = _generator_in(tmp_path / "stack", None)
    assert out.returncode != 0 and "docker cannot be asked" in out.stderr, out.stderr
    assert "AUTOBOT_DB_PASSWORD" not in (tmp_path / "stack" / "docker" / ".env.secrets").read_text(encoding="utf-8")


_SMOKE_WORKFLOWS = (".github/workflows/_gate-docker-smoke.yml", ".github/workflows/co-located-smoke.yml")


def smoke_exported_credentials(workflow_text: str) -> set[str]:
    """The keys a smoke workflow's 'Required credentials' step exports."""
    m = re.search(r"for key in ([A-Z0-9_ ]+); do", workflow_text)
    return set(m.group(1).split()) if m else set()


def test_each_smoke_job_exports_exactly_the_credentials_compose_requires() -> None:
    """The workflows' own comment says this guard exists; without it a newly required credential
    would abort the smoke jobs at compose up (27's review)."""
    required = set().union(
        *(required_credentials(f.read_text(encoding="utf-8")) for f in [_ROOT / "docker-compose.yml"])
    )
    assert required, "no required credential found in docker-compose.yml"
    for rel in _SMOKE_WORKFLOWS:
        exported = smoke_exported_credentials((_ROOT / rel).read_text(encoding="utf-8"))
        assert exported == required, f"{rel} exports {sorted(exported)}, compose requires {sorted(required)}"
    assert smoke_exported_credentials("          for key in A_PASSWORD B_SECRET; do\n") == {"A_PASSWORD", "B_SECRET"}
