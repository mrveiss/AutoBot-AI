# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""ChromaDB's port has one home: ``PortConfig.chromadb`` in ``autobot_shared/ssot_config.py`` (#19321).

Python readers derive from it (``config.port.chromadb``). Files that cannot import Python --
ansible, shell, compose, manifests, the UI -- keep a copy, and every copy is recorded in
:data:`PINNED` with the number of times it states the port; each must equal the SSOT default.

Two meanings exist and are kept apart:

* **host port** -- what ChromaDB listens on outside a container (the ansible ai-stack and redis
  roles' systemd units, install-bare-metal.sh) and what host-side clients dial. This is the SSOT.
* **container port** -- the ``chromadb/chroma`` image's own listen port inside compose (8000).
  In-network compose clients dial it as ``AUTOBOT_CHROMADB_PORT``; compose publishes it on the
  host port. :data:`COMPOSE_CONTAINER_PORT_SITES` must all agree with the mapping's container side.

The sweep (:func:`unrecorded_definitions`) finds every *named* ChromaDB port definition in the
tree -- ``chromadb_port: N``, ``CHROMADB_PORT=N``, ``| default(N)``, ``${..CHROMADB_PORT:-N}`` --
and fails on one in a file outside the record, whatever its value: a re-added copy is the
finding, not only a conflicting one.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from repo_tests._paths import repo_root

from autobot_shared.ssot_config import PortConfig
from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()

#: The one home. Read from the field, not restated.
CANONICAL = PortConfig.model_fields["chromadb"].default

#: file -> (pattern with one capture group, how many times the file states the port).
PINNED: dict[str, tuple[str, int]] = {
    "autobot_shared/ssot_config.py": (r'chromadb: int = Field\(default=(\d+), alias="AUTOBOT_CHROMADB_PORT"', 1),
    "autobot-infrastructure/shared/scripts/lib/ssot-config.sh": (r"AUTOBOT_CHROMADB_PORT:=(\d+)", 1),
    "autobot-infrastructure/shared/scripts/install-bare-metal.sh": (r"^CHROMADB_PORT=(\d+)", 1),
    "autobot-infrastructure/autobot-database/templates/autobot-chromadb.service": (r"--port (\d+)", 1),
    "autobot-infrastructure/autobot-database/templates/db-start.sh": (r"(?:ChromaDB \(|127\.0\.0\.1:)(\d+)", 2),
    "autobot-infrastructure/autobot-database/templates/db-status.sh": (r"(?:ChromaDB \(|127\.0\.0\.1:)(\d+)", 2),
    "autobot-infrastructure/autobot-database/manifest.yml": (
        r'(?:- port: (\d+)\n(?:.*\n){3}\s*description: "ChromaDB|localhost:(\d+)/api/v2|ChromaDB on :(\d+))',
        3,
    ),
    "autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml": (r"^chromadb_port: (\d+)", 1),
    "autobot-slm-backend/ansible/roles/redis/defaults/main.yml": (r"^chromadb_port: (\d+)", 1),
    "autobot-slm-backend/ansible/roles/backend/defaults/main.yml": (r"^backend_chromadb_port: (\d+)", 1),
    "autobot-slm-backend/ansible/playbooks/vars/backend-env.yml": (r"^backend_chromadb_port: (\d+)", 1),
    "autobot-slm-backend/ansible/setup-ai-stack.yml": (r"^\s+chromadb_port: (\d+)", 1),
    "autobot-slm-backend/ansible/playbooks/deploy-aiml.yml": (r"chromadb_port \| default\((\d+)\)", 3),
    "autobot-slm-backend/ansible/playbooks/pre-deployment-validation.yml": (r'name: "ChromaDB"\n\s+port: (\d+)', 1),
    "autobot-slm-backend/ansible/playbooks/health-check.yml": (
        r'Test ChromaDB health endpoint[^\n]*\n\s+uri:\n\s+url: "http://127\.0\.0\.1:(\d+)',
        1,
    ),
}

#: Compose clients that dial ChromaDB inside the network: the container port, not the SSOT.
COMPOSE = "docker-compose.yml"
COMPOSE_CONTAINER_PORT_SITES = 3

#: Named definitions the sweep recognises (on comment-stripped lines).
_NAMED = re.compile(
    r"(?i)chroma\w*port\w*[\"']?\s*(?:[:=,]\s*[\"']?|\|\s*default\(|:?[-=])(\d{2,5})\b",
)
_SKIP = re.compile(r"(^docs/|\.md$|(^|/)tests?/|(^|/)test_[^/]*$|_test\.py$|\.test\.|^repo_tests/|^\.test_durations)")


def _pinned_values(path: str, pattern: str) -> list[int]:
    text = (_ROOT / path).read_text(encoding="utf-8")
    hits = re.findall(pattern, text, re.M)
    return [int(next(g for g in (h if isinstance(h, tuple) else (h,)) if g)) for h in hits]


def _strip_comment(line: str) -> str:
    stripped = line.lstrip()
    if stripped.startswith(("#", "//")):
        return ""
    return re.split(r"\s#\s", line, maxsplit=1)[0]


def named_definitions(text: str) -> list[int]:
    """Every named ChromaDB port definition in *text*."""
    out = []
    for line in text.splitlines():
        out.extend(int(m) for m in _NAMED.findall(_strip_comment(line)))
    return out


def unrecorded_definitions(root: Path, paths: list[str]) -> list[str]:
    """``path: values`` for each file outside the record that defines the ChromaDB port."""
    found = []
    for rel in paths:
        if rel in PINNED or rel == COMPOSE or _SKIP.search(rel):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        values = named_definitions(text)
        if values:
            found.append(f"{rel}: {values}")
    return found


def _tracked() -> list[str]:
    return tracked_paths(_ROOT)


def test_the_canonical_default_is_the_provisioned_port() -> None:
    # The ai-stack role's systemd unit listens on chromadb_port; it is the provisioning truth.
    role = yaml.safe_load((_ROOT / "autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml").read_text("utf-8"))
    assert role["chromadb_port"] == CANONICAL


def test_every_pinned_copy_equals_the_ssot() -> None:
    wrong = {}
    for path, (pattern, count) in PINNED.items():
        values = _pinned_values(path, pattern)
        if len(values) != count or any(v != CANONICAL for v in values):
            wrong[path] = values
    assert not wrong, f"ChromaDB port copies disagree with PortConfig.chromadb={CANONICAL} (or moved): {wrong}"


def _compose_chromadb() -> tuple[int, int, list[int]]:
    text = (_ROOT / COMPOSE).read_text(encoding="utf-8")
    mapping = yaml.safe_load(text)["services"]["autobot-chromadb"]["ports"][0]
    host, container = (int(p) for p in mapping.rsplit(":", 2)[-2:])
    clients = [int(v) for v in re.findall(r"^\s+- AUTOBOT_CHROMADB_PORT=(\d+)$", text, re.M)]
    return host, container, clients


def test_compose_publishes_the_ssot_port_and_clients_dial_the_container_port() -> None:
    host, container, clients = _compose_chromadb()
    assert host == CANONICAL, f"compose publishes ChromaDB on {host}, the SSOT says {CANONICAL}"
    assert len(clients) == COMPOSE_CONTAINER_PORT_SITES, clients
    assert set(clients) == {container}, f"in-network clients dial {clients}; the container listens on {container}"


def test_no_unrecorded_chromadb_port_definition() -> None:
    tracked = _tracked()
    assert len(tracked) > 1000, "git ls-files returned almost nothing -- the sweep would pass vacuously"
    found = unrecorded_definitions(_ROOT, tracked)
    assert not found, f"ChromaDB port defined outside its home (derive from config.port.chromadb): {found}"


#: Python readers that restated the port before #19321; each now derives from ``port.chromadb``.
PYTHON_READERS = (
    "autobot-backend/api/monitoring.py",
    "autobot-backend/api/service_monitor.py",
    "autobot-slm-backend/api/infrastructure.py",
    "autobot-slm-backend/api/setup_wizard.py",
    "autobot-slm-backend/services/role_registry.py",
    "autobot-slm-backend/services/security_posture_auditor.py",
    "autobot-slm-backend/services/service_orchestrator.py",
)


def test_the_python_readers_derive_from_the_ssot() -> None:
    literal = re.compile(r"(?<![\w.])\d{4,5}(?![\w.])")
    stale = {}
    for rel in PYTHON_READERS:
        text = (_ROOT / rel).read_text(encoding="utf-8")
        code = [_strip_comment(ln) for ln in text.splitlines()]
        # A literal on a chroma line, or the SSOT value anywhere (a dict entry need not say "chroma").
        hits = [ln.strip() for ln in code if literal.search(ln) and ("chroma" in ln.lower() or str(CANONICAL) in ln)]
        if hits or "port.chromadb" not in text:
            stale[rel] = hits
    assert not stale, f"a ChromaDB port literal is back (use config.port.chromadb): {stale}"


#: A ChromaDB value taken from the AI-stack's host or port -- the monitoring.py shape (#19321 review).
_FROM_AISTACK = re.compile(r"(?i)chroma\w*\s*=.*\baistack\b")


def aistack_borrowers(root: Path, paths: list[str]) -> list[str]:
    """``path:line`` for each ``chromadb_* = ...aistack...`` assignment in a Python file."""
    found = []
    for rel in paths:
        if not rel.endswith(".py") or _SKIP.search(rel) or not (root / rel).is_file():
            continue
        for no, line in enumerate((root / rel).read_text(encoding="utf-8").splitlines(), 1):
            if _FROM_AISTACK.search(_strip_comment(line)):
                found.append(f"{rel}:{no}")
    return found


def test_no_chromadb_value_is_taken_from_the_ai_stack() -> None:
    found = aistack_borrowers(_ROOT, _tracked())
    assert not found, f"ChromaDB is not the AI-stack service; use vm/port.chromadb: {found}"


def test_an_ai_stack_borrower_is_caught(tmp_path: Path) -> None:
    rel = "autobot-backend/api/probe.py"
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text('chromadb_port = ConfigRegistry.get("port.aistack")\n', encoding="utf-8")
    assert aistack_borrowers(tmp_path, [rel]) == [f"{rel}:1"]
    (tmp_path / rel).write_text('chromadb_port = ConfigRegistry.get("port.chromadb")\n', encoding="utf-8")
    assert aistack_borrowers(tmp_path, [rel]) == []


def test_a_re_added_copy_is_caught(tmp_path: Path) -> None:
    # The deliberate copy: a role default that re-states the port, at the old compose value.
    rel = "autobot-slm-backend/ansible/roles/vector/defaults/main.yml"
    (tmp_path / rel).parent.mkdir(parents=True)
    (tmp_path / rel).write_text("chromadb_port: 8000\nother_port: 9000\n", encoding="utf-8")
    assert unrecorded_definitions(tmp_path, [rel]) == [f"{rel}: [8000]"]
    (tmp_path / rel).write_text("other_port: 9000\n", encoding="utf-8")
    assert unrecorded_definitions(tmp_path, [rel]) == []


def test_the_sweep_reads_each_definition_shape() -> None:
    text = (
        "chromadb_port: 8100\n"
        "CHROMADB_PORT=8000\n"
        '  port: "{{ chromadb_port | default(8080) }}"\n'
        'P="${AUTOBOT_CHROMADB_PORT:-8200}"\n'
        "# chromadb_port: 9999 is a comment\n"
        "chromadb_host: 127.0.0.1\n"
    )
    assert named_definitions(text) == [8100, 8000, 8080, 8200]
