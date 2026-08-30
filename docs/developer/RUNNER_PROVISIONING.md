# Self-hosted runner provisioning

What a CI runner host needs beyond the GitHub runner agent itself, and why.

## Run this on each runner host

```bash
scripts/provision-runner-host.sh --check    # reports gaps, changes nothing
scripts/provision-runner-host.sh --apply    # installs what is missing
```

Idempotent — every step checks before acting. `--check` exits non-zero when something is missing, so it works as a gate.

Runner hosts are listed in [`scripts/runner-watchdog-inventory.yaml`](../../scripts/runner-watchdog-inventory.yaml), the SSOT for which runners exist.

## Why a runner needs Python installed at all

`actions/setup-python` resolves a version by downloading a build from `actions/python-versions`. That publisher ships builds for **LTS Ubuntu only** — 22.04, 24.04, 26.04. The runners are on 25.10, a non-LTS release, so there is nothing to fetch and the step fails outright (#15313):

```
##[error]The version '3.14' with architecture 'x64' was not found for Ubuntu 25.10.
```

GitHub-hosted runners never hit this: their images ship the tool cache pre-populated, so `setup-python` finds 3.14 locally and never downloads.

[#15314](https://github.com/mrveiss/AutoBot-AI/pull/15314) made `.github/actions/setup-python-ci` branch on `runner.environment` — on a self-hosted runner it uses the interpreter already on `PATH` instead of downloading. That turns an impossible download into a clear error, but it only succeeds once the interpreter is actually installed.

## Why a venv is not enough

`python3.14 -m venv` **requires python3.14 to already exist**. A venv is not an interpreter: it copies or symlinks one and writes a `pyvenv.cfg` naming it. Create it with 3.13 and you get a 3.13 environment.

So the order is always: install the interpreter, then build the venv. That is the same order the rest of the platform already uses — `install.sh:396-406` installs `python3.14` from deadsnakes, and the backend ansible role then runs `python3.14 -m venv`.

## Why deadsnakes rather than changing the runner OS

Moving the runners to an LTS release would also fix this, and fixes the whole class for every tool-cache-backed action (`setup-node`, `setup-go`, …). It is the broader fix and is tracked in #15313.

The deadsnakes PPA is the narrower one, and it is what the rest of the platform already uses. It publishes for non-LTS releases, so the runner OS does not have to change. Every other AutoBot host gets its Python this way.

## What "provisioned" means today

| Requirement | Why |
|---|---|
| `python3.14` on `PATH` | `setup-python-ci` resolves the **versioned binary by name**; a default `python3` that happens to be 3.14 does not satisfy it |
| `python3.14-venv` | separate package on Debian/Ubuntu, and it fails at *use* time rather than install time |
| `python3.14-dev` | headers, for packages that build native extensions |
| `pip` inside that interpreter | Debian/Ubuntu ship `python3.x` **without** pip. CI's first step after resolving Python is `python -m pip install --upgrade pip setuptools wheel`, so a host with the interpreter but no pip fails *after* passing the interpreter check — which reads as a new problem rather than an incomplete install. There is no `python3.14-pip` apt package; `python3.14 -m ensurepip --upgrade` is the supported route, and `ensurepip` ships in `python3.14-venv` |

| *(nothing — handled in-workflow)* | pip installs console scripts into the user script directory whenever site-packages is not writable, which is the normal case for a non-root runner user. Rather than editing the host, `setup-python-ci` asks the interpreter for `site --user-base` and appends `/bin` to `$GITHUB_PATH`. That is per-job and ephemeral, so **runners stay in their default GitHub configuration** — no `.path`, no `.env`, no unit edit |

### Why this one is hard to diagnose

A step that shells out to a missing binary often swallows the `command not found` — `enforce-precommit.yml` routes it into a warning branch and still reports success. The failure then surfaces in a *later* step as something unrelated:

```
line 17: pre-commit: command not found          <- the real cause, in a step that PASSED
check-precommit-hooks-executed: FATAL -- no hook result line in the captured output.
```

Read "no hook ran" as "the hook runner was not found", not as a hook problem.

This is now handled by the action rather than by host configuration, so it should not recur — but the diagnosis above is worth keeping, because the same swallowing pattern hides any missing binary.

Docker is deliberately **not** listed. Image builds stay on GitHub-hosted runners, where Docker and buildx ship preinstalled and hosted concurrency is worth more than runner locality (#15310).

## Verifying

After provisioning, confirm a job actually landed on a runner rather than falling back:

```bash
gh api repos/:owner/:repo/actions/jobs/<job-id> --jq '.runner_name'
```

A green check alone does not prove it ran self-hosted.
