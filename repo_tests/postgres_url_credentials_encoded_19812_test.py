# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""#19812: Ansible's connection URLs carry encoded credentials, and the backup's shell builds none."""

from __future__ import annotations

import os
import re
import subprocess
from urllib.parse import unquote, urlsplit

import jinja2
import pytest
import yaml
from repo_tests._paths import repo_root
from sqlalchemy.engine import make_url

from autobot_shared.postgres_dsn import build_postgres_dsn

_ANSIBLE = "autobot-slm-backend/ansible"
_DEFAULTS = f"{_ANSIBLE}/roles/postgresql/defaults/main.yml"
_BACKUP = f"{_ANSIBLE}/_shared/tasks/pre_migration_backup.yml"
_ROLE_URL_SITES = [
    f"{_ANSIBLE}/roles/postgresql/templates/db-credentials.env.j2",
    f"{_ANSIBLE}/roles/postgresql/tasks/databases.yml",
]
_SINGLE_BOX = f"{_ANSIBLE}/playbooks/provision-backend-db-single-box.yml"
_NASTY = "a@:/%b"


def _read(rel: str) -> str:
    return (repo_root() / rel).read_text(encoding="utf-8")


def test_the_role_credentials_parse_back_with_the_host_intact() -> None:
    expr = yaml.safe_load(_read(_DEFAULTS))["db_url_credentials"]
    creds = jinja2.Environment(autoescape=False).from_string(expr).render(db_user="u@x", db_password=_NASTY)
    parts = urlsplit(f"postgresql+asyncpg://{creds}@db.local:5432/name")
    assert (unquote(parts.username), unquote(parts.password), parts.hostname) == ("u@x", _NASTY, "db.local")


@pytest.mark.parametrize("site", _ROLE_URL_SITES)
def test_each_role_url_uses_the_encoded_credentials(site: str) -> None:
    urls = re.findall(r"postgresql\+asyncpg://[^\n]*", _read(site))
    assert urls and all(u.startswith("postgresql+asyncpg://{{ db_url_credentials }}@") for u in urls)


def test_the_single_box_url_encodes_both_credentials() -> None:
    url = re.search(r"AUTOBOT_DATABASE_URL=(\S.*)", _read(_SINGLE_BOX)).group(1)
    assert url.count("urlencode | replace('/', '%2F')") == 2


def test_the_backup_gives_libpq_the_raw_credentials_outside_the_url() -> None:
    lines = [ln.strip() for ln in _read(_BACKUP).splitlines()]
    start = lines.index('elif [ -n "${AUTOBOT_POSTGRES_HOST:-}" ]; then') + 1
    body = "\n".join(ln for ln in lines[start : start + 4] if ln.startswith(("export ", 'DUMP_URL="')))
    env = {
        "PATH": os.environ["PATH"],
        "AUTOBOT_POSTGRES_HOST": "db.local",
        "AUTOBOT_POSTGRES_USER": "u",
        "AUTOBOT_POSTGRES_PASSWORD": _NASTY,
    }
    script = f'{body}\nprintf "%s\\n%s\\n%s\\n" "$PGUSER" "$PGPASSWORD" "$DUMP_URL"'
    out = subprocess.run(["bash", "-c", script], capture_output=True, text=True, check=True, env=env).stdout
    assert out.split("\n")[:3] == ["u", _NASTY, "postgresql://db.local:5432/autobot_users"]


def test_sqlalchemy_reads_the_real_password_and_renders_it_back_encoded() -> None:
    url = make_url(build_postgres_dsn("postgresql", "user", _NASTY, "db.local", 5432, "name"))
    assert url.password == _NASTY and url.host == "db.local"
    assert make_url(url.render_as_string(hide_password=False)).password == _NASTY
