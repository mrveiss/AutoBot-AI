# Fleet and panel management patterns — nine sources against the SLM layer

Research artifact, 2026-09-08. Sources named freely (maintainer's call: none of these compete with
AutoBot). Companion to `host-management-console-patterns.md`, which covered Cockpit,
Webmin/Virtualmin and oVirt.

**Not an OS question.** Nothing here is about targeting or resembling a platform. These are
control-plane *methods*: how a manager declares what it manages, gates what enters service, proves
a backup is real, distinguishes drift from intent, and rolls back.

| Source | Category | What it was read for |
|---|---|---|
| Proxmox VE | virtualization | `pmxcfs` replicated config, path-templated ACLs, privilege-separated API tokens |
| MAAS | bare-metal provisioning | machine life-cycle as a state machine; commissioning scripts as quality gates |
| Foreman / Katello | fleet content | content views — pinned, promotable repository snapshots |
| Xen Orchestra (XCP-ng) | virtualization | backup **health checks** — restore-and-boot verification |
| ISPConfig | hosting panel | master + slave agents draining a replicated change log |
| cPanel / WHM | hosting panel | API token model (read narrowly) |
| Salt | config management | beacons + reactor — agent-side condition watchers on an event bus |
| Puppet | config management | corrective vs intentional change reporting |
| NixOS | OS/config | generations and atomic rollback |

---

## Phase 1 — what each one does

### Proxmox VE — config as a quorum-gated filesystem, permissions as paths

**pmxcfs.** A FUSE filesystem mounted at `/etc/pve`, backed by SQLite
(`/var/lib/pve-cluster/config.db`, mode 0600) and replicated in real time across the cluster by
Corosync. It keeps a RAM copy, capped at 128 MiB, which is enough for several thousand guests.

The decisive property: **when a node loses quorum, the filesystem goes read-only.** A partitioned
node cannot write config at all — split-brain is prevented by the storage layer refusing writes,
not by application code remembering to check.

It also drops POSIX features on purpose: no symlinks, and non-empty directories cannot be renamed,
which is how uniqueness of guest IDs is enforced *structurally*. Layout separates
`/etc/pve/nodes/<name>/` (per-node), cluster-wide files (`datacenter.cfg`, `storage.cfg`,
`user.cfg`), `/etc/pve/ha/` and `/etc/pve/priv/` (root only).

**Permissions.** ACLs are `(path, identity, role)` triples over a filesystem-like namespace:
`/nodes/{node}`, `/vms/{vmid}`, `/storage/{id}`, `/pool/{name}`, `/access/realms/{id}`. Paths are
**templated** — parameters of the API call, in braces, determine which path the permission check
runs against, so authorization is derived from the request rather than hand-written per endpoint.
Permissions propagate down by default; user grants override group grants; `NoAccess` on a path
beats everything else.

**API tokens.** Privilege separation is **on by default**: a token carries its own ACLs and its
effective permission is the *intersection* of the user's and the token's. Tokens expire and are
revocable independently of the account. A "full privileges" mode exists but is opt-in.

### MAAS — a machine is not usable until it has proved it is

Life-cycle: **New → Commissioning → Ready → Deployed → Released**, with **Failed** as the terminus
of a failed commissioning or hardware test.

Commissioning is the interesting state. The machine boots an ephemeral image, runs hardware probes
(CPU, RAM, storage, network), applies baseline configuration, and runs hardware tests. Only on
success does it reach **Ready** — and only then does MAAS have the complete inventory it needs to
schedule work onto it. Operators can upload **custom commissioning and testing scripts**, which run
alongside the built-ins and act as quality gates: a machine that fails one never becomes schedulable.

The principle: *entering service is a state a machine earns by passing checks, not a state it
occupies by existing.*

### Foreman / Katello — content views: a frozen, promotable package set

A **content view** is a snapshot of one or more repositories, with filters that include or exclude
specific packages, package groups or errata. **Publishing** a content view clones the content,
applies the filters, and produces a **content view version** — a frozen snapshot that later changes
to the underlying repositories cannot alter. A **composite content view** is a content view of
content views.

Versions are then **promoted** through lifecycle environments (Dev → Test → Production). Hosts
consume the version promoted to their environment, so upstream repositories can keep moving while
hosts stay on a known set until someone promotes.

### Xen Orchestra — a backup is not healthy until it has been restored and booted

Backup jobs support a **health check**: after the run, XO *actually restores the backup* — by
downloading it for a delta/full backup or cloning it for a replication — **starts it**, and waits
for guest tools to load within a ten-minute timeout. Only then is the backup marked healthy. The
restored guest is deleted afterwards. A guest without guest tools fails the check.

For workloads whose health is not "guest tools appeared", a VM tagged
`xo-backup-health-check-xenstore` makes XO wait instead for a script inside the guest to write
`success` or `failure` to a xenstore key — a **custom liveness predicate** supplied by the thing
being verified.

Delta backups restore from a chain (full + deltas), so XO advises either short chains via a full
backup interval, or health checks to prove the chain still resolves.

### ISPConfig — a replicated change log drained by per-server agents

A master holds the interface and the database; slave servers run web, mail and DNS. Every
configuration change is written to a **`sys_datalog`** table. Each slave runs `server.php` on a
cron, which selects datalog rows with `datalog_id` greater than the last one it processed, filtered
by its own `server_id` (with `server_id = 0` meaning "all servers") or `mirror_server_id`, and
dispatches each row to module functions hooked on that table's actions.

So the master never pushes: it *records intent*, and each agent pulls the slice addressed to it and
applies it locally. Known failure modes are the honest part — the datalog is not pruned by default
and bloats, and a slave stuck at an old `datalog_id` falls behind in a way that surfaces as
replication errors rather than as an obvious "this node is behind" signal.

### cPanel / WHM — read narrowly, and the least to learn from

API tokens are created from the UI or via `Tokens::create_full_access`, and authenticate with an
`Authorization: cpanel username:TOKEN` header. The published documentation covers creation and
header format; it does not document scope restriction, per-IP limits, or expiry semantics, and the
canonical creation function is named for full access. Compared against Proxmox's intersection model
this is the weaker design, and it is included here mainly to mark that the hosting-panel category
has little to offer beyond what Virtualmin already gave us.

### Salt — beacons put the watcher on the agent, the decision on the master

**Beacons** run on the minion and watch non-Salt system state — file changes (inotify), load,
service status, logins, disk and network usage. When the watched condition fires, the beacon emits
an event onto Salt's event bus with a structured tag:

    salt/beacon/{minion_id}/{beacon_type}/{watched_resource}

Configuration is declarative, per beacon, with a check `interval` (default one second):

    beacons:
      inotify:
        - files:
            /etc/important_file:
              mask: [modify]
        - interval: 5
        - disable_during_state_run: True

The **reactor** on the master subscribes by tag glob and runs an SLS in response — typically
`state.apply` to remediate:

    reactor:
      - 'salt/beacon/*/inotify//etc/important_file':
        - /srv/reactor/revert.sls

The detail worth stealing is `disable_during_state_run`. A reactor that remediates the file its
beacon watches will re-trigger itself forever; the framework ships the loop-breaker as a first-class
option rather than leaving each author to discover the feedback loop.

### Puppet — the report distinguishes fixing drift from applying intent

In enforcement mode a run classifies each resource as receiving an **intentional change** (the
catalog changed — someone asked for this), a **corrective change** (the catalog did not change; the
resource had drifted and was put back), or no change. `corrective_change` is a flag on the report
indicating whether any event remediated drift.

Node run status escalates to "with corrective changes" when that is the highest alert level in the
run — drift being silently repaired is treated as *more* alarming than a change you asked for, which
is the correct polarity and the opposite of how most systems report.

No-op mode reports what *would* have happened, preserving the same distinction ("would have
corrective changes"), and a no-op run is always reported as no-op even if some resources were
enforced.

### NixOS — every build is a generation, and rollback is selecting one

`nixos-rebuild switch` builds the configuration, adds the result to the system profile under
`/nix/var/nix/profiles`, activates it immediately and makes it the default boot entry. Sibling verbs
separate the axes that are usually conflated: `boot` (default at next boot, don't activate now),
`test` (activate now, don't touch the bootloader), `build` (produce it, activate nothing).

Each build is a **generation** — a collection of symlinks — and **older generations remain intact**.
`nixos-rebuild list-generations` shows number, build date, version and kernel.
`nixos-rebuild switch --rollback` returns to the previous one, and every retained generation is
selectable from the boot menu, so a configuration that breaks the running system is still
recoverable from outside it.

The honest limitation: as of late 2024 `nixos-rebuild` had no built-in way to switch directly to a
generation older than the previous one — the boot menu is the interface for that.

---

## Phase 2 — against the SLM layer

Every row carries the audit that produced it.

### Already-exists audit

| Concept | Files read | Present? |
|---|---|---|
| Quorum-gated config writes | `services/fleet_sync_guard.py` (an in-process asyncio lock preventing overlapping fleet syncs — #1979) | **N/A** — single control plane, no cluster quorum to lose |
| Scoped API tokens | `api/api_keys.py`, `user_management/services/api_key_service.py`, `user_management/schemas/api_key.py`, `services/auth.py:341-388` | **Stored, never enforced — defect** |
| Node life-cycle states | `models/database.py:35-46` `NodeStatus` | PENDING → ENROLLING → ONLINE → DEGRADED/OFFLINE/ERROR/**MAINTENANCE**/DECOMMISSIONED |
| Commissioning gate before service | same enum; `slm/agent/role_detector.py`, `port_scanner.py`, `health_collector.py` | **No `READY` state — gap** |
| Backup verification | `services/backup.py:112`, `:136-151`, `:207-221` | **Checksum only — gap** |
| Corrective vs intentional change | `services/reconciler.py` (`grep -nE 'corrective\|intentional'` → no hits) | **No — gap** |
| Rollback depth | `services/blue_green.py:277-302` `rollback()` | Previous state only; **no generation list** |
| Pinned package sets | `api/updates.py`, `models/manifest.py:183` | Partially — see #16038 |
| Agent-side condition watchers | `slm/agent/health_collector.py` | Collector reports; **decisions are control-plane side** |

### Confirmed defect — API key scopes are stored and never enforced

`services/auth.py:341` `get_api_key_user` is the request-time authentication dependency for
`X-API-Key`. It calls `APIKeyService.validate_key`, fetches the owning user, and returns:

    {"sub": user.username, "admin": user.is_platform_admin, "api_key_id": str(api_key.id)}

**It never reads `api_key.scopes`.** The scopes are accepted at creation (`api/api_keys.py:75`),
persisted (`api_key_service.py:53`, `:185`), echoed in responses (`:87`) and published by a
deliberately unauthenticated endpoint (`api/api_keys.py:118-121`). A repo-wide grep for `scopes`
outside tests returns only the schemas, that public endpoint and the security-headers allowlist —
no enforcement site anywhere.

Consequence: **an API key acts with its owning user's full privileges, `is_platform_admin`
included.** The scope list is decorative. This is precisely the failure Proxmox's default
privilege-separated tokens exist to prevent — there, effective permission is the intersection of
user and token, so a narrow token cannot inherit admin. Filed separately; see below.

### Adopt

**A. Commissioning gate before a node carries work — `MAAS`.** `NodeStatus` goes
ENROLLING → ONLINE with nothing in between: a node becomes eligible for work by finishing
enrollment, not by proving it is fit. The agent already collects what a gate would need
(`role_detector.py`, `port_scanner.py`, `health_collector.py`) — the inventory exists, it just
isn't a precondition. Adding a `READY` state that a node reaches only by passing declared checks
turns that data into a gate. Pairs with #16030's `skipped(reason)`: same principle, node scope
rather than role scope.

**B. Restore-and-verify backups — `Xen Orchestra`.** `BackupService` verifies a *checksum*
(`backup.py:136-151`) — proof the bytes arrived intact, not proof the backup restores. XO's answer
is to actually restore it, start it, and require a liveness signal within a timeout, then discard
the restored copy; and where "it booted" is the wrong predicate, the workload supplies its own via
a key the check waits on. That maps cleanly onto per-role backup (#16031): a role declaring backup
also declares how a restore of it is proved good. **Hidden cost:** a verify-restore consumes real
resources on a real node and can itself fail noisily — so it belongs on a schedule with an explicit
target, never inline in every backup.

**C. Corrective vs intentional change — `Puppet`.** The reconciler remediates (restart, cooldowns,
attempt limits at `reconciler.py:57-112`) but its events do not say whether a change *restored a
declared state that had drifted* or *applied a state the operator just asked for*. Those are
different facts and only one of them is alarming. Puppet's polarity is the instructive part: a run
containing corrective changes escalates *above* one containing intentional changes, because silent
self-repair is a signal that something else is breaking things. Feeds #16033 — an audit delta that
does not distinguish the two is half a record.

**D. Deploy generations, not just "previous" — `NixOS`.** `blue_green.rollback()` unwinds *this*
deployment. There is no list of prior known-good deploys to select from, so recovery from a bad
deploy that was already superseded is not a supported operation. NixOS's separation of verbs is the
transferable part — activate-now, default-at-next-start, and try-without-committing are three
different intents that a single "deploy" verb currently conflates. **Hidden cost:** retaining N
generations means retaining N artifact sets; the retention policy is the whole design, and without
one this becomes disk exhaustion with extra steps.

**E. Agent-side watchers with a loop-breaker — `Salt`.** #16035's invariant registry is currently
specified control-plane side, mirroring `security_posture_auditor`. Salt's split puts the *watcher*
on the agent and the *decision* on the master, which detects conditions the control plane cannot
poll for. Whatever the placement, adopt `disable_during_state_run` by name: an invariant that fires
on a condition our own remediation creates will re-trigger itself forever, and the loop-breaker
should ship with the registry rather than be discovered by the first author who hits it.

**F. Frozen, promotable content sets — `Katello`.** #16038 scopes the update set to what a role
declares; Katello goes further — publish a *filtered, frozen* version and promote it through
environments, so hosts consume a known set while upstream keeps moving. That is the same shape as
#16032's per-commit checksum manifest, applied to packages instead of files. Worth folding into
#16038's design rather than filing separately: the manifest already names the packages, and
"pinned + promoted" is the natural second step once it does.

### Already better here

- **Path-templated authorization** (Proxmox) is elegant but solves a problem FastAPI dependencies
  plus RBAC already solve with types; adopting a path-string namespace would be a downgrade. The
  *token* half is the part we lack, and that is the defect above, not an adoption.
- **`pmxcfs`** is a cluster-consensus answer to a problem a single control plane does not have. The
  transferable residue is narrow: enforcing uniqueness *structurally* rather than by convention. Our
  manifests declare `coexistence.conflicts_with` but nothing refuses to create the conflict.
- **cPanel's token model** is weaker than what we already have on paper — ours are hashed, prefixed,
  expiring and scoped. The defect is enforcement, not design.
- **ISPConfig's `sys_datalog`** is a pull-based intent log with two documented failure modes we do
  not want: unbounded growth without pruning, and an agent silently stuck at an old offset. Our
  transport was not audited in this pass, so no verdict — but "how do we detect an agent that has
  fallen behind" is the question their design answers badly and ours should answer explicitly.
