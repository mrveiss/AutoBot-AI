# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""A stale `workflow.ts` is caught by the required gate and the self-heal report (#16568).

`autobot-frontend/src/types/_generated/workflow.ts` is generated from Python sources by
`gen_frontend_types.py`. Its only guard used to be `frontend-codegen-drift`, which is not a
required context, so a backend enum change could merge with stale frontend types. The required
`verify-generated-types` check now regenerates it and diffs it, and the auto-fix report covers it.

Three claims, each with a control:

* the committed file is what the generator emits now, and a deliberately stale copy is NOT
  (the generator's own `--check` returns 1 on it and 0 on a fresh copy);
* the required workflow regenerates the file, diffs it, and its path filters fire for every
  source the generator reads;
* the auto-fix covers the same file (the pairing is also enforced generically by
  `auto_fix_generated_types_coverage_test.py`, which derives the set from the diff invocation).
"""

from __future__ import annotations

import importlib.util
import re
import sys

import pytest
import yaml
from repo_tests._paths import repo_root

_ROOT = repo_root()
_GEN = _ROOT / "autobot-infrastructure" / "shared" / "scripts" / "gen_frontend_types.py"
_WORKFLOW_TS = "autobot-frontend/src/types/_generated/workflow.ts"
# #18208: the body of the required `verify-generated-types` gate lives in _gate-generated-types.yml
# (called by ci.yml); its path filters live in .github/filters/gate-paths.yml.
_VERIFY = _ROOT / ".github" / "workflows" / "_gate-generated-types.yml"
_FILTERS = _ROOT / ".github" / "filters" / "gate-paths.yml"
_AUTOFIX = _ROOT / ".github" / "workflows" / "auto-fix-generated-types.yml"
_ACTION = _ROOT / ".github" / "actions" / "generated-types-autofix" / "action.yml"
_GEN_SCRIPT_REL = "autobot-infrastructure/shared/scripts/gen_frontend_types.py"
_REQUIRED_PATHS = ("autobot-frontend/src/types/_generated/**", _GEN_SCRIPT_REL)


def _load_generator():
    spec = importlib.util.spec_from_file_location("gen_frontend_types_16568", _GEN)
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def _run_check(module, monkeypatch, target, rendered: str) -> int:
    # Render once against the real tree; main() would re-render against the moved root.
    monkeypatch.setattr(module, "generate", lambda: rendered)
    # The drift message prints paths relative to the repo root, so the root and the script move
    # with the target; otherwise a file outside the checkout raises instead of reporting drift.
    monkeypatch.setattr(module, "REPO_ROOT", target.parent)
    monkeypatch.setattr(module, "__file__", str(target.parent / "scripts" / "gen_frontend_types.py"))
    monkeypatch.setattr(module, "OUTPUT_PATH", target)
    monkeypatch.setattr(sys, "argv", ["gen_frontend_types.py", "--check"])
    return module.main()


def _verify_doc() -> dict:
    return yaml.safe_load(_VERIFY.read_text(encoding="utf-8"))


def test_the_committed_workflow_ts_is_what_the_generator_emits(monkeypatch, tmp_path):
    """The live tree: a stale committed file fails here as well as in CI."""
    module = _load_generator()
    committed = (_ROOT / _WORKFLOW_TS).read_text(encoding="utf-8")
    assert module.generate() == committed, "workflow.ts is stale: run gen_frontend_types.py and commit it"


def test_the_check_distinguishes_a_stale_copy_from_a_fresh_one(monkeypatch, tmp_path, capsys):
    """Control: the detector says 0 on fresh input and 1 on a deliberately stale one."""
    module = _load_generator()
    rendered = module.generate()
    assert rendered, "an empty render would make fresh and stale indistinguishable"

    fresh = tmp_path / "fresh.ts"
    fresh.write_text(rendered, encoding="utf-8")
    assert _run_check(module, monkeypatch, fresh, rendered) == 0

    stale = tmp_path / "stale.ts"
    stale.write_text(rendered.replace("export", "export /* stale */", 1), encoding="utf-8")
    assert stale.read_text(encoding="utf-8") != rendered
    assert _run_check(module, monkeypatch, stale, rendered) == 1
    assert "DRIFT" in capsys.readouterr().err

    assert _run_check(module, monkeypatch, tmp_path / "missing.ts", rendered) == 1


def test_the_required_gate_regenerates_then_diffs_workflow_ts():
    steps = _verify_doc()["jobs"]["verify-types-run"]["steps"]
    regen = next(i for i, s in enumerate(steps) if _GEN_SCRIPT_REL in s.get("run", ""))
    diff = next(i for i, s in enumerate(steps) if f"git diff --exit-code {_WORKFLOW_TS}" in s.get("run", ""))
    assert regen < diff, "the diff must run after the regeneration it judges"
    dump = next(i for i, s in enumerate(steps) if "--dump-openapi" in s.get("run", ""))
    assert diff < dump, "workflow.ts must be judged before the whole-backend OpenAPI dump can mask it"


def test_no_new_required_context_was_added():
    """The decision: extend verify-generated-types, do not add a context."""
    names = {job.get("name", key) for key, job in _verify_doc()["jobs"].items()}
    assert names == {"verify-types-run", "verify-generated-types-slm"}


@pytest.mark.parametrize("path", _REQUIRED_PATHS)
def test_every_source_path_fires_the_required_gate(path):
    filters = yaml.safe_load(_FILTERS.read_text(encoding="utf-8"))
    assert path in filters["types"], f"the `types` filter lacks {path}"
    assert path not in filters["slm_types"], "workflow.ts has nothing to do with the SLM job"


def test_the_generators_python_sources_are_under_watched_trees():
    """Control for the filters: every source the manifest names is matched by a watched glob."""
    text = _GEN.read_text(encoding="utf-8")
    sources = set(re.findall(r'"((?:autobot_shared|autobot-backend)/[\w/.-]+\.py)"', text))
    assert len(sources) >= 5, "the scan found no manifest sources"
    filters = yaml.safe_load(_FILTERS.read_text(encoding="utf-8"))["types"]
    prefixes = {g.removesuffix("/**/*.py") for g in filters if g.endswith("/**/*.py")}
    unwatched = {s for s in sources if s.split("/")[0] not in prefixes}
    assert unwatched == set(), f"generator sources that cannot trigger the required gate: {unwatched}"


def test_the_autofix_regenerates_and_reports_workflow_ts():
    paths = yaml.safe_load(_AUTOFIX.read_text(encoding="utf-8"))[True]["pull_request"]["paths"]
    for path in _REQUIRED_PATHS:
        assert path in paths, f"auto-fix trigger paths lack {path}"
    steps = yaml.safe_load(_ACTION.read_text(encoding="utf-8"))["runs"]["steps"]
    regen = next(i for i, s in enumerate(steps) if _GEN_SCRIPT_REL in s.get("run", ""))
    report = next(i for i, s in enumerate(steps) if "GENERATED=" in s.get("run", ""))
    assert regen < report
    assert _WORKFLOW_TS in steps[report]["run"]


def test_the_autofix_adds_no_token():
    """Dev tokens only in dev workflows: this change adds no secret reference to the action."""
    assert "secrets." not in _ACTION.read_text(encoding="utf-8")
