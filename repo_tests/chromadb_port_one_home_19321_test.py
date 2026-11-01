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
and fails on one outside the record, whatever its value: a re-added copy is the finding, not only
a conflicting one. A pinned file is swept too, with only its pinned sites masked (:func:`masked`),
so a second definition beside a pinned one is caught. Reach is declared (:data:`SCAN`) and bound
on what the sweep READ, not on what it listed.
"""

from __future__ import annotations

import re
from pathlib import Path

import yaml
from repo_tests._paths import repo_root
from repo_tests._pinned_sweep import masked
from repo_tests._reach import declare

from autobot_shared.ssot_config import PortConfig
from tools.lint._comment_syntax import strip_trailing_comment
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

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
_COMPOSE_CLIENT = r"^\s+- AUTOBOT_CHROMADB_PORT=(\d+)$"

#: The sites each recorded file may state the port at: its pin, or compose's in-network clients.
_RECORDED: dict[str, str] = {**{rel: pattern for rel, (pattern, _) in PINNED.items()}, COMPOSE: _COMPOSE_CLIENT}

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
    # A whole-line `//` comment counts; a trailing `//` would cut `http://` URLs, so only `#` trails.
    if not strip_trailing_comment(line.lstrip(), ("//",)):
        return ""
    return strip_trailing_comment(line, ("#",))


def named_definitions(text: str) -> list[int]:
    """Every named ChromaDB port definition in *text*."""
    out = []
    for line in text.splitlines():
        out.extend(int(m) for m in _NAMED.findall(_strip_comment(line)))
    return out


def unrecorded_definitions(texts: dict[str, str]) -> list[str]:
    """``path: values`` for each named ChromaDB port definition outside the record."""
    found = []
    for rel, text in texts.items():
        if _SKIP.search(rel):
            continue
        values = named_definitions(masked(text, _RECORDED[rel]) if rel in _RECORDED else text)
        if values:
            found.append(f"{rel}: {values}")
    return found


def _tracked() -> list[str]:
    return tracked_paths(_ROOT)


def _swept(root: Path) -> list[str]:
    """Tracked files outside docs and tests, the recorded ones included; ``[]`` on an empty tree."""
    try:
        paths = tracked_paths(root)
    except EmptyEnumeration:
        return []
    return [rel for rel in paths if not _SKIP.search(rel)]


SCAN = declare(
    "chromadb-port-one-home-scan",
    discover=_swept,
    floor=6718,  # mid-window: population 6802, window (6643, 6793)
    growth=150,
    skips=9,  # tracked binaries (images, icons, executables) that do not decode as UTF-8
    what="tracked non-doc, non-test files swept for a named ChromaDB port definition",
)


def readable(root: Path, paths: list[str]) -> dict[str, str]:
    """The text of each path that decodes; the rest are counted out by ``SCAN.completed``."""
    texts = {}
    for rel in paths:
        try:
            texts[rel] = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
    return texts


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
    clients = [int(v) for v in re.findall(_COMPOSE_CLIENT, text, re.M)]
    return host, container, clients


def test_compose_publishes_the_ssot_port_and_clients_dial_the_container_port() -> None:
    host, container, clients = _compose_chromadb()
    assert host == CANONICAL, f"compose publishes ChromaDB on {host}, the SSOT says {CANONICAL}"
    assert len(clients) == COMPOSE_CONTAINER_PORT_SITES, clients
    assert set(clients) == {container}, f"in-network clients dial {clients}; the container listens on {container}"


def test_no_unrecorded_chromadb_port_definition() -> None:
    texts = readable(_ROOT, list(SCAN.examined(_ROOT)))
    SCAN.completed(len(texts))
    assert set(_RECORDED) <= set(texts), f"the sweep never read {sorted(set(_RECORDED) - set(texts))}"
    found = unrecorded_definitions(texts)
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


def test_a_re_added_copy_is_caught() -> None:
    # The deliberate copy: a role default that re-states the port, at the old compose value.
    rel = "autobot-slm-backend/ansible/roles/vector/defaults/main.yml"
    assert unrecorded_definitions({rel: "chromadb_port: 8000\nother_port: 9000\n"}) == [f"{rel}: [8000]"]
    assert unrecorded_definitions({rel: "other_port: 9000\n"}) == []


def test_a_second_definition_in_a_pinned_file_is_caught() -> None:
    # A pin admits its own sites, not the whole file: the unchanged role default passes, the
    # same file with an extra named port beside the pinned one fails.
    rel = "autobot-slm-backend/ansible/roles/ai-stack/defaults/main.yml"
    text = (_ROOT / rel).read_text(encoding="utf-8")
    assert unrecorded_definitions({rel: text}) == []
    assert unrecorded_definitions({rel: text + "chromadb_http_port: 9000\n"}) == [f"{rel}: [9000]"]


def test_masking_blanks_only_the_pinned_capture() -> None:
    pattern = PINNED["autobot-slm-backend/ansible/playbooks/deploy-aiml.yml"][0]
    text = "a: {{ chromadb_port | default(8100) }}\nchromadb_port: 8100\n"
    assert masked(text, pattern) == "a: {{ chromadb_port | default(____) }}\nchromadb_port: 8100\n"


def test_the_sweep_reads_what_it_lists(tmp_path: Path) -> None:
    (tmp_path / "ok.yml").write_text("chromadb_port: 8100\n", encoding="utf-8")
    (tmp_path / "bin.png").write_bytes(b"\x89PNG\xff\xfe")
    assert readable(tmp_path, ["ok.yml", "bin.png", "gone.yml"]) == {"ok.yml": "chromadb_port: 8100\n"}


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
