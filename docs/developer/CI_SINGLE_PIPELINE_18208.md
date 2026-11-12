# One pull-request pipeline: job graph, required contexts, migration (#18208)

Audience: engineers changing CI, and the repository owner who maintains branch protection.

Before #18208 every gated workflow ran its own `Detect changed paths` job (13 rows on a docs-only PR)
and each required context was published by two same-named jobs: a real job and an "always-reporting
shim" in a second workflow. A reusable workflow runs once per calling workflow run and there is no
cross-workflow `needs:`, so the row count could only fall by merging the workflows. `ci.yml` is now the
one workflow that runs on a pull request, a merge group and a push to a base branch.

## Job graph

```
changes (Detect changed paths)           one job, one dorny/paths-filter step per .github/filters/ file
 |-- provision-packages -- python-shard x8 -- python-suite        gate
 |-- frontend-tests
 |-- run-code-quality            (_gate-code-quality.yml)    --  code-quality               gate
 |-- run-startup-import-smoke    (_gate-startup-import-smoke.yml) -- startup-import-smoke   gate
 |-- run-frontend-test           (_gate-frontend-test.yml)   --  Unit & Integration Tests   gate
 |-- run-docker-smoke            (_gate-docker-smoke.yml)    --  smoke-test                 gate
 |-- run-api-wiring              (_gate-api-wiring.yml)      --  api-wiring                 gate
 |-- run-migration-gate          (_gate-migration.yml)       --  migration-matrix           gate
 |-- run-generated-types         (_gate-generated-types.yml) --  verify-generated-types     gate
 |-- run-precommit               (_gate-precommit.yml)       --  verify-precommit-config    gate
 |-- run-security, run-codeql, run-ai-security-review, run-npm-package-tests, run-slm-frontend
 '-- deployment-check -- notify
```

* A **work job** (`run-<x>`) calls a reusable body `_gate-<x>.yml`, only when `changes` says the gate
  applies and the PR is not a draft (`changes.outputs.ready`).
* A **gate job** carries the required name, `needs: [changes, <work job>]` and `if: always()`, and
  computes its verdict with `.github/actions/gate-verdict`. Order of the verdict: detection failed ->
  fail; draft PR -> fail ("mark ready for review"; pre-commit is exempt, #17957); gate not affected ->
  pass; work job succeeded -> pass; otherwise fail. A cancelled upstream ends the gate `cancelled`
  (`cancel-run-on-cancelled-upstream`, #17764).
* A gate can never be `skipped`: `if: always()` is the whole point, and
  `repo_tests/required_context_complements_test.py` fails on a required context whose publisher can be
  skipped, is published twice, or is not draft-gated as designed.
* Path sets: `.github/filters/*.yml`, keys unique across the directory
  (`filter_keys_are_unique_18208_test.py`). Sets that used to be inline in a workflow, or a literal
  `on.pull_request.paths` list, live in `.github/filters/gate-paths.yml`. Its `self` key forces every
  gate when `ci.yml`, a `_gate-*.yml` body, the gate-verdict action or `gate-paths.yml` changes.
* Merge queue: `ci.yml` triggers on `merge_group`; every filter step takes the merge group's base sha, so
  the gates run on the queue's temporary ref (#14054, #18191).
* Schedules and manual runs of the moved gates: five thin callers, `scheduled-codeql.yml`,
  `scheduled-docker-smoke.yml`, `scheduled-migration-gate.yml`, `scheduled-precommit.yml` and
  `scheduled-security.yml`, call the same bodies.
* The two governance checks stay separate workflows: `no-commit-trailers.yml` and
  `pr-blocking-findings.yml`.
* Workflows that only run on `workflow_dispatch` or a schedule (for example
  `dispatch-preboard-guards.yml`, `dispatch-generated-types.yml`, `ci-dispatch-watchdog.yml`) are not part of
  this graph and are unchanged.

## Required contexts

Branch protection matches a required context by check-run **name**. A job in a called workflow reports as
`<caller job> / <called job>`, so each gate is a top-level job of `ci.yml` whose `name:` is exactly the
required string, and the bodies are reusable. The result: the set of required names does not change.

| Required context | Before: published by | After: published by |
|---|---|---|
| `python-suite` (pinned to the GitHub Actions app) | `ci.yml`, or `python-required-context.yml` when the suite does not apply | `ci.yml` job `python-suite` |
| `code-quality` | `code-quality.yml`, or `code-quality-required-context.yml` | `ci.yml` job `code-quality` |
| `startup-import-smoke` | `startup-import-smoke.yml`, or `backend-required-context.yml` | `ci.yml` job `startup-import-smoke` |
| `Unit & Integration Tests` | `frontend-test.yml`, or `frontend-required-context.yml` | `ci.yml` job `unit-tests` |
| `smoke-test` | `docker-smoke-test.yml`, or `docker-smoke-required-context.yml` | `ci.yml` job `smoke-test` |
| `api-wiring` | `api-wiring.yml` (two jobs, one per case) | `ci.yml` job `api-wiring` |
| `migration-matrix` | `migration-gate.yml` | `ci.yml` job `migration-matrix` |
| `verify-generated-types` | `verify-generated-types.yml` | `ci.yml` job `verify-generated-types` |
| `verify-precommit-config` | `enforce-precommit.yml` | `ci.yml` job `verify-precommit-config` |
| `No commit trailers` | `no-commit-trailers.yml` | unchanged |
| `No open blocks-merge issues reference this PR` | `pr-blocking-findings.yml` | unchanged |

`REQUIRED_CONTEXTS` in `required_context_complements_test.py` is a hand-kept copy of the list branch
protection holds (it cannot be read offline); a change to the protected set must change both.

## Check names that change (for landing tools and anything that reads check runs)

Unchanged: `python-suite shard N/8`, `provision-packages`, `frontend-tests`, `deployment-check`, `notify`,
`autofix-types` (own workflow), `Company OS workflow end-to-end`, `No commit trailers`, the 11 gate names above,
and `Detect changed paths` (bare, from `ci.yml`).

| Before (as shown on a pull request) | After |
|---|---|
| `Detect changed paths / Detect changed paths` (one per converted workflow, 8 on a typical PR) | removed: the one bare `Detect changed paths` remains |
| `Detect changed paths (<docker smoke / required context / python required context / ...>) / Detect changed paths`, `Detect changed packages / ...`, `Detect changed languages` | removed |
| `migration-tests` | `run-migration-gate / Migration Matrix Tests` |
| `verify-types-run` | `run-generated-types / verify-types-run` |
| `verify-generated-types-slm` | `run-generated-types / verify-generated-types-slm` |
| `Security Scan`, `Build Test`, `Test Summary` (frontend suite) | `run-frontend-test / Security Scan`, `run-frontend-test / Build Test`, `run-frontend-test / Test Summary` |
| `Dependency Security Scan`, `Static Application Security Testing (SAST)`, `Secret Detection (whole tree)`, `Security Compliance Check`, `Security Summary Report` | the same names prefixed `run-security / ` |
| `Analyze (<language>)` | `run-codeql / Analyze (<language>)` |
| `Security Review` (AI review) | `run-ai-security-review / Security Review` |
| `NPM Package Tests` | `run-npm-package-tests / NPM Package Tests` |
| `SLM Frontend Check` | `run-slm-frontend / SLM Frontend Check` |
| `Backend Startup Import Smoke` and `API Wiring Audit` work jobs | `run-startup-import-smoke / Backend Startup Import Smoke`, `run-api-wiring / API Wiring Audit` |
| `Code Quality Audit` work job | `run-code-quality / Code Quality Audit` |
| docker smoke work job | `run-docker-smoke / Docker Image Build and Compose Smoke` |
| `verify-precommit-config` and `check-instructions` (enforce-precommit.yml) | gate `verify-precommit-config`; work jobs `run-precommit / Pre-commit Configuration` and `run-precommit / check-instructions` |
| the five `*-required-context.yml` shim jobs | removed (their names were the same as the gates') |

A tool that waits for a work job by its old bare name (for example `migration-tests`) must wait for the
gate instead: the gate is always present and always concludes.

## Branch protection: migration order

No required-context name changes, so **no branch-protection edit is needed to land or to revert this
change**. The ordered list below is only what the owner would do to *tighten* afterwards; none of it
blocks the merge.

1. Before merging: nothing to add. The 11 contexts already exist and keep their names. Do not remove any.
2. Merge. Pull requests opened before the merge carry old check runs; re-push them (or re-run) so they
   report from the new `ci.yml`. A PR whose run started under the old workflows has no `run-*` rows.
3. After merge, once the first pull request and the first push to `main` have reported all 11 contexts
   from `ci.yml`: confirm `python-suite` is still published by the GitHub Actions app (the protection pins
   it) and that CodeQL alert ceilings re-key under `run-codeql / Analyze (<language>)`.
4. Optional, D6/D7 of #18208: move the required checks into the ruleset so the guard can compare against
   the live rule instead of the copy in `required_context_complements_test.py`; then replace that constant.

Revert: one `git revert -m 1 <merge commit>` restores the old workflows; the 11 names are identical either
way.

## Not proven by this document

Acceptance criterion 3 of #18208 (a docs-only PR and a Python-only PR show the same run/skip outcome per
gate as before, with a CI run on each) needs CI and two proof pull requests after the change lands. The
required-context behaviour on a real run and merge-queue behaviour are likewise unobserved until then.
