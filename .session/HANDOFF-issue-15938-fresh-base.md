# Handoff: issue-15938-fresh-base
status: complete
pr: #16128
base_at_push: eed91b358
gates: pre-commit=PASS on every commit | pre-push=PASS through 71b7bfeaf; it did not block 90d6a4902, but its test selection for that push was not observed | CI at 90d6a4902: 0 failures, 22 running at handoff | wiring/duplication: run by CI (api-wiring, duplication-guard), not run separately
needs_rebase_before_merge: no
remaining:
  - Merge #16128 once all 10 required contexts are green AND the delta at 90d6a4902 (git calls moved to run_git) has been re-reviewed. The earlier review cleared the branch before that commit.
  - Then close #15938 with per-criterion evidence from base. AC4 ("no PR-less pushed branch more than 50 behind") stays UNTICKED. It was measured at 206 of 258 over when filed. No diff can satisfy it; only the fixed cron can.
  - Then unlock and remove this worktree (it is locked on purpose) and delete the branch. `rescue-15938-parked-branch-merger` becomes disposable once #16128's content is verified on base. That branch was not created by this session.
  - Follow-up PR, not started: move `_logical_lines` from `repo_tests/git_merge_rejects_pull_only_flags_15938_test.py` into `tools/lint/_scan_helpers.py` and use it from `repo_tests/hooks_path_override_15961_test.py` as well. That closes the continuation escape recorded on #15961: on base, `git config \` followed by `core.hooksPath <v>` on the next line is not caught. The same PR should split `scan_shell`, which is 39 code lines against a documented limit of 30. `tools/lint/check_git_toplevel_env_scrubbed.py` is at its 600-line ceiling, so the split must not grow the file.
  - Tests not written: the success arm of `_fetched_base_ref` (remote present and ref resolvable) and its `subprocess.TimeoutExpired` branch.
worktree: .worktrees/issue-15938-envfix  (safe to remove after merge; locked, unlock first)

done:
  - The parked-branch merger had never merged anything. `git merge --no-rebase` passes a flag that only `git pull` accepts, so every merge died during argument parsing and the else-arm filed it as CONFLICTS. Fixed. A non-conflict failure now has its own bucket and exits 1. Branches that could not be attempted go to `unreachable`, which counts toward `considered`, so "did not try" no longer reads as "nothing to do".
  - New task workspaces branch from a freshly fetched `AUTOBOT_WORKSPACE_BASE_REF` via `run_git`, with a strict environment and a 30s timeout. A repository with no remotes returns None. A failing `git remote` raises. A missing ref with a configured remote raises.
  - `pr-preflight.sh` gains a behind-base gate at `PREFLIGHT_MAX_BEHIND` and rejects a non-numeric limit instead of printing ok.
  - A guard refuses pull-only flags passed to `git merge` repo-wide, with shell continuations folded before matching.

notes:
  - Open in this lane: #15961 (runtime-detection half plus the continuation gap), #15938, #16079, #16109, #16214, #16218, #15756.
  - `statusCheckRollup` keeps runs from superseded head SHAs, so a clean head can read as failing. Read `commits/<head>/check-runs` and take the latest run per name.
  - `function_length_checker.py` counts code lines only and skips test files, so none of the `repo_tests` guards are ever measured.
