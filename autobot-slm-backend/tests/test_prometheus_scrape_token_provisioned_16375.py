# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The Prometheus scrape token reaches both sides from one secret (#16375).

The backend refuses ``/api/metrics/prometheus`` without the token, so a token
that reaches only one side is an outage, and one that leaks into a rendered
config is a disclosure. The path under test:

* **generated** once at SLM startup into ``SystemSecret`` and mirrored to the
  System vault (``services.generated_system_secrets``);
* **delivered** as the ``prometheus_scrape_token`` extra var
  (``services.ansible_secrets``) to the backend role -> ``backend.env`` and to
  the monitoring role -> a 0640 token file named by ``bearer_token_file``;
* in compose, by ``secrets-init`` into the shared volume Prometheus mounts.

Rendered files are checked to carry the token only where it is meant to be:
the backend's own env file and the token file. ``prometheus.yml`` names the
file, never the value.
"""

from __future__ import annotations

import ast
import asyncio
import logging
from pathlib import Path
from unittest.mock import AsyncMock, patch

import pytest

yaml = pytest.importorskip("yaml")
jinja2 = pytest.importorskip("jinja2")

_SLM = Path(__file__).resolve().parents[1]
_REPO = _SLM.parent
_ANSIBLE = _SLM / "ansible"
_MON = _ANSIBLE / "roles" / "monitoring"
_BACKEND = _ANSIBLE / "roles" / "backend"
_TOKEN = "0123456789abcdef-scrape-token-under-test"  # nosec B105  # test fixture


def _env() -> "jinja2.Environment":
    env = jinja2.Environment(trim_blocks=True, lstrip_blocks=True, undefined=jinja2.ChainableUndefined)
    env.filters["bool"] = lambda v: v if isinstance(v, bool) else str(v).strip().lower() in {"true", "yes", "1"}
    return env


def _render_prometheus(**overrides) -> str:
    context = {
        "prometheus_port": 9090,
        "node_exporter_port": 9100,
        "groups": {"slm_nodes": []},
        "hostvars": {},
        "backend_port": 8001,
        "backend_nginx_port": 8443,
        "backend_host": "backend-node",
        "redis_host": "db-node",
        "prometheus_scrape_token": _TOKEN,
        "prometheus_scrape_token_file": "/etc/prometheus/autobot-scrape-token",
    }
    context.update(overrides)
    return _env().from_string((_MON / "templates" / "prometheus.yml.j2").read_text(encoding="utf-8")).render(**context)


def _backend_job(text: str) -> dict:
    return next(j for j in yaml.safe_load(text)["scrape_configs"] if j["job_name"] == "autobot-backend")


@pytest.mark.parametrize("loopback", [True, False], ids=["co-located", "distributed"])
def test_the_backend_job_names_the_token_file_and_never_the_token(loopback: bool) -> None:
    text = _render_prometheus(_backend_metrics_on_loopback=loopback, _backend_scrape_token_present=True)
    assert _backend_job(text)["bearer_token_file"] == "/etc/prometheus/autobot-scrape-token"
    assert _TOKEN not in text


def test_no_token_file_renders_no_bearer_token_file() -> None:
    text = _render_prometheus(_backend_scrape_token_present=False)
    assert "bearer_token_file" not in _backend_job(text)


def _config_tasks() -> list[dict]:
    return yaml.safe_load((_MON / "tasks" / "prometheus_config.yml").read_text(encoding="utf-8"))


def _named(fragment: str) -> dict:
    return next(t for t in _config_tasks() if fragment in t.get("name", ""))


def test_the_token_file_is_written_from_the_secret_privately() -> None:
    task = _named("Write the backend scrape token file")
    copy = task["ansible.builtin.copy"]
    assert copy["content"] == "{{ prometheus_scrape_token | trim }}"
    assert copy["dest"] == "{{ prometheus_scrape_token_file }}"
    assert (copy["mode"], copy["owner"], copy["group"]) == ("0640", "root", "{{ prometheus_group }}")
    assert task["no_log"] is True
    assert "length > 0" in task["when"], "an empty run must not blank a working token file"


def test_the_token_file_is_resolved_before_the_config_renders() -> None:
    names = [t.get("name", "") for t in _config_tasks()]
    resolve = next(i for i, n in enumerate(names) if "Resolve whether the backend job" in n)
    assert resolve < names.index("Create Prometheus config")


def test_the_backend_env_renders_the_token_from_the_secret() -> None:
    defaults = yaml.safe_load((_BACKEND / "defaults" / "main.yml").read_text(encoding="utf-8"))
    assert defaults["backend_prometheus_scrape_token"] == "{{ prometheus_scrape_token | default('') }}"
    template = (_BACKEND / "templates" / "backend.env.j2").read_text(encoding="utf-8")
    assert "AUTOBOT_PROMETHEUS_SCRAPE_TOKEN={{ backend_prometheus_scrape_token }}" in template


@pytest.mark.parametrize("task_file", ["main.yml", "env_only.yml"])
def test_every_backend_env_render_keeps_a_deployed_token(task_file: str) -> None:
    text = (_BACKEND / "tasks" / task_file).read_text(encoding="utf-8")
    assert "keep_prometheus_scrape_token.yml" in text


def test_the_keep_task_reads_silently_and_never_overrides_a_supplied_token() -> None:
    tasks = yaml.safe_load((_ANSIBLE / "_shared" / "tasks" / "keep_prometheus_scrape_token.yml").read_text())
    assert all(t.get("no_log") is True for t in tasks)
    for task in tasks:
        guards = task["when"] if isinstance(task["when"], list) else [task["when"]]
        assert any("prometheus_scrape_token | default('') | trim) | length == 0" in g for g in guards)


def test_the_slm_delivers_the_secret_to_deploys() -> None:
    """Read from the source: other tests replace ``services.ansible_secrets`` in sys.modules."""
    tree = ast.parse((_SLM / "services" / "ansible_secrets.py").read_text(encoding="utf-8"))
    node = next(
        n
        for n in ast.walk(tree)
        if isinstance(n, ast.AnnAssign) and getattr(n.target, "id", "") == "_SECRET_TO_ANSIBLE_VAR"
    )
    assert ast.literal_eval(node.value)["prometheus_scrape_token"] == "prometheus_scrape_token"


def test_the_slm_seeds_the_secret_at_startup() -> None:
    from services.generated_system_secrets import PROMETHEUS_SCRAPE_TOKEN

    assert PROMETHEUS_SCRAPE_TOKEN.key == "prometheus_scrape_token"
    assert PROMETHEUS_SCRAPE_TOKEN.mirror_to_vault is True
    assert "ensure_generated_secret(PROMETHEUS_SCRAPE_TOKEN)" in (_SLM / "main.py").read_text(encoding="utf-8")


def _ensure(inserted: bool, caplog) -> tuple[AsyncMock, str]:
    import services.generated_system_secrets as gen

    mirror = AsyncMock(return_value=True)
    with (
        patch.object(gen, "_insert_if_absent", AsyncMock(return_value=inserted)) as insert,
        patch("services.system_secrets_vault.mirror_secret_to_vault", mirror),
        caplog.at_level(logging.DEBUG),
    ):
        asyncio.run(gen.ensure_generated_secret(gen.PROMETHEUS_SCRAPE_TOKEN))
    return mirror, insert.call_args.args[1]


def test_a_generated_token_is_mirrored_and_never_logged(caplog) -> None:
    mirror, value = _ensure(True, caplog)
    assert len(value) == 64
    mirror.assert_awaited_once_with("prometheus_scrape_token", value)
    assert value not in caplog.text


def test_an_existing_token_is_never_replaced(caplog) -> None:
    import services.generated_system_secrets as gen

    with patch.object(gen, "_backfill_vault_copy", AsyncMock()):
        mirror, _value = _ensure(False, caplog)
    mirror.assert_not_awaited()


def test_compose_provisions_the_same_token_to_both_sides() -> None:
    init = (_REPO / "docker" / "secrets-init.sh").read_text(encoding="utf-8")
    assert "ensure_key _GEN_PROMETHEUS_SCRAPE_TOKEN gen_hex" in init
    assert 'TOKEN_FILE="/secrets/prometheus_scrape_token"' in init
    wrapper = (_REPO / "docker" / "with-secrets.sh").read_text(encoding="utf-8")
    assert 'AUTOBOT_PROMETHEUS_SCRAPE_TOKEN="${_GEN_PROMETHEUS_SCRAPE_TOKEN:-}"' in wrapper
    compose = yaml.safe_load((_REPO / "docker-compose.yml").read_text(encoding="utf-8"))
    assert "autobot_secrets:/run/autobot-secrets:ro" in compose["services"]["autobot-prometheus"]["volumes"]
    scrape = yaml.safe_load((_REPO / "autobot-monitoring" / "prometheus.yml").read_text(encoding="utf-8"))
    job = next(j for j in scrape["scrape_configs"] if j["job_name"] == "autobot-backend")
    assert job["bearer_token_file"] == "/run/autobot-secrets/prometheus_scrape_token"


def test_an_existing_token_missing_from_the_vault_is_mirrored_on_startup() -> None:
    """Review: a mirror that failed at first boot is retried on every later startup."""
    import services.generated_system_secrets as gen

    backfill = AsyncMock()
    with (
        patch.object(gen, "_insert_if_absent", AsyncMock(return_value=False)),
        patch.object(gen, "_backfill_vault_copy", backfill),
    ):
        asyncio.run(gen.ensure_generated_secret(gen.PROMETHEUS_SCRAPE_TOKEN))
        asyncio.run(gen.ensure_generated_secret(gen.SCIM_BEARER_TOKEN))
    backfill.assert_awaited_once_with(gen.PROMETHEUS_SCRAPE_TOKEN)


def test_a_failing_vault_retry_never_raises_or_logs_a_value(caplog) -> None:
    import services.generated_system_secrets as gen

    class _Boom(Exception):
        pass

    with (
        patch("services.database.db_service.session", side_effect=_Boom("secret-ish")),
        caplog.at_level(logging.DEBUG),
    ):
        asyncio.run(gen._backfill_vault_copy(gen.PROMETHEUS_SCRAPE_TOKEN))
    assert "secret-ish" not in caplog.text
