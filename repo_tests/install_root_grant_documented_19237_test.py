# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""The service account's root grant is documented exactly as the installer writes it (#19237).

install.sh gives the `autobot` account `NOPASSWD:ALL`, and neither INSTALL.md nor README
mentioned it. On the owner's decision (2026-10-22), INSTALL.md now states the grant, why it is
that broad (Ansible become, sudo -n callers), how to audit it and how to remove it; narrowing
it is #19245. This keeps the documented line identical to the one install.sh writes, so the
doc cannot describe a grant the installer no longer makes, or miss a wider one.
"""

from __future__ import annotations

import re

from repo_tests._paths import repo_root

_ROOT = repo_root()


def test_install_md_documents_the_exact_grant_and_how_to_remove_it() -> None:
    install = (_ROOT / "install.sh").read_text(encoding="utf-8")
    m = re.search(r'echo "\$\{AUTOBOT_USER\} (ALL=\(ALL\) NOPASSWD:ALL)" > (/etc/sudoers\.d/autobot)', install)
    assert m, "install.sh's sudoers grant changed; update INSTALL.md's account section with it"
    doc = (_ROOT / "INSTALL.md").read_text(encoding="utf-8")
    assert f"`autobot {m.group(1)}`" in doc and f"`{m.group(2)}`" in doc, "INSTALL.md does not state the grant"
    for needed in ("root-equivalent", "sudo -l -U autobot", "sudo rm /etc/sudoers.d/autobot", "#19245"):
        assert needed in doc, f"INSTALL.md's account section lost: {needed}"
