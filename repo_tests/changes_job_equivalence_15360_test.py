# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""The reusable `changes` job is a zero-behaviour-change refactor (#15360).

Sixteen workflows each carried  their own `changes` job (checkout + dorny/paths-filter).
They now call `.github/workflows/_changes.yml`. "Zero change" is a claim about sixteen
things at once, so it is frozen as data: `fixtures/pre_15360_changes_jobs.json` was
generated from `origin/main` BEFORE the conversion (`python -m
repo_tests.changes_job_equivalence_15360_test` regenerates it from a git ref, for
provenance only). Each caller is resolved through `_changes.yml` (its inputs and their
defaults) into the same record and compared, field by field:

* the filter source -- a path plus the SHA-256 of that file, or the parsed inline dict;
* whether `base` is the merge group's base_sha, and whether the step is PR-only;
* checkout, timeout, runner, step ids and the pinned action refs;
* the `on:` block and the whole header, byte for byte;
* every non-`changes` job, byte for byte (so each `needs.changes.*` read is untouched).

An event matrix then evaluates the resolved record per event, so the answer is "same
base, same run or skip" rather than "same fields".

What this cannot prove: how GitHub evaluates the reusable call at run time. That is
only proven by CI running it.
"""

from __future__ import annotations

import hashlib
import json
import re
import subprocess
import sys
from pathlib import Path
from typing import Callable

import pytest
import yaml
from repo_tests._paths import repo_root

REPO = repo_root()
WORKFLOWS = ".github/workflows"
FIXTURE = Path(__file__).parent / "fixtures" / "pre_15360_changes_jobs.json"
REUSABLE_USES = f"./{WORKFLOWS}/_changes.yml"
CALLERS = (
    "api-wiring security startup-import-smoke backend-required-context code-quality "
    "code-quality-required-context frontend-test frontend-required-context python-required-context "
    "docker-smoke-required-context docker-smoke-test npm-package-tests slm-frontend-check "
    "verify-generated-types migration-gate ai-security-review"
).split()
#: The ONLY `on:` delta allowed: callers whose `paths:` list their own workflow file gained
#: `_changes.yml` beside it, because that is where their change-detection logic now lives.
#: workflow -> the events whose `paths:` carry the new entry. Pinned, not derived.
ON_ADDED_EVENTS = {
    "api-wiring": ("push",),
    "security": ("pull_request",),
    "startup-import-smoke": ("push",),
    "code-quality": ("push",),
    "frontend-test": ("push",),
    "npm-package-tests": ("push", "pull_request"),
    "slm-frontend-check": ("push", "pull_request"),
    "verify-generated-types": ("push",),
    "migration-gate": ("push",),
    "ai-security-review": ("pull_request",),
}
#: #17822 widens the Migration Gate on purpose: its filter listed where its tests live, not the code
#: they import, so #17772 changed `secrets_coordinator.py`, the gate skipped, and it merged green.
#: These eleven entries are the ONLY content change in this refactor, pinned by name. They land in the
#: caller's inline `migrations` filter AND its `on.push.paths` (the two lists must agree), and nowhere
#: else. Re-derived from commit 3006cacbb8 of the preserved branch `wip-17822-filter-guard`.
#: The pinned set lives in DATA, not in this module: `fixtures/issue_17822_migration_gate_entries.json`.
#: Two reasons. The glob-declaration census (#15900) reads every quoted glob in `repo_tests/*.py`
#: as a guard reading that tree, and these are workflow-filter values, not reads; and a second
#: copy in Python would be a second home for the eleven. The file is independent of the workflow
#: it asserts on, so deleting an entry from the workflow YAML still fails the pin; it is also
#: separate from `pre_15360_changes_jobs.json`, which `python -m` regenerates from a git ref and
#: would silently rewrite the expectation.
ISSUE_17822_ENTRIES = tuple(
    json.loads(
        (Path(__file__).parent / "fixtures" / "issue_17822_migration_gate_entries.json").read_text(encoding="utf-8")
    )
)
# 26 = the eleven #17822 entries plus `services/__init__.py`, `services/approval_gate_service.py` and
# `llc/services/workspace_lease.py` (#17996), `llc/services/company.py` + `company_ceo.py` (#15907's
# concurrent-move test), `llc/services/authz.py` + `membership_service.py` (the move's authorization,
# #19634), `llc/services/company_move_lock.py` (the move's row locks, #19593), `autobot_shared/db_errors.py`
# (its deadlock SQLSTATE) and `llc/scheduler/run_status.py` (#19582's concurrent-claim test), which the
# migration tests import, `llc/services/membership_policy.py` (#19985's two-session membership-lock test), and
# `llc/services/budget.py` + `llc/exceptions.py` (#20168's cost event foreign key test), and
# `llc/services/company_os/**` + `llc/services/goal.py` (#20115's two-session plan convert lock test).
assert (
    len(ISSUE_17822_ENTRIES) == 26
), "the pinned migration-gate set is 26 entries; an emptied fixture would pin nothing"
ISSUE_17822_WORKFLOW = "migration-gate"
EVENTS = ("push", "pull_request", "merge_group", "schedule", "workflow_dispatch")
MG_SHA = "merge-group-base-sha"  # a stand-in value; only its presence or absence is compared
PRE_BASE = "${{ github.event.merge_group.base_sha || '' }}"
POST_BASE = "${{ inputs.merge_group_base && github.event.merge_group.base_sha || '' }}"
POST_DORNY_IF = "${{ !inputs.pr_only || github.event_name == 'pull_request' }}"
PRE_PR_ONLY_IF = "github.event_name == 'pull_request'"
DORNY = "dorny/paths-filter@ceb8a2b8f2d89434be7ff52d3de7ec3738c5cc9d"
CHECKOUT = "actions/checkout@v7"
GITHUB_DEFAULT_TIMEOUT = 360

ReadFile = Callable[[str], bytes]


def _worktree_reader(rel: str) -> bytes:
    return (REPO / rel).read_bytes()


def _git_reader(ref: str) -> ReadFile:
    def read(rel: str) -> bytes:
        return subprocess.run(["git", "show", f"{ref}:{rel}"], cwd=REPO, capture_output=True, check=True).stdout

    return read


def digest(data: bytes) -> str:
    """SHA-256, hex, in dash-separated groups of eight.

    A bare 64-hex string in a committed fixture is what secret scanners are built to flag;
    these are content digests, not secrets, and the grouping keeps them out of that class
    without an allowlist entry. Equality is all they are used for.
    """
    hexed = hashlib.sha256(data).hexdigest()
    return "-".join(hexed[i : i + 8] for i in range(0, 64, 8))


def split_jobs(text: str) -> tuple[str, dict[str, str]]:
    """The header (everything before `jobs:`) and each job's raw text block."""
    head, sep, body = text.partition("\njobs:\n")
    assert sep, "no `jobs:` section"
    blocks: dict[str, str] = {}
    name = None
    for line in body.split("\n"):
        m = re.match(r"^  ([A-Za-z0-9_-]+):\s*$", line)
        if m:
            name = m.group(1)
            blocks[name] = ""
        if name is not None:
            blocks[name] += line + "\n"
    return head, {k: v.rstrip() for k, v in blocks.items()}


def filter_source(raw: str, read: ReadFile) -> dict:
    """dorny's own rule: no newline and no colon means a path, else inline YAML."""
    if "\n" in raw or ":" in raw:
        return {"inline": yaml.safe_load(raw)}
    data = read(raw.strip())
    return {"file": raw.strip(), "sha256": digest(data), "content": yaml.safe_load(data)}


#: The deliberate widenings, per filter file and key. `python_filter_covers_its_guards_test`
#: requires the python-suite filter to cover every file a guard reads, and these guards read
#: `_changes.yml`; so editing it now runs the suite. Nothing else about any path set moves.
ALLOWED_ADDITIONS = {
    #  + #17822: the migration-gate guard reads migration-gate.yml, so editing it must run the suite.
    ".github/filters/python-paths.yml": {
        "python": [
            f"{WORKFLOWS}/_changes.yml",
            f"{WORKFLOWS}/migration-gate.yml",
            f"{WORKFLOWS}/ai-security-review.yml",
            # #19503: install_and_code_sync_modes_19503_test reads this shell sync by concrete literal.
            "autobot-slm-frontend/scripts/sync-to-admin.sh",
            # #19503: its rsync guard exempts wiki.yml by concrete literal.
            f"{WORKFLOWS}/wiki.yml",
            # #20067: cancel_gate_survives_transient_error_20067_test runs this action's step.
            ".github/actions/cancel-run-on-cancelled-upstream/action.yml",
            # #19523: dependabot_root_coverage_19523_test reads dependabot.yml by concrete literal.
            ".github/dependabot.yml",
            # #19769: pr_conflict_gate_19769_test.py reads the conflict gate workflow.
            f"{WORKFLOWS}/pr-merge-conflict-gate.yml",
            # #17856: frontend_api_timeout_ssot_17856_test reads both .env.example files.
            ".env.example",
            "autobot-frontend/.env.example",
            # #18592: install_preflight_and_source_18581_test.py reads INSTALL.md; compose_slm_gui_profile_18585_test.py reads the root compose file and the frontend Dockerfile.
            "INSTALL.md",
            "docker-compose.yml",
            "docker/frontend/Dockerfile",
            # #19817: guards sweep every tracked Dockerfile, under either naming.
            "**/Dockerfile*",
            "**/*.Dockerfile",
            # #18556: one_static_data_copy_18556_test.py reads the canonical static data files.
            "autobot-backend/config/permission_rules.yaml",
            "autobot-backend/static/error_messages.yaml",
            "autobot-monitoring/prometheus.yml",
            "autobot-monitoring/grafana/provisioning/datasources/prometheus.yml",
            "autobot-backend/config/llm_models.yaml",
            "autobot-infrastructure/shared/config/permission_rules.yaml",
            "**/error_messages.yaml",
            "**/prometheus.yml",
            "**/permission_rules.yaml",
            "**/llm_models.yaml",
            # #18549: one_playwright_server_18549_test.py reads the canonical server and its store.
            "autobot-browser-worker/playwright-server.js",
            "autobot-browser-worker/session-store.js",
            # #18553: redis_direct_constructor_18553_test.py scans this installer for direct redis constructors.
            "autobot-backend/code_analysis/install.sh",
            # #15469: one_brand_mark_and_announcer_18240_test.py pins these icons to the kit mark.
            "autobot-frontend/public/favicon.ico",
            "autobot-frontend/public/favicon.svg",
            "autobot-slm-frontend/public/favicon.svg",
            # #18500: the autofix steps moved into a composite action with a dispatch-only caller; its guards read both.
            ".github/actions/generated-types-autofix/action.yml",
            f"{WORKFLOWS}/dispatch-generated-types.yml",
            # #18555: env_file_family_18555_test.py reads every tracked env file.
            "**/.env*",
            # #18555: root-level env files; `**/` alone does not match the root.
            ".env*",
            "autobot-slm-frontend/package.json",
            "**/*.env",
            # #18653: uninstall_covers_role_packages_18653_test.py reads .python-version.
            ".python-version",
            # #18729: docker_admin_seed_18729_test.py reads every Docker entrypoint.
            "docker/*/*entrypoint*.sh",
            # #17500: compose_exposure_and_credentials_17500_test.py checks every compose file.
            "docker-compose.hardened.yml",
            "docker-compose.override.example.yml",
            "docker/mcp-bridges.yml",
            # #18666: install_release_signed_18666_test.py compares release.yml's cosign pin with this one.
            f"{WORKFLOWS}/image-sign.yml",
            # #18666: the same test runs the signing-key gate against the real cosign.pub.
            "cosign.pub",
            # #17793: compose_exposure_and_credentials_17500_test.py checks that both smoke jobs export
            # exactly the credentials compose requires, so editing either workflow must run the suite.
            f"{WORKFLOWS}/docker-smoke-test.yml",
            f"{WORKFLOWS}/co-located-smoke.yml",
            # #17500, #18729: both guards read the secrets generator, so editing it must run the suite.
            "docker/generate-secrets.sh",
            "docker/postgres/init-databases.sh",
            # #19178: user_docs_stay_consistent_19178_test.py reads docs/README.md.
            "docs/README.md",
            # #18266: social_preview_18266_test.py pins the rendered preview image.
            "docs/assets/social-preview.png",
            # #19527: this test checks the docker filter's declared additions, so editing it must run the suite.
            ".github/filters/docker-paths.yml",
            # #19184: the same 19178 guard reads the five Company OS docs (_COMPANY_OS_DOCS).
            "docs/GLOSSARY.md",
            "docs/INDEX.md",
            "docs/architecture/PLATFORM_MODEL.md",
            "docs/features/CATALOG.md",
            "docs/llc/_index.md",
            # #19459: the disaster-recovery guard reads the runbook for the units it names.
            "docs/operations/disaster-recovery.md",
            # #19611: the playbook-reference guard reads this guide for its declared exemption.
            "docs/guides/slm-docker-ansible-deployment.md",
            # #19279: the landing-page guard reads the page for the libraries and placeholders it renders.
            "docs/index.html",
            # #18559: both duplication-guard tests read the pins file.
            ".github/duplication-pins.json",
            # #19324: browser_port_single_home_19324_test.py pins this file's browser-port fallback.
            "autobot-frontend/vite.config.js",
            # #19328: node_major_one_home_19328_test.py reads the Node home and the frontend lock.
            ".nvmrc",
            "autobot-frontend/package-lock.json",
        ]
    },
    # frontend_path_filter_mirror_test pins frontend-test.yml's on.push.paths to this file, so the
    # `_changes.yml` entry the workflow gained has to be here too.
    ".github/filters/frontend-paths.yml": {"frontend": [f"{WORKFLOWS}/_changes.yml"]},
    # #19527: the smoke job builds through this composite action and sizes its disk with the other,
    # so editing either one must run the smoke test it can break.
    ".github/filters/docker-paths.yml": {
        "docker": [".github/actions/build-smoke-images/**", ".github/actions/free-disk-space/**"]
    },
}


def without_allowed_additions(src: dict, name: str | None = None) -> dict:
    """`src` with the declared additions removed and, where any applied, the hash dropped."""
    if name == ISSUE_17822_WORKFLOW and "inline" in src:
        inline = {k: [e for e in v if e not in ISSUE_17822_ENTRIES] for k, v in src["inline"].items()}
        return {"inline": inline}
    extra = ALLOWED_ADDITIONS.get(src.get("file"))
    if not extra:
        return src
    content = {k: [e for e in v if e not in extra.get(k, [])] for k, v in src["content"].items()}
    return {"file": src["file"], "content": content}


ADDED_ENTRY = f"{WORKFLOWS}/_changes.yml"


def strip_added_on_entries(head: str, doc_on: dict, name: str | None) -> tuple[str, dict]:
    """The header text and parsed `on:` with the pinned `_changes.yml` additions removed.

    Asserts the additions are exactly where ON_ADDED_EVENTS says, and nowhere else.
    """
    events = ON_ADDED_EVENTS.get(name, ()) if name else ()
    extra = ISSUE_17822_ENTRIES if name == ISSUE_17822_WORKFLOW else ()
    lines = head.split("\n")
    quoted = {f"- '{e}'" for e in (ADDED_ENTRY, *extra)} | {f'- "{ADDED_ENTRY}"'}
    marked = [i for i, ln in enumerate(lines) if ln.strip() in quoted]
    assert len(marked) == len(events) + len(
        extra
    ), f"{name}: {len(marked)} added entries, pinned {len(events) + len(extra)}"
    kept = "\n".join(ln for i, ln in enumerate(lines) if i not in marked)
    parsed = {e: dict(v) if isinstance(v, dict) else v for e, v in doc_on.items()}
    for event in events:
        paths = list(parsed[event]["paths"])
        assert paths.count(ADDED_ENTRY) == 1, f"{name}: on.{event}.paths lacks the pinned entry"
        parsed[event]["paths"] = [p for p in paths if p != ADDED_ENTRY]
    for entry in extra:
        paths = list(parsed["push"]["paths"])
        assert paths.count(entry) == 1, f"{name}: on.push.paths lacks the pinned #17822 entry {entry}"
        parsed["push"]["paths"] = [p for p in paths if p != entry]
    return kept, parsed


def _common(text: str, doc: dict, read: ReadFile, name: str | None = None) -> dict:
    head, blocks = split_jobs(text)
    head, on_block = strip_added_on_entries(head, doc.get(True, doc.get("on")), name)
    others = {k: v for k, v in blocks.items() if k != "changes"}
    jobs = doc["jobs"]
    return {
        "header_sha256": digest(head.encode()),
        "on": on_block,
        "other_jobs_sha256": {k: digest(v.encode()) for k, v in others.items()},
        "other_jobs_if_needs": {k: [jobs[k].get("if"), jobs[k].get("needs")] for k in others},
        "consumed_outputs": sorted(set(re.findall(r"needs\.changes\.outputs\.(\w+)", text))),
        "display_name": jobs["changes"].get("name"),
        "job_level_extras": sorted(set(jobs["changes"]) - _JOB_KEYS),
    }


_JOB_KEYS = {"name", "runs-on", "timeout-minutes", "outputs", "steps", "uses", "with"}


def pre_record(text: str, read: ReadFile) -> dict:
    """The record of a `changes` job in its original, self-contained shape."""
    doc = yaml.safe_load(text)
    job = doc["jobs"]["changes"]
    steps = job["steps"]
    dorny = [s for s in steps if str(s.get("uses", "")).startswith("dorny/paths-filter@")]
    checkout = [s for s in steps if str(s.get("uses", "")).startswith("actions/checkout@")]
    assert len(dorny) == 1 and len(checkout) <= 1 and len(steps) == len(dorny) + len(checkout)
    with_ = dorny[0]["with"]
    assert set(with_) <= {"base", "filters"}, with_
    rec = _common(text, doc, read)
    rec.update(
        filters=filter_source(with_["filters"], read),
        base_is_merge_group=with_.get("base") == PRE_BASE,
        pr_only=dorny[0].get("if") == PRE_PR_ONLY_IF,
        checkout=bool(checkout),
        checkout_uses=checkout[0]["uses"] if checkout else None,
        dorny_uses=dorny[0]["uses"],
        step_id=dorny[0].get("id"),
        timeout=job.get("timeout-minutes", GITHUB_DEFAULT_TIMEOUT),
        runs_on=job["runs-on"],
        outputs=sorted(job["outputs"]),
        declared_outputs_read_from_step=all(
            v == "${{ steps.filter.outputs." + k + " }}" for k, v in job["outputs"].items()
        ),
    )
    assert with_.get("base", PRE_BASE) == PRE_BASE and dorny[0].get("if", PRE_PR_ONLY_IF) == PRE_PR_ONLY_IF
    return rec


def _input(reusable: dict, call_with: dict, name: str):
    spec = reusable[True if True in reusable else "on"]["workflow_call"]["inputs"][name]
    return call_with.get(name, spec.get("default"))


def post_record(text: str, reusable_text: str, read: ReadFile, name: str) -> dict:
    """The same record, resolved through the caller's `with:` and `_changes.yml`."""
    doc, reusable = yaml.safe_load(text), yaml.safe_load(reusable_text)
    job = doc["jobs"]["changes"]
    assert job.get("uses") == REUSABLE_USES, "the caller does not use the reusable job"
    call = job.get("with") or {}
    inner = reusable["jobs"]["changes"]
    co = [s for s in inner["steps"] if str(s.get("uses", "")).startswith("actions/checkout@")]
    dorny = [s for s in inner["steps"] if str(s.get("uses", "")).startswith("dorny/paths-filter@")]
    assert len(co) == 1 and len(dorny) == 1 and co[0]["if"] == "${{ inputs.checkout }}"
    assert dorny[0]["with"]["base"] == POST_BASE and dorny[0]["if"] == POST_DORNY_IF
    assert dorny[0]["with"]["filters"] == "${{ inputs.filters }}"
    assert inner["timeout-minutes"] == "${{ inputs.timeout_minutes }}"
    rec = _common(text, doc, read, name)
    rec.update(
        filters=filter_source(call["filters"], read),
        base_is_merge_group=bool(_input(reusable, call, "merge_group_base")),
        pr_only=bool(_input(reusable, call, "pr_only")),
        checkout=bool(_input(reusable, call, "checkout")),
        checkout_uses=co[0]["uses"],
        dorny_uses=dorny[0]["uses"],
        step_id=dorny[0].get("id"),
        timeout=_input(reusable, call, "timeout_minutes"),
        runs_on=inner["runs-on"],
        outputs=sorted(reusable[True if True in reusable else "on"]["workflow_call"]["outputs"]),
        declared_outputs_read_from_step=all(
            v == "${{ steps.filter.outputs." + k + " }}" for k, v in inner["outputs"].items()
        ),
    )
    assert set(call) <= {"filters", "merge_group_base", "pr_only", "checkout", "timeout_minutes"}, call
    return rec


def evaluate(rec: dict, event: str) -> dict:
    """What the dorny step receives and whether it runs, for one event."""
    base = MG_SHA if (rec["base_is_merge_group"] and event == "merge_group") else ""
    runs = (not rec["pr_only"]) or event == "pull_request"
    return {"base": base, "dorny_runs": runs, "checkout_runs": rec["checkout"]}


def _load_pre() -> dict:
    return json.loads(FIXTURE.read_text(encoding="utf-8"))


def _post(name: str) -> dict:
    text = (REPO / WORKFLOWS / f"{name}.yml").read_text(encoding="utf-8")
    reusable = (REPO / WORKFLOWS / "_changes.yml").read_text(encoding="utf-8")
    return post_record(text, reusable, _worktree_reader, name)


def _generate(ref: str) -> dict:
    read = _git_reader(ref)
    return {n: pre_record(read(f"{WORKFLOWS}/{n}.yml").decode(), read) for n in CALLERS}


_EQUAL_FIELDS = (
    "filters",
    "base_is_merge_group",
    "pr_only",
    "checkout",
    "checkout_uses",
    "dorny_uses",
    "step_id",
    "timeout",
    "runs_on",
    "display_name",
    "header_sha256",
    "on",
    "other_jobs_sha256",
    "other_jobs_if_needs",
    "consumed_outputs",
    "job_level_extras",
    "declared_outputs_read_from_step",
)


def test_the_fixture_covers_every_caller_and_is_not_vacuous():
    pre = _load_pre()
    assert sorted(pre) == sorted(CALLERS)
    assert any(r["base_is_merge_group"] for r in pre.values()), "no merge-group caller frozen"
    assert any(not r["base_is_merge_group"] for r in pre.values())
    assert [n for n, r in pre.items() if r["pr_only"]] == ["docker-smoke-test"]
    assert {r["timeout"] for r in pre.values()} == {10, GITHUB_DEFAULT_TIMEOUT}
    assert any("inline" in r["filters"] for r in pre.values()) and any("file" in r["filters"] for r in pre.values())
    assert all(r["other_jobs_sha256"] for r in pre.values()), "a caller with no other job freezes nothing"


@pytest.mark.parametrize("name", CALLERS)
@pytest.mark.parametrize("field", _EQUAL_FIELDS)
def test_each_resolved_field_equals_the_pre_conversion_value(name, field):
    post, pre = _post(name)[field], _load_pre()[name][field]
    if field == "filters":
        post, pre = without_allowed_additions(post, name), without_allowed_additions(pre, name)
    assert post == pre


def test_the_only_widenings_are_the_declared_entries_in_two_filter_files():
    """Every other filter file is byte-identical (hash); this one differs by exactly the entry."""
    widened = 0
    for name in CALLERS:
        pre, post = _load_pre()[name]["filters"], _post(name)["filters"]
        if pre.get("file") not in ALLOWED_ADDITIONS:
            assert pre.get("sha256") == post.get("sha256") or "inline" in pre
            continue
        widened += 1
        key = next(iter(ALLOWED_ADDITIONS[pre["file"]]))
        for entry in ALLOWED_ADDITIONS[pre["file"]][key]:
            assert entry not in pre["content"][key] and post["content"][key].count(entry) == 1
        assert len(post["content"][key]) == len(pre["content"][key]) + len(ALLOWED_ADDITIONS[pre["file"]][key])
    assert widened >= 2, "no caller reads the widened filter; the allowance is dead"


def test_the_only_inline_widening_is_the_pinned_17822_set_on_the_migration_gate():
    """The one inline filter that grew: exactly the pinned entries, in the `migrations` key, no other."""
    for name in CALLERS:
        pre, post = _load_pre()[name]["filters"], _post(name)["filters"]
        if "inline" not in pre:
            continue
        added = {k: [e for e in post["inline"][k] if e not in pre["inline"][k]] for k in post["inline"]}
        assert set(post["inline"]) == set(pre["inline"]), name
        if name == ISSUE_17822_WORKFLOW:
            assert added == {"migrations": list(ISSUE_17822_ENTRIES)}, added
            assert all(
                pre["inline"][k] == [e for e in post["inline"][k] if e not in ISSUE_17822_ENTRIES]
                for k in pre["inline"]
            )
        else:
            assert not any(added.values()), f"{name} widened outside the pinned #17822 set: {added}"


@pytest.mark.parametrize("name", CALLERS)
def test_the_reusable_job_still_provides_every_output_the_job_had(name):
    pre, post = _load_pre()[name], _post(name)
    assert set(pre["outputs"]) <= set(post["outputs"])
    assert set(post["consumed_outputs"]) <= set(pre["outputs"])


@pytest.mark.parametrize("name", CALLERS)
@pytest.mark.parametrize("event", EVENTS)
def test_the_event_matrix_gives_the_same_base_and_the_same_run_or_skip(name, event):
    assert evaluate(_post(name), event) == evaluate(_load_pre()[name], event)


def test_the_event_matrix_is_not_vacuous():
    pre = _load_pre()
    mg = [n for n, r in pre.items() if evaluate(r, "merge_group")["base"] == MG_SHA]
    assert mg and set(mg) < set(CALLERS), "the matrix must see both a base and no base on merge_group"
    assert not evaluate(pre["docker-smoke-test"], "push")["dorny_runs"]
    assert evaluate(pre["docker-smoke-test"], "pull_request")["dorny_runs"]
    assert all(evaluate(r, "push")["base"] == "" for r in pre.values())


def test_every_output_the_reusable_job_declares_reads_the_matching_step_output():
    inner = yaml.safe_load((REPO / WORKFLOWS / "_changes.yml").read_text(encoding="utf-8"))
    wf = inner[True if True in inner else "on"]["workflow_call"]["outputs"]
    for key, spec in wf.items():
        assert spec["value"] == "${{ jobs.changes.outputs." + key + " }}"
        assert inner["jobs"]["changes"]["outputs"][key] == "${{ steps.filter.outputs." + key + " }}"
    assert len(wf) == 15  # the union of every caller's outputs


def test_the_pinned_dorny_ref_carries_its_version_comment():
    text = (REPO / WORKFLOWS / "_changes.yml").read_text(encoding="utf-8")
    assert f"uses: {DORNY}  # v4.0.3" in text


if __name__ == "__main__":
    FIXTURE.write_text(
        json.dumps(_generate(sys.argv[1] if len(sys.argv) > 1 else "origin/main"), indent=1, sort_keys=True) + "\n",
        encoding="utf-8",
    )
