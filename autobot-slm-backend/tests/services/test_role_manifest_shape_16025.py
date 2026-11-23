# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Unit tests for services/role_manifest_shape.py (#16025).

``models.manifest`` has no AutoBot-internal dependency beyond pydantic, so
these build synthetic ``RoleManifest`` objects directly -- no need for
``test_role_registry.py``'s real-vs-stubbed-module bootstrap (that dance
exists only for ``role_registry.py``'s own ``models.database``/``sqlalchemy``
imports, which this module does not have).
"""

import ast
from pathlib import Path

import pytest

from models.manifest import (
    ManifestDeploy,
    ManifestHealth,
    ManifestPort,
    ManifestService,
    RoleManifest,
    ServiceType,
)
from services import role_manifest_shape as rms
from services.manifest_loader import ManifestLoader


def _manifest(role: str, services=(), health_endpoint: str | None = None, ports=()) -> RoleManifest:
    return RoleManifest(
        role=role,
        description="test fixture",
        deploy=ManifestDeploy(
            source=f"{role}/", destination=f"/opt/autobot/{role}/", sync_target=f"/opt/autobot/{role}"
        ),
        services=list(services),
        ports=list(ports),
        health=ManifestHealth(endpoint=health_endpoint) if health_endpoint else None,
    )


def _svc(name: str, **kw) -> ManifestService:
    return ManifestService(name=name, **kw)


# ---------------------------------------------------------------------------
# canonical_manifest_role / find_role_manifest
# ---------------------------------------------------------------------------


def test_bare_name_gets_the_autobot_prefix():
    assert rms.canonical_manifest_role("backend") == "autobot-backend"


def test_already_prefixed_name_is_unchanged():
    assert rms.canonical_manifest_role("autobot-llm-cpu") == "autobot-llm-cpu"


def test_the_shared_role_translates_its_underscore_to_a_hyphen():
    """autobot_shared -> autobot-shared, not autobot-autobot_shared (#16025)."""
    assert rms.canonical_manifest_role("autobot_shared") == "autobot-shared"


def test_direct_owner_gets_every_systemd_service_of_its_manifest():
    """The backend role owns autobot-backend's manifest directly (#16025 AC4)."""
    manifest = _manifest(
        "autobot-backend",
        services=[_svc("autobot-backend"), _svc("autobot-celery", slm_roles=["celery"])],
    )
    manifests = {"autobot-backend": manifest}
    resolved, owns_whole = rms.find_role_manifest("backend", manifests)
    assert resolved is manifest
    assert owns_whole is True
    assert rms.systemd_units("backend", manifest, owns_whole) == ["autobot-backend", "autobot-celery"]


def test_narrower_role_gets_only_its_own_tagged_service():
    """redis/postgres/chromadb share one manifest but stay independently assignable."""
    manifest = _manifest(
        "autobot-database",
        services=[
            _svc("autobot-database-redis", system_service="redis-stack-server", slm_roles=["redis"]),
            _svc("autobot-database-postgres", system_service="postgresql", slm_roles=["postgres"]),
        ],
    )
    manifests = {"autobot-database": manifest}
    resolved, owns_whole = rms.find_role_manifest("redis", manifests)
    assert owns_whole is False
    assert rms.systemd_units("redis", resolved, owns_whole) == ["redis-stack-server"]
    assert rms.systemd_units("postgres", resolved, owns_whole) == ["postgresql"]


def test_one_service_can_fan_out_to_two_hardware_variant_roles():
    """autobot-ollama backs both autobot-llm-cpu and autobot-llm-gpu (#16025)."""
    manifest = _manifest(
        "autobot-ollama",
        services=[_svc("ollama", system_service="ollama", slm_roles=["autobot-llm-cpu", "autobot-llm-gpu"])],
    )
    manifests = {"autobot-ollama": manifest}
    for role_name in ("autobot-llm-cpu", "autobot-llm-gpu"):
        resolved, owns_whole = rms.find_role_manifest(role_name, manifests)
        assert rms.systemd_units(role_name, resolved, owns_whole) == ["ollama"]


def test_a_oneshot_build_step_is_never_a_systemd_unit():
    manifest = _manifest(
        "autobot-frontend",
        services=[
            _svc("autobot-frontend-build", type=ServiceType.ONESHOT),
            _svc("autobot-frontend", system_service="nginx"),
        ],
    )
    assert rms.systemd_units("frontend", manifest, owns_whole_manifest=True) == ["nginx"]


def test_no_manifest_at_all_resolves_to_none():
    resolved, owns_whole = rms.find_role_manifest("tts-worker", {})
    assert resolved is None
    assert owns_whole is False


# ---------------------------------------------------------------------------
# health_from_manifest
# ---------------------------------------------------------------------------


def test_health_port_and_path_come_from_an_explicit_port():
    manifest = _manifest("autobot-x", health_endpoint="http://localhost:8100/api/v2/heartbeat")
    assert rms.health_from_manifest(manifest) == (8100, "/api/v2/heartbeat")


def test_health_port_defaults_from_https_when_the_url_has_none():
    port, _ = rms.health_from_manifest(_manifest("autobot-x", health_endpoint="https://localhost/api/health"))
    assert port == 443


def test_health_is_none_when_the_manifest_declares_none():
    assert rms.health_from_manifest(_manifest("autobot-x")) == (None, None)


# ---------------------------------------------------------------------------
# manifest_ports
# ---------------------------------------------------------------------------


def test_ports_are_exposed_as_plain_dicts():
    manifest = _manifest("autobot-x", ports=[ManifestPort(port=8100, public=False, loopback_only=True)])
    assert rms.manifest_ports(manifest) == [{"port": 8100, "protocol": "https", "public": False, "loopback_only": True}]


# ---------------------------------------------------------------------------
# apply_manifest_shape -- the AC5 divergence guarantee
# ---------------------------------------------------------------------------


def test_no_manifest_wraps_the_existing_string_into_a_sequence():
    role_data = {"name": "vnc", "systemd_service": "tigervncserver", "source_paths": [], "target_path": "/x"}
    result = rms.apply_manifest_shape(role_data, {})
    assert result["systemd_service"] == ["tigervncserver"]
    assert "canonical_name" not in result


def test_manifest_found_but_no_matching_unit_falls_back_to_the_wrapped_literal():
    """slm-frontend: its manifest exists but declares only a oneshot build step."""
    build_step = _svc("autobot-slm-frontend-build", type=ServiceType.ONESHOT)
    manifest = _manifest("autobot-slm-frontend", services=[build_step])
    role_data = {"name": "slm-frontend", "systemd_service": "nginx"}
    result = rms.apply_manifest_shape(role_data, {"autobot-slm-frontend": manifest})
    assert result["systemd_service"] == ["nginx"]
    assert result["canonical_name"] == "autobot-slm-frontend"


def test_health_derivation_is_skipped_for_the_excluded_role():
    assert "slm-backend" in rms.HEALTH_DERIVATION_EXCLUDED
    manifest = _manifest(
        "autobot-slm-backend",
        services=[_svc("autobot-slm-backend")],
        health_endpoint="https://localhost/api/health",
    )
    role_data = {"name": "slm-backend", "systemd_service": "autobot-slm-backend", "health_check_port": 8000}
    result = rms.apply_manifest_shape(role_data, {"autobot-slm-backend": manifest})
    assert result["health_check_port"] == 8000, "the internal bind port must survive, not the external nginx URL"


def test_a_role_with_no_health_check_gains_none_from_a_shared_manifest():
    """celery runs from the backend manifest, whose one health endpoint is the backend's, not celery's."""
    manifest = _manifest(
        "autobot-backend", services=[_svc("autobot-celery", slm_roles=["celery"])], health_endpoint="https://x:8443/x"
    )
    role_data = {"name": "celery", "systemd_service": "autobot-celery"}
    result = rms.apply_manifest_shape(role_data, {"autobot-backend": manifest})
    assert "health_check_port" not in result


def test_registry_only_fields_are_never_touched():
    """The allowlist is not just documentation -- prove none of it gets set."""
    role_data = {
        "name": "backend",
        "systemd_service": "autobot-backend",
        **{field: object() for field in rms.REGISTRY_ONLY_FIELDS},
    }
    sentinels = {field: role_data[field] for field in rms.REGISTRY_ONLY_FIELDS}
    manifest = _manifest(
        "autobot-backend",
        services=[_svc("autobot-backend"), _svc("autobot-celery")],
        health_endpoint="https://localhost:8443/api/health",
        ports=[ManifestPort(port=8443)],
    )
    result = rms.apply_manifest_shape(role_data, {"autobot-backend": manifest})
    for field, sentinel in sentinels.items():
        assert result[field] is sentinel, f"{field} is registry-only but apply_manifest_shape changed it"


def test_registry_only_fields_may_only_shrink():
    """Ratchet (#16025): a phase 2 migration removes names from here, never adds."""
    assert len(rms.REGISTRY_ONLY_FIELDS) <= 7
    assert not {"source_paths", "target_path"} & rms.REGISTRY_ONLY_FIELDS, "derived from the manifest since #16025 AC1"


def test_derivation_reflects_the_manifest_it_is_given_not_a_frozen_copy():
    """The core AC5 guarantee: change the manifest, the derived shape changes too."""
    two_units = _manifest("autobot-backend", services=[_svc("autobot-backend"), _svc("autobot-celery")])
    one_unit = _manifest("autobot-backend", services=[_svc("autobot-backend")])

    role_data = {"name": "backend", "systemd_service": "autobot-backend"}
    first = rms.apply_manifest_shape(dict(role_data), {"autobot-backend": two_units})
    second = rms.apply_manifest_shape(dict(role_data), {"autobot-backend": one_unit})

    assert first["systemd_service"] == ["autobot-backend", "autobot-celery"]
    assert second["systemd_service"] == ["autobot-backend"]
    assert (
        first["systemd_service"] != second["systemd_service"]
    ), "two different manifests produced the same shape -- the derivation is not reading the manifest"


# ---------------------------------------------------------------------------
# End-to-end against the real, checked-in manifests
# ---------------------------------------------------------------------------


def test_the_real_backend_manifest_yields_all_its_systemd_units():
    """Proves the actual autobot-backend/manifest.yml (not a fixture) drives this.

    "backend" owns the whole manifest (find_role_manifest's direct-ownership
    branch), so it gets every systemd service the manifest declares --
    autobot-celery-beat included, even though that service also tags its own
    narrower "scheduler" role below.
    """
    from repo_tests._paths import repo_root

    loader = ManifestLoader(infra_base=repo_root() / "autobot-infrastructure")
    manifests = loader.load_all()
    resolved, owns_whole = rms.find_role_manifest("backend", manifests)
    assert resolved is not None, "autobot-backend/manifest.yml did not load"
    assert rms.systemd_units("backend", resolved, owns_whole) == [
        "autobot-backend",
        "autobot-celery",
        "autobot-celery-beat",
    ]


def test_the_real_backend_manifest_also_yields_celery_and_scheduler_alone():
    from repo_tests._paths import repo_root

    loader = ManifestLoader(infra_base=repo_root() / "autobot-infrastructure")
    manifests = loader.load_all()
    for role_name, expected in (("celery", ["autobot-celery"]), ("scheduler", ["autobot-celery-beat"])):
        resolved, owns_whole = rms.find_role_manifest(role_name, manifests)
        assert rms.systemd_units(role_name, resolved, owns_whole) == expected


# ---------------------------------------------------------------------------
# #16025 AC1 -- source_paths / target_path are derived, and derived to what the registry declared before
# ---------------------------------------------------------------------------

_BASE = "/opt/autobot"
_AGENT = "/opt/autobot/autobot-slm-agent"
_PLACEHOLDERS = {"base_dir": _BASE, "agent_dir": _AGENT}

#: (source_paths, target_path) every manifest-backed role syncs, with the default AUTOBOT_BASE_DIR / SLM_AGENT_DIR.
#: A change here is a change to what the code-sync does on a node. #21974: the six roles that synced into the install
#: root and the agent that synced into the agent directory now sync into the directory their unit runs from.
_BEFORE_THE_MOVE = {
    "slm-backend": (["autobot-slm-backend/"], f"{_BASE}/autobot-slm-backend"),
    "slm-frontend": (["autobot-slm-frontend/"], f"{_BASE}/autobot-slm-frontend"),
    "slm-database": ([], ""),
    "slm-monitoring": ([], ""),
    "backend": (["autobot-backend/"], f"{_BASE}/autobot-backend"),
    "celery": (["autobot-backend/"], f"{_BASE}/autobot-backend"),
    "scheduler": (["autobot-backend/"], f"{_BASE}/autobot-backend"),
    "frontend": (["autobot-frontend/"], f"{_BASE}/autobot-frontend"),
    "redis": ([], ""),
    "postgres": ([], "/var/lib/postgresql"),
    "chromadb": ([], ""),
    "ai-stack": (["autobot-infrastructure/shared/docker/ai-stack/"], f"{_BASE}/autobot-ai-stack"),
    "npu-worker": (["autobot-npu-worker/"], f"{_BASE}/autobot-npu-worker"),
    "browser-service": (["autobot-browser-worker/"], f"{_BASE}/autobot-browser-worker"),
    "autobot-llm-cpu": ([], ""),
    "autobot-llm-gpu": ([], ""),
    "autobot_shared": (["autobot_shared/"], f"{_BASE}/autobot_shared"),
    "slm-agent": (["autobot-slm-backend/slm/agent/"], f"{_AGENT}/slm/agent"),
}


def _real_manifests():
    from repo_tests._paths import repo_root

    return ManifestLoader(infra_base=repo_root() / "autobot-infrastructure").load_all()


def test_derived_sync_fields_equal_the_pinned_table():
    manifests = _real_manifests()
    for role_name, expected in _BEFORE_THE_MOVE.items():
        derived = rms.apply_manifest_shape({"name": role_name}, manifests, _PLACEHOLDERS)
        assert (derived["source_paths"], derived["target_path"]) == expected, role_name


def test_the_environment_override_still_decides_the_roots():
    manifests = _real_manifests()
    placeholders = {"base_dir": "/srv/ab", "agent_dir": "/srv/agent"}
    backend = rms.apply_manifest_shape({"name": "backend"}, manifests, placeholders)
    shared = rms.apply_manifest_shape({"name": "autobot_shared"}, manifests, placeholders)
    agent = rms.apply_manifest_shape({"name": "slm-agent"}, manifests, placeholders)
    assert backend["target_path"] == "/srv/ab/autobot-backend"
    assert shared["target_path"] == "/srv/ab/autobot_shared"
    assert agent["target_path"] == "/srv/agent/slm/agent"


def test_every_real_manifest_declares_its_sync_fields_explicitly():
    for role, manifest in _real_manifests().items():
        raw = manifest.deploy.model_fields_set
        assert "sync_target" in raw, f"{role}: deploy.sync_target not declared"
        assert manifest.deploy.sync or "sync" in raw, role
        if manifest.deploy.sync:
            assert manifest.deploy.sync_target, f"{role}: syncs but names no target"


def test_a_no_sync_manifest_ships_nothing():
    manifest = _manifest("autobot-x")
    manifest.deploy.sync, manifest.deploy.sync_target = False, ""
    assert rms.sync_from_manifest("x", manifest, True, _PLACEHOLDERS) == ([], "")


def test_a_service_sync_target_overrides_the_deploy_one_for_its_own_role_only():
    manifest = _manifest(
        "autobot-db", services=[_svc("pg", slm_roles=["postgres"], sync_target="/data"), _svc("r", slm_roles=["redis"])]
    )
    # Like the real autobot-database manifest: nothing is rsynced, so the deploy-level target is empty.
    manifest.deploy.sync, manifest.deploy.sync_target = False, ""
    assert rms.sync_from_manifest("postgres", manifest, False, _PLACEHOLDERS)[1] == "/data"
    assert rms.sync_from_manifest("redis", manifest, False, _PLACEHOLDERS)[1] == ""


# ---------------------------------------------------------------------------
# #16025 failure paths: a manifest-backed role that cannot resolve fails loudly, never with a silent drop
# ---------------------------------------------------------------------------


def test_a_manifest_backed_role_with_no_loaded_manifest_raises_naming_role_and_manifest():
    """The infra dir resolved to nothing: `load_all()` is {} and the role has no static copy of its own."""
    with pytest.raises(rms.RoleManifestMissingError) as caught:
        rms.apply_manifest_shape({"name": "backend", "systemd_service": "autobot-backend"}, {}, _PLACEHOLDERS)
    message = str(caught.value)
    assert "'backend'" in message and "autobot-backend" in message and "source_paths" in message


def test_one_unparsable_manifest_fails_its_role_not_the_others(tmp_path):
    """A manifest that fails to parse is absent from `load_all()`; only the roles it backs raise."""
    (tmp_path / "autobot-backend").mkdir()
    (tmp_path / "autobot-backend" / "manifest.yml").write_text("role: [unclosed\n", encoding="utf-8")
    good = tmp_path / "autobot-frontend"
    good.mkdir()
    (good / "manifest.yml").write_text(
        "role: autobot-frontend\ndescription: x\ndeploy:\n  source: autobot-frontend/\n  destination: /x/\n"
        '  sync_target: "{base_dir}"\n',
        encoding="utf-8",
    )
    manifests = ManifestLoader(infra_base=tmp_path).load_all()
    assert "autobot-backend" not in manifests
    assert rms.apply_manifest_shape({"name": "frontend"}, manifests, _PLACEHOLDERS)["target_path"] == "/opt/autobot"
    with pytest.raises(rms.RoleManifestMissingError, match="autobot-backend"):
        rms.apply_manifest_shape({"name": "backend"}, manifests, _PLACEHOLDERS)


def test_a_role_that_declares_its_own_shape_needs_no_manifest():
    """tts-worker, vnc and docker have no manifest; their static values stand."""
    role = {"name": "tts-worker", "source_paths": ["autobot-tts-worker/"], "target_path": "/x"}
    assert rms.apply_manifest_shape(dict(role), {}, _PLACEHOLDERS) == role


def test_a_syncing_manifest_without_a_sync_target_is_refused():
    with pytest.raises(ValueError, match="sync_target is empty"):
        ManifestDeploy(source="a/", destination="/a/")
    assert ManifestDeploy(source="a/", destination="/a/", sync=False).sync_target == ""


def test_an_unknown_placeholder_names_the_manifest_role_and_token():
    manifest = _manifest("autobot-x")
    manifest.deploy.sync_target = "{nope}/x"
    with pytest.raises(ValueError, match=r"autobot-x.*'x'.*'nope'"):
        rms.sync_from_manifest("x", manifest, True, _PLACEHOLDERS)


def test_a_failed_load_is_not_cached_and_the_cache_keys_on_the_placeholders(monkeypatch):
    from services import manifest_loader

    rms._default_roles_cache.clear()
    static = [{"name": "backend", "systemd_service": "autobot-backend"}]

    class _Loader:
        def __init__(self, manifests):
            self.manifests = manifests

        def load_all(self):
            return self.manifests

    monkeypatch.setattr(manifest_loader, "get_manifest_loader", lambda: _Loader({}))
    with pytest.raises(rms.RoleManifestMissingError):
        rms.default_roles_for(static, _PLACEHOLDERS)
    assert not rms._default_roles_cache, "a failed build must leave nothing behind"

    good = {"autobot-backend": _manifest("autobot-backend", services=[_svc("autobot-backend")])}
    good["autobot-backend"].deploy.sync_target = "{base_dir}"
    monkeypatch.setattr(manifest_loader, "get_manifest_loader", lambda: _Loader(good))
    first = rms.default_roles_for(static, _PLACEHOLDERS)[0]["target_path"]
    other = rms.default_roles_for(static, {"base_dir": "/srv/ab", "agent_dir": "/srv/ag"})[0]["target_path"]
    assert (first, other) == ("/opt/autobot", "/srv/ab")
    rms._default_roles_cache.clear()


# ---------------------------------------------------------------------------
# #16025 AC1 -- role shape is declared in one place: the registry restates none of it
# ---------------------------------------------------------------------------

_REPO_ROOT = Path(__file__).resolve().parents[3]
_REGISTRY_SOURCE = _REPO_ROOT / "autobot-slm-backend" / "services" / "role_registry.py"

#: Roles whose registry literal unit is the ONLY declaration: no manifest names a systemd unit for them.
_LITERAL_UNIT_ROLES = frozenset({"slm-frontend", "tts-worker", "vnc"})

#: The health every derived role had before the registry stopped restating it (#16025 AC1) -- the registry literal
#: and the manifest agreed for all of them, so dropping the literal changes nothing a consumer sees.
_EXPECTED_HEALTH = {
    "slm-frontend": (443, "/"),
    "slm-monitoring": (9090, "/-/healthy"),
    "backend": (8443, "/api/health"),
    "frontend": (443, "/api/health"),
    "ai-stack": (8080, "/health"),
    "chromadb": (8100, "/api/v2/heartbeat"),
    "npu-worker": (8081, "/health"),
    "browser-service": (9001, "/health"),
    "autobot-llm-cpu": (11434, "/api/tags"),
    "autobot-llm-gpu": (11434, "/api/tags"),
    "slm-backend": (8000, "/api/health"),
}


def _registry_role_fields() -> dict[str, set[str]]:
    tree = ast.parse(_REGISTRY_SOURCE.read_text(encoding="utf-8"))
    roles = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
            name = fields.get("name")
            if isinstance(name, ast.Constant) and "display_name" in fields:
                roles[name.value] = set(fields)
    return roles


def _registry_unit_literals() -> dict[str, object]:
    """``role name -> the systemd_service literal`` (str or list) the registry source holds."""
    tree = ast.parse(_REGISTRY_SOURCE.read_text(encoding="utf-8"))
    found = {}
    for node in ast.walk(tree):
        if isinstance(node, ast.Dict):
            fields = {k.value: v for k, v in zip(node.keys, node.values) if isinstance(k, ast.Constant)}
            name, unit = fields.get("name"), fields.get("systemd_service")
            if isinstance(name, ast.Constant) and "display_name" in fields and unit is not None:
                found[name.value] = ast.literal_eval(unit)
    return found


def test_the_registry_restates_no_health_a_manifest_provides():
    declared = {n for n, f in _registry_role_fields().items() if f & {"health_check_port", "health_check_path"}}
    owned = rms.HEALTH_DERIVED_ROLES | set(rms.HEALTH_OWN_BIND)
    assert (
        not declared & owned
    ), f"role_registry.py restates health the manifest/own-bind table owns: {declared & owned}"


def test_the_registry_restates_no_unit_a_manifest_declares():
    manifests = _real_manifests()
    restated = []
    for name, fields in _registry_role_fields().items():
        if "systemd_service" not in fields or name in _LITERAL_UNIT_ROLES:
            continue
        shaped = rms.apply_manifest_shape(
            {"name": name, "source_paths": [], "target_path": "/x"}, manifests, _PLACEHOLDERS
        )
        if shaped.get("systemd_service"):
            restated.append(name)
    assert not restated, f"role_registry.py still declares the unit of manifest-backed roles: {restated}"


def test_the_literal_unit_roles_have_no_manifest_unit():
    manifests = _real_manifests()
    for name in _LITERAL_UNIT_ROLES:
        shaped = rms.apply_manifest_shape(
            {"name": name, "source_paths": [], "target_path": "/x"}, manifests, _PLACEHOLDERS
        )
        assert not shaped.get("systemd_service"), f"{name} now has a manifest unit; drop its registry literal"


def test_every_derived_health_equals_what_the_registry_declared_before():
    manifests = _real_manifests()
    got = {}
    for name in _EXPECTED_HEALTH:
        shaped = rms.apply_manifest_shape(
            {"name": name, "source_paths": [], "target_path": "/x"}, manifests, _PLACEHOLDERS
        )
        got[name] = (shaped.get("health_check_port"), shaped.get("health_check_path"))
    assert got == _EXPECTED_HEALTH


def test_the_ssot_ports_still_match_the_manifest_health_ports():
    """The #19321 / #19324 one-home rule: the manifest's port is the SSOT port, now that no registry literal says so."""
    from autobot_shared.ssot_config import config

    ports = {name: port for name, (port, _path) in _EXPECTED_HEALTH.items()}
    assert ports["chromadb"] == config.port.chromadb
    assert ports["npu-worker"] == config.port.npu
    assert ports["browser-service"] == config.port.browser


def test_the_static_unit_reader_in_repo_tests_agrees_with_the_runtime_projection():
    from repo_tests._registry_role_units import registry_role_units

    manifests = _real_manifests()
    static = registry_role_units(_REPO_ROOT)
    literals = _registry_unit_literals()
    for name, units in static.items():
        role = {"name": name, "source_paths": [], "target_path": "/x"}
        if name in literals:
            role["systemd_service"] = literals[name]
        shaped = rms.apply_manifest_shape(role, manifests, _PLACEHOLDERS)
        assert units == (shaped.get("systemd_service") or []), name


def test_the_static_unit_reader_defaults_a_missing_type_to_systemd_like_the_manifest_model():
    from repo_tests._registry_role_units import _units_of

    services = [{"name": "untyped"}, {"name": "built", "type": "oneshot"}, {"name": "typed", "type": "systemd"}]
    assert _units_of(services, None) == ["untyped", "typed"]
    assert ManifestService(name="untyped").type == ServiceType.SYSTEMD


# ---------------------------------------------------------------------------
# #21974 AC3 -- the sync target is the install layout: what the unit runs from, which is the manifest's destination
# ---------------------------------------------------------------------------


def test_every_syncing_manifest_syncs_into_its_install_directory():
    """`deploy.sync_target` resolves to `deploy.destination`, so a code-sync updates the files the service loads.

    The install directory is what every unit's WorkingDirectory/ExecStart names (ansible/roles/*/templates, the
    SLM agent's `python -m slm.agent.agent` with PYTHONPATH on the agent directory) and where Ansible places the code.
    Source directories are rsynced by CONTENTS, so a target one level up (the install root, or the agent directory
    instead of its `slm/agent` package) writes files nothing loads.
    """
    from autobot_shared.fleet_constants import FLEET_AGENT_DIR, FLEET_INSTALL_ROOT

    placeholders = {"base_dir": FLEET_INSTALL_ROOT, "agent_dir": FLEET_AGENT_DIR}
    checked = []
    for role, manifest in _real_manifests().items():
        if not manifest.deploy.sync:
            continue
        target = manifest.deploy.sync_target.format_map(placeholders)
        assert target == manifest.deploy.destination.rstrip("/"), role
        checked.append(role)
    assert len(checked) >= 9, f"only {checked} were examined"
