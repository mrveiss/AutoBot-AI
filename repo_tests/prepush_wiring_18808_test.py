# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The two non-selection checks tools/git-hooks/pre-push gained for #18808 stay wired.

Both caught defects only in CI before: the hardcoded-values baseline audit (#18708, #18790) and
the sys.modules leak guard (#18785). Their behaviour is tested where it lives
(pipeline-scripts/detect_hardcoded_values_audit_test.py; the probe module itself); this pins the
hook's invocations, whose loss would be silent -- a hook that skips a check still passes.
"""

from __future__ import annotations

from repo_tests._paths import repo_root

_HOOK = repo_root() / "tools" / "git-hooks" / "pre-push"
_PROBE = "repo_tests/sys_modules_leak_probe_18808_test.py"


def _hook() -> str:
    return _HOOK.read_text(encoding="utf-8")


def test_the_hook_audits_the_baseline_scoped_to_the_changed_files():
    text = _hook()

    assert 'detect-hardcoded-values.sh" --audit-baseline --paths-from=' in text


def test_the_hook_collects_the_selection_serially_before_the_leak_probe():
    """Serial, because under xdist the probe can land on a worker that never imported the stub."""
    text = _hook()
    line = next(row for row in text.splitlines() if "--collect-only" in row and "leak_probe" in row)

    assert "-p no:xdist" in line
    assert line.index("$leak_targets") < line.index('"$leak_probe"'), "the probe must be collected last"
    assert f'leak_probe="{_PROBE}"' in text
    assert (repo_root() / _PROBE).is_file()


def test_the_audit_gets_every_changed_path_not_only_baselined_ones(tmp_path):
    """#19312 review: a NEW file gaining a value has no baseline entry, so filtering the changed
    paths to baselined ones handed the scoped verdict nothing. Runs the hook's own block."""
    import subprocess  # noqa: PLC0415  # nosec B404

    text = _hook()
    block = text[text.index("  # ----- Hardcoded-values baseline (#18808)") : text.index("  # ----- Backend (Python)")]
    fake = tmp_path / "pipeline-scripts" / "detect-hardcoded-values.sh"
    fake.parent.mkdir(parents=True)
    fake.write_text(
        '#!/bin/bash\nfor a; do case "$a" in --paths-from=*) cp "${a#--paths-from=}" "$OUT";; esac; done\n',
        encoding="utf-8",
    )
    fake.chmod(0o755)
    (fake.parent / "hardcoded_values_baseline.txt").write_text("1|other|autobot-backend/old.py|x\n", encoding="utf-8")
    script = (
        "ok(){ :; }; fail(){ :; }\nEXIT_CODE=0\nREPO_ROOT=\"$1\"\nchanged=$'autobot-backend/old.py\\nautobot-backend/brand_new.py'\n"
        + block
    )
    out = tmp_path / "paths.txt"
    subprocess.run(
        ["bash", "-c", script, "_", str(tmp_path)],
        env={"OUT": str(out), "PATH": "/usr/bin:/bin"},
        check=True,
        timeout=30,
    )  # nosec B603

    assert out.read_text(encoding="utf-8").split() == ["autobot-backend/old.py", "autobot-backend/brand_new.py"]
