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
        deploy=ManifestDeploy(source=f"{role}/", destination=f"/opt/autobot/{role}/"),
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
    role_data = {"name": "vnc", "systemd_service": "tigervncserver"}
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


def test_a_role_with_no_health_field_today_gains_none_from_the_manifest():
    manifest = _manifest("autobot-backend", services=[_svc("autobot-backend")], health_endpoint="https://x:8443/x")
    role_data = {"name": "backend", "systemd_service": "autobot-backend"}
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
    assert len(rms.REGISTRY_ONLY_FIELDS) <= 9


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
