# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
"""install.sh gives the SLM secrets file the internal API key, and keeps one it already has (#10200).

Without it the backend sends an empty X-Internal-API-Key, the SLM answers 403, and the first
admin is never linked. The key is the SLM's canonical one that the Ansible resolver renders into
the backend env (#20750); install only provisions it, with the same generator as its other keys.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

from repo_tests._paths import repo_root

_KEY = "AUTOBOT_INTERNAL_API_KEY"


def _real_helper(text: str) -> str:
    """The installer's own _upsert_secrets_key, cut out of install.sh whole, so the test cannot drift from it."""
    match = re.search(r"^[ \t]*_upsert_secrets_key\(\) \{\n.*?^[ \t]*\}\n", text, re.M | re.S)
    assert match, "install.sh no longer defines _upsert_secrets_key"
    return match.group(0)


def _install() -> str:
    return (repo_root() / "install.sh").read_text(encoding="utf-8")


def test_the_fresh_secrets_file_is_written_with_the_key() -> None:
    heredoc = _install().split('(umask 077; cat > "${SECRETS_FILE}") << EOF', 1)[1].split("\nEOF", 1)[0]
    assert re.search(rf"^{_KEY}=\$\{{autobot_internal_api_key\}}$", heredoc, re.M)


def test_a_reinstall_keeps_an_existing_key_and_a_new_one_is_generated() -> None:
    line = next(ln for ln in _install().splitlines() if ln.strip().startswith("autobot_internal_api_key=$(grep"))
    assert f"^{_KEY}=" in line and "openssl rand -hex 32" in line


def test_a_preserved_file_without_the_key_gets_one_and_with_it_keeps_it(tmp_path: Path) -> None:
    line = next(ln for ln in _install().splitlines() if ln.strip().startswith(f"grep -q '^{_KEY}=.'"))
    helper = _real_helper(_install())
    assert line
    secrets = tmp_path / "slm-secrets.env"

    def run() -> str:
        script = helper + 'SECRETS_FILE="$1"\n' + line.strip() + "\n"
        subprocess.run(["bash", "-c", script, "bash", str(secrets)], check=True)
        return secrets.read_text(encoding="utf-8")

    secrets.write_text("SLM_HOST=a\n", encoding="utf-8")
    first = re.findall(rf"^{_KEY}=(.+)$", run(), re.M)
    assert len(first) == 1 and len(first[0]) == 64
    assert re.findall(rf"^{_KEY}=(.+)$", run(), re.M) == first
    secrets.write_text(f"{_KEY}=\nSLM_HOST=a\n", encoding="utf-8")
    assert len(re.findall(rf"^{_KEY}=(.{{64}})$", run(), re.M)) == 1
