# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""Test for deploy_autobot's generated Kubernetes manifest (#15585 sweep finding).

``deploy_kubernetes`` built the sample namespace manifest from a
triple-quoted string containing ``{self.namespace}`` with no ``f`` prefix,
so every ``namespace:`` field in the generated YAML declared the literal
text ``{self.namespace}`` instead of the deployer's real namespace -- a
manifest ``kubectl apply`` would either reject outright or, if accepted,
mis-scope. This asserts the written manifest contains the real namespace and
no leftover ``{identifier`` placeholder shape.
"""

import re
import subprocess
import sys
from pathlib import Path

# Lives here, not beside the script it tests -- see microservice_architecture_evaluator_test.py
# in this same directory for the ci.yml path-list reasoning (#14563, #14518).
_SCRIPTS_ROOT = Path(__file__).resolve().parents[1] / "scripts"
if str(_SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(_SCRIPTS_ROOT))

from deploy_autobot import AutoBotDeployer  # noqa: E402

_LEFTOVER_PLACEHOLDER_RE = re.compile(r"\{[A-Za-z_]")


def test_k8s_manifest_renders_real_namespace_not_placeholder(tmp_path: Path, monkeypatch):
    deployer = object.__new__(AutoBotDeployer)
    deployer.namespace = "autobot-staging"
    deployer.project_root = tmp_path

    # deploy_kubernetes gates manifest creation on `kubectl version --client`
    # succeeding; stub run_command so the test exercises the manifest text
    # without depending on kubectl being installed.
    monkeypatch.setattr(
        deployer,
        "run_command",
        lambda *args, **kwargs: subprocess.CompletedProcess(args=[], returncode=0),
    )

    deployer.deploy_kubernetes()

    manifest = (tmp_path / "k8s" / "autobot-deployment.yml").read_text(encoding="utf-8")

    assert not _LEFTOVER_PLACEHOLDER_RE.search(manifest), (
        "Kubernetes manifest contains an un-substituted {identifier} placeholder -- "
        "a triple-quoted string is missing its f prefix"
    )
    assert manifest.count("namespace: autobot-staging") == 2
    assert "name: autobot-staging" in manifest
