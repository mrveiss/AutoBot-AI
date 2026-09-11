# Why CI runs park, and the token that stops it (#13791)

## Symptom

A pull request shows a handful of checks — often just `semgrep-cloud-platform/scan` —
and reads as green. It has not been tested: the rest of its workflow runs were
created with `conclusion=action_required` and never started.

Counting the checks is the tell. A PR with 50+ checks ran; a PR with 1 did not.

## Cause

The repository's fork-PR policy is `all_external_contributors`:

```
$ gh api repos/mrveiss/AutoBot-AI/actions/permissions/fork-pr-contributor-approval
{"approval_policy":"all_external_contributors"}
```

That policy is correct and should stay. This is a public repository that accepts
fork pull requests, and `pull_request` jobs run on a **self-hosted** runner —
so an unapproved fork run would execute contributor-supplied code on the owner's
machine.

The problem is that the policy also catches `github-actions[bot]`. Any workflow
that pushes with the default `GITHUB_TOKEN` attributes its commit to that bot,
and every run the push triggers is treated as external and parked:

```
issue-13590:  49 runs  actor=mrveiss              -> ran
              23 runs  actor=github-actions[bot]  -> all parked
```

The owner is never the problem. Their own pushes dispatch normally.

## Fix

Workflows that push prefer `AUTOBOT_PUSH_TOKEN`, falling back to `GITHUB_TOKEN`:

```yaml
token: ${{ secrets.AUTOBOT_PUSH_TOKEN || secrets.GITHUB_TOKEN }}
```

The fallback matters: without the secret configured the workflows behave exactly
as they do today rather than failing, so this change is safe to land before the
secret exists.

### The token is optional, and belongs to one repository

`AUTOBOT_PUSH_TOKEN` is a CI secret of whichever repository the workflows run
in. It is optional, and the AutoBot product never reads it. AutoBot is open
source and runs on anyone's infrastructure, so nothing in it may depend on this
repository's secrets (owner ruling, 11 Sep 2026). Leaving it unset is
supported: every workflow falls back to `GITHUB_TOKEN`, at the cost described in
"The release-sync PR without the token" below.

### Creating one, for this repository or a fork

A fine-grained personal access token, scoped to that one repository:

| Permission | Level |
|---|---|
| Contents | Read and write |
| Pull requests | Read and write |
| Workflows | Read and write |

Workflows is needed because the release-sync push carries changes under
`.github/workflows/`. Store the token as the repository secret
`AUTOBOT_PUSH_TOKEN`. A fork creates its own, or leaves it unset.

### Applies to

- `.github/workflows/auto-fix-generated-types.yml`
- `.github/workflows/auto-update-pr-branches.yml`
- `.github/workflows/sync-main-to-dev.yml` — pushes the `release-sync-main` branch
  and opens the release-sync PR from it (#16246).

## The release-sync PR without the token

Under the fallback, `sync-main-to-dev.yml` pushes `release-sync-main` and opens
its PR as `github-actions[bot]`, so every run those events trigger parks (see
Cause). The watchdog below releases them only once #16272 is live on `main`. It
runs `main`'s copy of `ci-dispatch-watchdog.yml`, and a copy without #16272
approves runs only for open PRs into `WATCHDOG_BASE_BRANCH` (`Dev_new_gui`).
Until then the sync PR's two required contexts, `No commit trailers` and `No
open blocks-merge issues reference this PR`, never report, and the PR cannot
merge.

**Owner step, for the bootstrap sync, and for every sync until #16272 is live on
`main`:** once the workflow has
opened or updated the sync PR, approve its parked runs
(`POST /repos/{owner}/{repo}/actions/runs/{id}/approve` per run, the endpoint the
watchdog uses), or close and reopen the PR as a person. `reopened` is a trigger
of both `no-commit-trailers.yml` and `pr-blocking-findings.yml`, the workflows
behind those two contexts.

The watchdog's schedule runs `main`'s copy, so #16272 takes effect only after the
first sync lands: the bootstrap sync always needs this step. From then on the
watchdog sweeps the release-sync PR along with its other heads, on the irregular
schedule described below.

## The safety net

`ci-dispatch-watchdog.yml` sweeps parked runs and approves only those whose head
repository is this repository **and** whose triggering actor is the bot — fork
PRs are never approved, only reported. It sweeps open PRs into `Dev_new_gui`,
plus the one open release-sync PR into `main` (head `release-sync-main`, from
this repository), and no other PR into `main` (#16272).

Its cron is `*/15`, but do not count on a release within minutes: measured on
11 Sep 2026, its scheduled runs fired every 1.5 to 4 hours (#16272).

That cron only fires from the **default branch**. The workflow must therefore
exist on `main`, not only on `Dev_new_gui`; until it does, the schedule never
runs and the sweep is limited to `push` and `pull_request` events:

```
$ gh api .../workflows/ci-dispatch-watchdog.yml/runs --jq '[.workflow_runs[].event]|group_by(.)|map({event:.[0],n:length})'
[{"event":"pull_request","n":73},{"event":"push","n":27}]     # schedule: 0
```

## What not to do

Do not relax the policy to `first_time_contributors` to make parking stop. It
would let a returning external contributor run code on the self-hosted runner
without approval — which is the exact exposure `all_external_contributors`
exists to prevent, and the repository has live fork pull requests today.
