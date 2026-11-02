# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#20639: the SLM's databases move to their own Postgres, once, with the originals untouched.

Runs the real script against two real Postgres clusters. Skipped where the binaries aren't installed.
"""

from __future__ import annotations

import os
import shutil
import socket
import subprocess
from pathlib import Path

import pytest
import yaml

_ROOT = Path(__file__).resolve().parents[1]
_SCRIPT = _ROOT / "docker" / "postgres" / "copy-slm-databases.sh"
_BIN = Path("/usr/lib/postgresql/16/bin")
_USER = "autobot"
_PASSWORD = "pw"  # pragma: allowlist secret


def _free_port() -> int:
    with socket.socket() as sock:
        sock.bind(("127.0.0.1", 0))
        return sock.getsockname()[1]


class _Cluster:
    def __init__(self, base: Path) -> None:
        self.data, self.port = base, _free_port()
        pwfile = base.with_suffix(".pw")
        pwfile.write_text(_PASSWORD, encoding="utf-8")
        subprocess.run(
            [_BIN / "initdb", "-D", base, "-U", _USER, "--pwfile", pwfile, "-A", "md5"],
            check=True,
            capture_output=True,
        )
        self.start()

    def start(self) -> None:
        options = f"-p {self.port} -k {self.data} -c listen_addresses=127.0.0.1"
        subprocess.run(
            [_BIN / "pg_ctl", "-D", self.data, "-w", "-l", self.data / "log", "-o", options, "start"],
            check=True,
            capture_output=True,
        )

    def stop(self) -> None:
        subprocess.run([_BIN / "pg_ctl", "-D", self.data, "-w", "-m", "fast", "stop"], capture_output=True)

    def sql(self, database: str, statement: str) -> str:
        done = subprocess.run(
            [_BIN / "psql", "-h", "127.0.0.1", "-p", str(self.port), "-U", _USER, "-d", database, "-qtAc", statement],
            env={**os.environ, "PGPASSWORD": _PASSWORD},
            check=True,
            capture_output=True,
            text=True,
        )
        return done.stdout.strip()


@pytest.fixture
def clusters(tmp_path):
    if not (_BIN / "initdb").exists() or os.geteuid() == 0:
        pytest.skip("needs the Postgres 16 binaries and a non-root user")
    old, new = _Cluster(tmp_path / "old"), _Cluster(tmp_path / "new")
    new.sql("postgres", "CREATE DATABASE autobot_slm")
    yield old, new
    old.stop()
    new.stop()


def _seed_old(old: _Cluster) -> None:
    for database, value in (("autobot_slm", "node-1"), ("slm_users", "admin")):
        old.sql("postgres", f"CREATE DATABASE {database}")
        old.sql(database, f"CREATE TABLE t (v text); INSERT INTO t VALUES ('{value}')")


def _copy(old: _Cluster, new: _Cluster, old_data: Path, wait: int = 0, **extra: str) -> subprocess.CompletedProcess:
    env = {
        **os.environ,
        "PATH": f"{_BIN}:{os.environ['PATH']}",
        "POSTGRES_USER": _USER,
        "PGPASSWORD": _PASSWORD,
        "SLM_DB_NAME": "autobot_slm",
        "SLM_COPY_OLD_HOST": "127.0.0.1",
        "SLM_COPY_NEW_HOST": "127.0.0.1",
        "SLM_COPY_OLD_PORT": str(old.port),
        "SLM_COPY_NEW_PORT": str(new.port),
        "SLM_COPY_OLD_DATA": str(old_data),
        "SLM_COPY_WAIT_SECONDS": str(wait),
        **extra,
    }
    return subprocess.run(
        [shutil.which("bash"), _SCRIPT], env=env, capture_output=True, text=True, timeout=120, check=False
    )


def test_an_existing_install_is_copied_and_the_originals_stay(clusters) -> None:
    old, new = clusters
    _seed_old(old)
    done = _copy(old, new, old.data)
    assert done.returncode == 0, done.stderr
    assert new.sql("autobot_slm", "SELECT v FROM t") == "node-1"
    assert new.sql("slm_users", "SELECT v FROM t") == "admin"
    assert old.sql("autobot_slm", "SELECT v FROM t") == "node-1"


def test_after_the_copy_the_main_postgres_can_be_down(clusters) -> None:
    old, new = clusters
    _seed_old(old)
    assert _copy(old, new, old.data).returncode == 0
    new.sql("autobot_slm", "INSERT INTO t VALUES ('written after the move')")
    old.stop()
    again = _copy(old, new, old.data)
    old.start()
    assert again.returncode == 0, again.stderr
    assert new.sql("autobot_slm", "SELECT count(*) FROM t") == "2", "a second run must not copy over newer data"


def test_a_fresh_install_has_nothing_to_copy(clusters, tmp_path) -> None:
    old, new = clusters
    old.stop()
    done = _copy(old, new, tmp_path / "empty-volume")
    old.start()
    assert done.returncode == 0, done.stderr
    assert new.sql("postgres", "SELECT count(*) FROM pg_database WHERE datname = 'slm_copy_done'") == "1"


def test_old_data_it_cannot_reach_stops_the_slm_and_says_why(clusters) -> None:
    old, new = clusters
    _seed_old(old)
    old.stop()
    done = _copy(old, new, old.data)
    old.start()
    assert done.returncode != 0
    assert "docker compose up -d autobot-postgres" in done.stderr
    assert new.sql("postgres", "SELECT count(*) FROM pg_database WHERE datname = 'slm_copy_done'") == "0"


def test_a_rerun_after_a_partial_copy_completes_it(clusters) -> None:
    old, new = clusters
    _seed_old(old)
    new.sql("autobot_slm", "CREATE TABLE t (v text); INSERT INTO t VALUES ('partial')")
    done = _copy(old, new, old.data)
    assert done.returncode == 0, done.stderr
    assert new.sql("autobot_slm", "SELECT v FROM t") == "node-1"


def _marked(new: _Cluster) -> bool:
    return new.sql("postgres", "SELECT count(*) FROM pg_database WHERE datname = 'slm_copy_done'") == "1"


def test_a_failed_query_on_the_old_server_stops_and_marks_nothing(clusters) -> None:
    """A wrong password must not read as "nothing to copy": the SLM would start empty."""
    old, new = clusters
    _seed_old(old)
    old.sql("postgres", "ALTER ROLE autobot PASSWORD 'other'")
    done = _copy(old, new, old.data)
    assert done.returncode != 0 and not _marked(new)
    assert "nothing was copied" in done.stderr


def test_the_marker_name_is_refused_as_the_slm_database(clusters) -> None:
    old, new = clusters
    done = _copy(old, new, old.data, SLM_DB_NAME="slm_copy_done")
    assert done.returncode != 0 and not _marked(new)


def test_a_database_name_with_an_apostrophe_is_still_copied(clusters) -> None:
    old, new = clusters
    old.sql("postgres", 'CREATE DATABASE "team\'s_slm"')
    old.sql("team's_slm", "CREATE TABLE t (v text); INSERT INTO t VALUES ('x')")
    done = _copy(old, new, old.data, SLM_DB_NAME="team's_slm")
    assert done.returncode == 0, done.stderr
    assert new.sql("team's_slm", "SELECT v FROM t") == "x"


def test_grants_to_a_role_the_new_server_lacks_dont_stop_the_copy(clusters) -> None:
    old, new = clusters
    _seed_old(old)
    old.sql("postgres", "CREATE ROLE gone")
    old.sql("autobot_slm", "GRANT SELECT ON t TO gone")
    done = _copy(old, new, old.data)
    assert done.returncode == 0, done.stderr


def test_a_custom_slm_role_exists_afterwards_and_can_read_the_copy(clusters) -> None:
    old, new = clusters
    _seed_old(old)
    done = _copy(old, new, old.data, SLM_POSTGRES_USER="slm_app")
    assert done.returncode == 0, done.stderr
    assert new.sql("autobot_slm", "SET ROLE slm_app; SELECT v FROM t") == "node-1"


def _services() -> dict:
    return yaml.safe_load((_ROOT / "docker-compose.yml").read_text(encoding="utf-8"))["services"]


def test_the_slm_doesnt_need_the_main_postgres_to_start() -> None:
    depends = _services()["autobot-slm"]["depends_on"]
    assert "autobot-postgres" not in depends
    assert depends["autobot-slm-postgres-copy"]["condition"] == "service_completed_successfully"


def test_the_copy_step_doesnt_depend_on_the_main_postgres_and_reads_its_volume_only() -> None:
    copy = _services()["autobot-slm-postgres-copy"]
    assert list(copy["depends_on"]) == ["autobot-slm-postgres"]
    assert "postgres_data:/old-postgres:ro" in copy["volumes"]


def test_the_slm_has_its_own_volume() -> None:
    assert "slm_postgres_data:/var/lib/postgresql/data" in _services()["autobot-slm-postgres"]["volumes"]


def test_every_healthy_dependency_can_become_healthy_and_is_reachable() -> None:
    """A dependent of a service with no healthcheck or shared network never starts (#20641 review)."""
    services = _services()

    def networks(service: dict) -> set:
        return set(service.get("networks") or [])

    for name, service in services.items():
        depends = service.get("depends_on") or {}
        for dependency, rule in (depends.items() if isinstance(depends, dict) else ()):
            if rule.get("condition") == "service_healthy":
                assert "healthcheck" in services[dependency], f"{name} waits on {dependency}, which has no healthcheck"
            if services[dependency].get("networks") and service.get("networks"):
                assert networks(service) & networks(services[dependency]), f"{name} can't reach {dependency}"


def test_the_slm_postgres_has_the_address_the_fleet_expects() -> None:
    address = _services()["autobot-slm-postgres"]["networks"]["autobot-mgmt"]["ipv4_address"]
    assert address.endswith(".18")
    fleet = (_ROOT / "autobot-slm-backend" / "services" / "compose_fleet.py").read_text(encoding="utf-8")
    assert '"id": "autobot-slm-postgres"' in fleet and '"host": 18' in fleet
