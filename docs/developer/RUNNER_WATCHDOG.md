# Runner Watchdog — Schedule and Inventory

`scripts/runner-watchdog.sh` detects the "ghost busy" condition on a
self-hosted GitHub Actions runner — the API reports `busy=true` but no
`Runner.Worker` process is actually running locally — and restarts the
runner's systemd service to clear it. It must run **on the host that hosts
the runner**: the restart it performs (`sudo systemctl restart <service>`)
is local, so scheduling it anywhere else cannot work (#15309).

## Runner host OS (#15313)

Both self-hosted runners (`Little-Slave`, `Second-Little-Slave`) were on
**Ubuntu 25.10** as of 2026-08-29 (#15313) -- a non-LTS release
`actions/python-versions` publishes no build for, which breaks any
self-hosted job using `actions/setup-python` for a version not already in
the runner's tool cache. Recorded here so the next "works hosted, fails
self-hosted" report starts from this fact instead of rediscovering it.
Re-confirm and update this line whenever the host OS changes:

```
ssh <runner-host> cat /etc/os-release   # or: gh api .../actions/runners, cross-reference host inventory
```

## Current inventory (SSOT)

`scripts/runner-watchdog-inventory.yaml` is the source of truth for which
runners are expected to have this watchdog scheduled, and is enforced in
`code-quality` by `tools/lint/check_runner_watchdog_schedule.py --audit`
(see that module's docstring for exactly what it checks and why). Keep it in
sync with:

```
gh api repos/mrveiss/AutoBot-AI/actions/runners
```

Bump each entry's `verified` date whenever you re-confirm it against that
command. The audit fails once any entry is older than the file's
`max_verified_age_days` — a forgotten re-check is a red required job, not a
doc nobody looks at again.

## Installing the watchdog on a runner host (host-side — not performed from this repo)

Run once per runner, **on that runner's own host**, logged in as the account
that runs the runner's systemd service:

```bash
# 1. Install the instantiated systemd unit + timer from this repo's checkout
#    on the host (adjust the source path to wherever AutoBot-AI is checked
#    out there; the templates assume ~/AutoBot-AI).
sudo cp scripts/systemd/runner-watchdog@.service /etc/systemd/system/
sudo cp scripts/systemd/runner-watchdog@.timer /etc/systemd/system/
sudo systemctl daemon-reload

# 2. Create a log directory this user can write (#15309 fault #1: /var/log
#    is root:syslog and not writable by the invoking user on these hosts).
mkdir -p ~/.local/state/runner-watchdog

# 3. Create the token file the unit's EnvironmentFile reads. GH_TOKEN needs
#    read access to this repo's Actions API; never commit this file.
mkdir -p ~/.config/runner-watchdog
umask 077
printf 'GH_TOKEN=%s\n' "<token>" > ~/.config/runner-watchdog/token.env
chmod 600 ~/.config/runner-watchdog/token.env

# 4. Grant passwordless restart of THIS host's own runner service only.
#    Fill in the two placeholders in the template, validate, then install
#    as a NEW file under /etc/sudoers.d/ — never edit /etc/sudoers directly.
sed -e "s/RUNNER_SERVICE_USER/$(whoami)/" \
    -e "s/RUNNER_SERVICE_NAME/actions.runner.mrveiss-AutoBot-AI.<runner-name>.service/" \
    scripts/systemd/runner-watchdog.sudoers.template > /tmp/runner-watchdog-sudoers
sudo visudo -cf /tmp/runner-watchdog-sudoers && \
  sudo install -m 0440 /tmp/runner-watchdog-sudoers /etc/sudoers.d/runner-watchdog-<runner-name>
rm -f /tmp/runner-watchdog-sudoers

# 5. Enable and start the instance for THIS host's runner name (must match
#    the `name` in scripts/runner-watchdog-inventory.yaml exactly).
sudo systemctl enable --now runner-watchdog@<runner-name>.timer

# 6. Verify -- the check the original entry silently failed for two months
#    (#15309): confirm the log FILE exists after the first scheduled run.
sudo systemctl start runner-watchdog@<runner-name>.service  # run once now
sleep 5
test -s ~/.local/state/runner-watchdog/<runner-name>.log && echo "watchdog log OK"
```

Repeat per runner host, substituting that host's own `<runner-name>` (from
the inventory) throughout.

### Removing a stale unit for a decommissioned runner

If a host previously ran a different runner (renamed or moved), remove any
leftover unit pointing at a missing `WorkingDirectory`:

```bash
sudo systemctl disable --now <stale-unit-name>
sudo rm -f /etc/systemd/system/<stale-unit-name>
sudo systemctl daemon-reload
```

## Adding, renaming or removing a runner

1. Update `gh api repos/mrveiss/AutoBot-AI/actions/runners` to confirm the
   current registered set.
2. Edit `scripts/runner-watchdog-inventory.yaml` — add/rename/remove the
   entry, matching `service` to
   `actions.runner.mrveiss-AutoBot-AI.<name>.service`, and set `verified` to
   today.
3. `python3 tools/lint/check_runner_watchdog_schedule.py --audit` locally
   before opening the PR.
4. Install (or remove) the systemd instance on that runner's own host per
   the steps above.
