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

That is the whole list. `setup-python-ci` builds a **venv** from that interpreter inside `RUNNER_TEMP` and puts it first on `PATH`, which means the host needs no pip of its own and no `PATH` edit:

- **PEP 668 does not apply.** Debian/Ubuntu mark system Python installs externally-managed, so `pip install` into system site-packages is refused. Installing into a venv is the route the error message itself recommends. This was observed as an *intermittent* failure: one runner refused, its sibling did not, because the two hosts had been provisioned differently — so a job passed or failed depending on which runner picked it up.
- **pip comes with the venv.** `python -m venv` runs `ensurepip` internally, so the venv has pip even when the system interpreter does not.
- **Console scripts land in `$VENV/bin`**, which is on `PATH` by construction — no user script directory to chase.
- **Nothing is installed outside `RUNNER_TEMP`.** Runners stay in their default GitHub configuration; the venv dies with the job.

### Why this one is hard to diagnose

A step that shells out to a missing binary often swallows the `command not found` — `enforce-precommit.yml` routes it into a warning branch and still reports success. The failure then surfaces in a *later* step as something unrelated:

```
line 17: pre-commit: command not found          <- the real cause, in a step that PASSED
check-precommit-hooks-executed: FATAL -- no hook result line in the captured output.
```

Read "no hook ran" as "the hook runner was not found", not as a hook problem.

This is now handled by the action rather than by host configuration, so it should not recur — but the diagnosis above is worth keeping, because the same swallowing pattern hides any missing binary.

**Node** is also not a host requirement. A pre-commit hook shells out to `node`, which hosted images ship and self-hosted runners do not — so `enforce-precommit.yml` runs `actions/setup-node` itself. That works where `setup-python` does not, because Node publishes generic `linux-x64` tarballs rather than per-distro builds, so a non-LTS runner OS is irrelevant to it.

The general rule this suggests: when a tool is missing on a runner, check whether its `setup-*` action distributes OS-agnostic binaries. If it does, add the action and leave the host alone.

Docker is deliberately **not** listed. Image builds stay on GitHub-hosted runners, where Docker and buildx ship preinstalled and hosted concurrency is worth more than runner locality (#15310).

## Verifying

After provisioning, confirm a job actually landed on a runner rather than falling back:

```bash
gh api repos/:owner/:repo/actions/jobs/<job-id> --jq '.runner_name'
```

A green check alone does not prove it ran self-hosted.
