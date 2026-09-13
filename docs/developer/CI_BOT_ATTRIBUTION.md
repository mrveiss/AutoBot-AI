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
supported: every workflow falls back to `GITHUB_TOKEN`. What that means for the
release sync is in "The release sync in this repository: by hand" below.

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
- `.github/workflows/sync-main-to-release.yml` — pushes the `release-sync-release` branch
  and opens the release-sync PR from it, or, where GitHub refuses the PR, keeps
  the tracking issue described below (#16246).

## The release sync in this repository: by hand

The owner ruled that this repository syncs `release` by hand (#15834 Q2). It has no
`AUTOBOT_PUSH_TOKEN`, and "Allow GitHub Actions to create and approve pull
requests" stays off. Measured 11 Sep 2026: `actions/permissions/workflow` returns
`default_workflow_permissions: read` and `can_approve_pull_request_reviews:
false`, and the repository holds no Actions secrets.

So `sync-main-to-release.yml` pushes `release-sync-release` but can never open the sync
PR. When GitHub refuses it, the workflow keeps ONE tracking issue instead, titled
`release: release is behind main — open the sync PR by hand` and labelled
`automation`. The issue carries the PR body (the commit count, the scheduled
workflows the sync activates, changes or stops, and the merge-commit
instruction), the compare link, and the one command that opens the PR. Each run
updates it in place, and closes it once a sync PR is open or `release` has nothing
left to sync. If the issue cannot be written the run fails, so a green run means
the PR or the issue is current. The job declares `issues: write` because the
default token here is read-only.

**Owner step, every sync:** open the PR from the issue's link or command, then
merge it with a merge commit, as its body says. A PR a person opens starts its
checks normally, so nothing parks.

The watchdog's release of the sync PR's parked runs (#16272) therefore does not
come into play here. It matters only if the workflow ever opens the PR as the
bot, which needs "Allow GitHub Actions to create and approve pull requests"
turned on with no push token set. A push token opens the PR as the token's
owner, whose runs do not park.

## The safety net

`ci-dispatch-watchdog.yml` sweeps parked runs and approves only those whose head
repository is this repository **and** whose triggering actor is the bot — fork
PRs are never approved, only reported. It sweeps open PRs into `main`,
plus the one open release-sync PR into `release` (head `release-sync-release`, from
this repository), and no other PR into `release` (#16272).

Its cron is `*/15`, but do not count on a release within minutes: measured on
11 Sep 2026, its scheduled runs fired every 1.5 to 4 hours (#16272).

That cron only fires from the **default branch**. The workflow must therefore
exist on `main`, not only on `release`; until it does, the schedule never
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
