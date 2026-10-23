# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The SLM manager's node id has one name and one default: ``MiscConfig.slm_node_id`` (#19322).

The env name is ``AUTOBOT_SLM_NODE_ID``. ``SLM_NODE_ID`` is a different concept -- the SLM
agent's OWN id on each host (slm-agent.service sets it per node) -- and the SLM backend honours
it only as a deprecated alias of the manager id. A value can still disagree in three ways, and
each is a test here:

* a pinned copy (inventory, installer, shell mirror, .env template) drifts from the SSOT default;
* a literal fallback for either name is re-added anywhere (``getenv(.., "x")``, ``${..:-x}``,
  ``| default('x')``) -- the shape that produced ``01-Backend`` and a fixed hex id;
* the SLM backend stops resolving the canonical name first.
"""

from __future__ import annotations

import os
import re
import shutil
import subprocess
from pathlib import Path

import pytest
import yaml
from repo_tests._paths import repo_root

from autobot_shared.ssot_config import MiscConfig
from tools.lint._scan_helpers import tracked_paths

_ROOT = repo_root()

#: The one home. Read from the field, not restated.
CANONICAL = MiscConfig.model_fields["slm_node_id"].default

#: file -> (pattern, number of statements of the manager id). These cannot import Python.
PINNED: dict[str, tuple[str, int]] = {
    "autobot_shared/ssot_config.py": (r'slm_node_id: str = Field\(default="([^"]+)", alias="AUTOBOT_SLM_NODE_ID"', 1),
    "autobot-infrastructure/shared/scripts/lib/ssot-config.sh": (r"AUTOBOT_SLM_NODE_ID:=([^}]+)\}", 1),
    ".env.example": (r"^AUTOBOT_SLM_NODE_ID=(\S+)", 1),
    # The installer runs before the repository exists; its constant and generated inventory.
    "install.sh": (r'readonly SLM_NODE_ID="([^"]+)"|^\s+slm_node_id: "([^"]+)"', 2),
    "autobot-slm-backend/ansible/inventory/localhost.yml": (r'slm_node_id: "([^"]+)"', 1),
    "autobot-slm-backend/ansible/inventory/group_vars/all.yml": (r"\| default\('([^']+)'\)\) \}\}", 1),
}

#: A literal default for either name. `["']?` admits a quoted value; `${` does not match.
_FALLBACK = re.compile(
    r"(?:AUTOBOT_)?SLM_NODE_ID[\"']?\s*(?:,\s*[\"']|:?[-=][\"']?|\)\s*\|\s*default\(\s*[\"'])([A-Za-z0-9_-]+)",
)
_PY_LITERAL = re.compile(r"\bslm_node_id\s*(?::\s*str)?\s*=\s*[\"']([A-Za-z0-9_-]+)[\"']")
_SKIP = re.compile(r"(^docs/|\.md$|(^|/)tests?/|(^|/)test_[^/]*$|_test\.py$|^repo_tests/|^\.test_durations)")


def _values(text: str, pattern: str) -> list[str]:
    hits = re.findall(pattern, text, re.M)
    return [next(g for g in (h if isinstance(h, tuple) else (h,)) if g) for h in hits]


def _code(line: str) -> str:
    return "" if line.lstrip().startswith("#") else re.split(r"\s#\s", line, maxsplit=1)[0]


def literal_defaults(rel: str, text: str) -> list[str]:
    """Every literal default for the SLM node id in *text*."""
    out = []
    for line in map(_code, text.splitlines()):
        out.extend(_FALLBACK.findall(line))
        if rel.endswith(".py"):
            out.extend(_PY_LITERAL.findall(line))
    return out


def unrecorded_defaults(root: Path, paths: list[str]) -> list[str]:
    found = []
    for rel in paths:
        if rel in PINNED or _SKIP.search(rel):
            continue
        try:
            text = (root / rel).read_text(encoding="utf-8")
        except (UnicodeDecodeError, FileNotFoundError, IsADirectoryError):
            continue
        values = literal_defaults(rel, text)
        if values:
            found.append(f"{rel}: {values}")
    return found


def test_every_pinned_copy_equals_the_ssot() -> None:
    wrong = {}
    for path, (pattern, count) in PINNED.items():
        values = _values((_ROOT / path).read_text(encoding="utf-8"), pattern)
        if len(values) != count or any(v != CANONICAL for v in values):
            wrong[path] = values
    assert not wrong, f"SLM manager node id copies disagree with MiscConfig.slm_node_id={CANONICAL!r}: {wrong}"


def test_the_inventory_slm_server_host_is_the_ssot_id() -> None:
    inv = yaml.safe_load((_ROOT / "autobot-slm-backend/ansible/inventory/slm-nodes.yml").read_text("utf-8"))
    children = inv["all"]["children"]
    (manager,) = children["slm_server"]["hosts"]
    groups = [(g or {}).get("hosts") or {} for g in children.values()]
    ids = [(hosts[manager] or {}).get("slm_node_id") for hosts in groups if manager in hosts]
    assert manager == CANONICAL and CANONICAL in ids, (manager, ids)


def test_no_unrecorded_literal_default() -> None:
    tracked = tracked_paths(_ROOT)
    assert len(tracked) > 1000, "the tracked-file enumeration is near empty -- the sweep would pass vacuously"
    found = unrecorded_defaults(_ROOT, tracked)
    assert not found, f"a literal SLM node id default outside its home (read AUTOBOT_SLM_NODE_ID): {found}"


def test_a_re_added_default_is_caught(tmp_path: Path) -> None:
    # The deliberate copy: the enroll-local default this issue removed.
    rel = "autobot-slm-backend/ansible/playbooks/enroll-x.yml"
    (tmp_path / rel).parent.mkdir(parents=True)
    line = "    slm_node_id: \"{{ lookup('env', 'SLM_NODE_ID') | default('01-Backend', true) }}\"\n"
    (tmp_path / rel).write_text(line, encoding="utf-8")
    assert unrecorded_defaults(tmp_path, [rel]) == [f"{rel}: ['01-Backend']"]
    (tmp_path / rel).write_text("    slm_node_id: \"{{ lookup('env', 'SLM_NODE_ID') }}\"\n", encoding="utf-8")
    assert unrecorded_defaults(tmp_path, [rel]) == []


def test_the_sweep_reads_each_default_shape() -> None:
    text = (
        'X = os.getenv("SLM_NODE_ID", "00-SLM-Manager")\n'
        'SLM_NODE_ID="${SLM_NODE_ID:-33792bf5}"\n'
        ': "${AUTOBOT_SLM_NODE_ID:=a-b}"\n'
        'slm_node_id: str = "lit"\n'
        'SLM_NODE_ID="${AUTOBOT_SLM_NODE_ID}"\n'
        "Environment=SLM_NODE_ID={{ slm_node_id }}\n"
        "# SLM_NODE_ID=commented\n"
    )
    assert literal_defaults("x.py", text) == ["00-SLM-Manager", "33792bf5", "a-b", "lit"]


_HOOK = _ROOT / "autobot-infrastructure/shared/scripts/hooks/slm-post-commit"


def _hook_node_id(tmp_path: Path, config_text: str | None, exported: str = "") -> str:
    bash = shutil.which("bash")
    if bash is None:
        pytest.skip("bash unavailable")
    fn = re.search(r"^agent_node_id\(\) \{.*?^\}$", _HOOK.read_text(encoding="utf-8"), re.M | re.S)
    assert fn, "slm-post-commit no longer defines agent_node_id()"
    config = tmp_path / "config.yaml"
    if config_text is not None:
        config.write_text(config_text, encoding="utf-8")
    script = f'{fn.group(0)}\nSLM_NODE_ID="${{SLM_NODE_ID:-$(agent_node_id "{config}")}}"\necho "$SLM_NODE_ID"'
    env = {"PATH": os.environ.get("PATH", ""), **({"SLM_NODE_ID": exported} if exported else {})}
    return subprocess.run([bash, "-c", script], capture_output=True, text=True, env=env, timeout=30).stdout.strip()


def test_the_post_commit_hook_reads_the_agents_node_id(tmp_path: Path) -> None:
    # agent-config.yaml.j2 renders `node_id: "<id>"`; the hook's git shell has no agent environment.
    assert _hook_node_id(tmp_path, '# Node: x\n---\nnode_id: "a1b2c3d4"\nhostname: "h"\n') == "a1b2c3d4"
    assert _hook_node_id(tmp_path, "node_id: plain-id\n") == "plain-id"
    assert _hook_node_id(tmp_path, 'node_id: "a1b2c3d4"\n', exported="exported-id") == "exported-id"
    (tmp_path / "absent").mkdir()
    assert _hook_node_id(tmp_path / "absent", None) == "", "an absent agent config must skip, not invent an id"
