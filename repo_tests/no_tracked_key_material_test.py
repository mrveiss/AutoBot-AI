# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""No tracked file may hold raw key material, whatever it is named (#16275).

``.infra_encryption_key`` -- an auto-generated Fernet key, 44 characters, no
extension, at the repository root -- was tracked in this public repository from
October 2025 until #16275, although ``.gitignore`` listed it. Three gaps let it
through, and the assertions below close one each:

* **The CI step never read the root.** It grepped three shapes inside three
  directories. The ``secret-detection`` job in ``security.yml`` now scans every
  tracked file on every event, ungated by any path filter.
* **The scanner that should have run never did.** ``.secrets.baseline`` sat in
  the tree with no hook and no workflow behind it. The detect-secrets hook is
  now wired to that baseline, over every staged file, and every baseline entry
  must carry an audited verdict.
* **Even wired, detect-secrets misses this shape.** Measured with 1.5.0 before
  the file was untracked: zero findings for it, because its high-entropy
  plugins read quoted strings and a bare key file has none. So the shape is
  checked by ``pipeline-scripts/tracked_key_material.py`` -- the same script
  the CI job runs, loaded here so the guard and the gate share one predicate --
  against a planted key in an extensionless dotfile, the committed file's own
  shape.

Planted keys come from ``os.urandom`` at test time and exist only under
``tmp_path``. No key, real or fake, is written into this repository.
"""

from __future__ import annotations

import base64
import functools
import importlib.util
import json
import os
import re
import string
import subprocess
import sys
from pathlib import Path
from types import ModuleType

import yaml
from repo_tests._paths import repo_root
from repo_tests._reach import declare

from autobot_shared.paths import scrubbed_git_env
from tools.lint._scan_helpers import EmptyEnumeration, tracked_paths

_REPO_ROOT = repo_root()
_DETECTOR = _REPO_ROOT / "pipeline-scripts" / "tracked_key_material.py"
_PRE_COMMIT = _REPO_ROOT / ".pre-commit-config.yaml"
_BASELINE = _REPO_ROOT / ".secrets.baseline"
_SECURITY_WORKFLOW = _REPO_ROOT / ".github" / "workflows" / "security.yml"
_COMMITTED_KEY = ".infra_encryption_key"
_HOOK_REPO_URL = "https://github.com/Yelp/detect-secrets"
_RELEASE_TAG = re.compile(r"^v?(\d+\.\d+\.\d+)$")
_URLSAFE_ALPHABET = (string.ascii_uppercase + string.ascii_lowercase + string.digits + "-_").encode()


def _tracked(root: Path) -> list[str]:
    """Every tracked path, any extension; ``[]`` on an empty tree so the floor refuses it."""
    try:
        return tracked_paths(root)
    except EmptyEnumeration:
        # Relocates the refusal rather than weakening it: REACH's floor then
        # raises ReachFloorError, the typed refusal reach_declarations_test
        # expects (see excluded_tree_size_debt_test).
        return []


#: 10,075 tracked files were measured when #16275 landed; the floor sits 75 below.
#: `growth` is how far the population may grow before reach_declarations_test
#: asks for the floor to be raised -- a maintenance interval chosen by judgement,
#: not measured. No `skips`: the tree held no symlink or gitlink when measured,
#: so every listed path is a file the sweep reads.
REACH = declare(
    "tracked-key-material",
    discover=_tracked,
    floor=10_000,
    growth=800,
    what="tracked files of any extension",
)


@functools.lru_cache(maxsize=1)
def _detector() -> ModuleType:
    """The CI script itself, loaded by path and registered before it executes.

    Registration first, because its dataclass resolves its own annotations
    through ``sys.modules``.
    """
    name = "_tracked_key_material_16275"
    spec = importlib.util.spec_from_file_location(name, _DETECTOR)
    assert spec is not None and spec.loader is not None, f"cannot load {_DETECTOR}"
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


def _planted_fernet_key() -> bytes:
    """A key-shaped token from ``os.urandom``, fresh each run. Never a real key.

    Redrawn in the ~4e-10 case where it lacks upper or lower case: the detector
    deliberately reads a single-case run as an identifier.
    """
    while True:
        token = base64.urlsafe_b64encode(os.urandom(32))
        if re.search(rb"[a-z]", token) and re.search(rb"[A-Z]", token):
            return token


def _pem_header() -> bytes:
    """Assembled at run time, so this file does not itself hold the header it plants."""
    return " ".join(["-----BEGIN", "EC", "PRIVATE", "KEY-----"]).encode()


def _plant(root: Path, files: dict[str, bytes]) -> tuple[list, list[str]]:
    for name, body in files.items():
        (root / name).write_bytes(body)
    return _detector().scan_paths(root, sorted(files))


def test_no_tracked_file_holds_key_material() -> None:
    """The sweep the CI gate runs, over every tracked file of any extension."""
    detector = _detector()
    findings, read = detector.scan_paths(_REPO_ROOT, REACH.examined(_REPO_ROOT))
    REACH.completed(read)
    problems = detector.exemption_problems(findings, read)
    assert not problems, "raw key material is tracked (values withheld):\n" + "\n".join(problems)


def test_the_committed_key_stays_untracked_and_ignored() -> None:
    """#16275's own file: out of the index, and still matched by ``.gitignore``."""
    assert _COMMITTED_KEY not in set(REACH.examined(_REPO_ROOT)), f"{_COMMITTED_KEY} is tracked again"
    ignored = subprocess.run(
        ["git", "check-ignore", "--quiet", "--no-index", _COMMITTED_KEY],
        cwd=_REPO_ROOT,
        env=scrubbed_git_env(),
        check=False,
    )
    assert ignored.returncode == 0, f"{_COMMITTED_KEY} is not ignored (git check-ignore exit {ignored.returncode})"


def test_a_planted_key_in_an_extensionless_dotfile_is_flagged(tmp_path: Path) -> None:
    """The known positive: the committed file's own shape -- bare, newline-ended and assigned."""
    token = _planted_fernet_key()
    planted = {".planted_key": token, ".planted_key_nl": token + b"\n", ".env.planted": b'KEY="' + token + b'"\n'}
    findings, read = _plant(tmp_path, planted)
    assert read == sorted(planted), "the planted files were not all read"
    assert {(f.path, f.kind) for f in findings} == {(name, _detector().FERNET) for name in planted}
    assert all(token.decode() not in f.render() for f in findings), "a finding must never carry the value"


def test_non_decoding_lookalikes_are_not_flagged(tmp_path: Path) -> None:
    """Shapes that resemble a key but are not what ``Fernet.generate_key()`` emits."""
    real = _planted_fernet_key()
    flipped = _URLSAFE_ALPHABET.index(real[42]) ^ 1
    lookalikes = {
        # 44 characters with no padding: decodes to 33 bytes, not 32.
        ".unpadded": base64.urlsafe_b64encode(os.urandom(33)),
        # The last data character carries stray low bits: no encoder emits it.
        ".non_canonical": real[:42] + _URLSAFE_ALPHABET[flipped : flipped + 1] + b"=",
        # A 43-character single-case NAME and '=': decodes cleanly, but is an identifier.
        ".env.identifier": b"AUTOBOT_" + b"X" * 34 + b"E=\n",
    }
    findings, read = _plant(tmp_path, lookalikes)
    assert read == sorted(lookalikes), "the look-alikes were not all read, so their absence proves nothing"
    assert not findings, [f.render() for f in findings]


def test_a_planted_pem_private_key_header_is_flagged(tmp_path: Path) -> None:
    """Any algorithm, in a file of any name."""
    findings, _read = _plant(tmp_path, {".deploy_identity": _pem_header() + b"\n"})
    assert [(f.path, f.kind) for f in findings] == [(".deploy_identity", _detector().PEM)]


def _detect_secrets_entry() -> tuple[str, dict]:
    config = yaml.safe_load(_PRE_COMMIT.read_text(encoding="utf-8"))
    repos = [r for r in config["repos"] if r.get("repo") == _HOOK_REPO_URL]
    assert len(repos) == 1, f"expected one {_HOOK_REPO_URL} entry in .pre-commit-config.yaml"
    hooks = [h for h in repos[0]["hooks"] if h.get("id") == "detect-secrets"]
    assert len(hooks) == 1, "the detect-secrets hook is not configured"
    return repos[0]["rev"], hooks[0]


def test_the_detect_secrets_hook_scans_every_staged_file_against_the_baseline() -> None:
    rev, hook = _detect_secrets_entry()
    assert _RELEASE_TAG.match(rev), f"detect-secrets rev {rev!r} is not a pinned release"
    assert hook.get("args") == ["--baseline", ".secrets.baseline"], hook.get("args")
    narrowing = sorted(set(hook) & {"files", "exclude", "types", "types_or", "exclude_types", "stages"})
    assert not narrowing, f"the hook is narrowed by {narrowing}; it must see every staged file"


def test_the_top_level_exclude_hides_no_tracked_file() -> None:
    """The one filter the hook still inherits must not hide a tracked file from it."""
    pattern = re.compile(yaml.safe_load(_PRE_COMMIT.read_text(encoding="utf-8")).get("exclude", "^$"))
    hidden = [path for path in REACH.examined(_REPO_ROOT) if pattern.search(path)]
    assert not hidden, f"{len(hidden)} tracked file(s) sit under the top-level exclude: {hidden[:10]}"


def test_the_scanner_is_one_version_everywhere() -> None:
    """A baseline written by one detect-secrets version is not an audit of another's findings."""
    rev, _hook = _detect_secrets_entry()
    baseline_version = json.loads(_BASELINE.read_text(encoding="utf-8"))["version"]
    ci_pins = re.findall(r"detect-secrets==(\d+\.\d+\.\d+)", _SECURITY_WORKFLOW.read_text(encoding="utf-8"))
    assert ci_pins, "security.yml no longer installs a pinned detect-secrets"
    release = _RELEASE_TAG.match(rev)
    hook_version = release.group(1) if release else rev
    assert {hook_version, *ci_pins} == {baseline_version}, (hook_version, ci_pins, baseline_version)


def test_every_baseline_entry_carries_a_not_a_secret_verdict() -> None:
    """Nothing is parked in the baseline unaudited, and nothing real is parked there at all."""
    results = json.loads(_BASELINE.read_text(encoding="utf-8"))["results"]
    assert results, "the baseline holds no results -- an empty baseline audits nothing"
    unaudited = [
        f"{path}:{entry['line_number']}: {entry['type']} (is_secret={entry.get('is_secret', 'unaudited')})"
        for path, entries in results.items()
        for entry in entries
        if entry.get("is_secret") is not False
    ]
    assert not unaudited, "baseline entries without a not-a-secret verdict:\n" + "\n".join(unaudited)


def test_ci_scans_every_tracked_file_on_every_event() -> None:
    """Ungated: a path filter keyed on file types would skip an extensionless dotfile."""
    job = yaml.safe_load(_SECURITY_WORKFLOW.read_text(encoding="utf-8"))["jobs"].get("secret-detection")
    assert job is not None, "security.yml has no secret-detection job"
    assert "needs" not in job and "if" not in job, "secret-detection must run on every event, ungated"
    runs = "\n".join(step.get("run", "") for step in job["steps"])
    assert "git ls-files -z | python3 pipeline-scripts/tracked_key_material.py" in runs
    assert "detect-secrets scan --baseline .secrets.baseline" in runs
