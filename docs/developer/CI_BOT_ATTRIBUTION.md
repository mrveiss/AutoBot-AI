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

### Configuring the secret

A fine-grained personal access token scoped to this repository:

| Permission | Level |
|---|---|
| Contents | Read and write |
| Pull requests | Read and write |
| Workflows | Read and write (only if a pushed change touches `.github/workflows/`) |

Store it as the repository secret `AUTOBOT_PUSH_TOKEN`.

### Applies to

- `.github/workflows/auto-fix-formatting.yml`
- `.github/workflows/auto-fix-generated-types.yml`
- `.github/workflows/auto-update-pr-branches.yml`

## The safety net

`ci-dispatch-watchdog.yml` sweeps parked runs every 15 minutes and approves only
those whose head repository is this repository **and** whose triggering actor is
the bot — fork PRs are never approved, only reported.

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
