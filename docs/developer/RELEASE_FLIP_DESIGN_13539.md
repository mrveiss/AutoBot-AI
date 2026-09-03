<!--
Copyright 2025-2026 mrveiss
SPDX-License-Identifier: Apache-2.0
-->

# Release directories with an atomic pointer flip (#13539, #15092)

**Status:** design, not implemented. Owner decision recorded on #13539 (3 Sep 2026): build the
release-directory-with-atomic-pointer-flip scheme as the permanent fix. Stopping services during
the changeover is authorised, so restart cost is not a design constraint.

**Scope:** both writers of the deployed Python tree, in one change — the update playbook
(`autobot-slm-backend/ansible/playbooks/update-all-nodes.yml`) and the drift-resolve path in
`autobot-slm-backend/api/code_sync.py` (#15092). Landing one without the other makes the guarantee
true of one writer and silently false of the other.

Throughout, `<ROOT>` means the deployed root that `services/drift_checker.py:831`
(`get_default_deployed_dir`) derives from `SLM_DEPLOYED_ROOT`. No path in this design is a literal.

---

## 0. What is actually broken, restated as an invariant

A running CPython process resolves an import **lazily**, at first import, against whatever is on
disk at that instant. `sys.modules` is never re-read. Therefore:

> **Invariant R:** the directory tree a live interpreter imports from must never be mutated for the
> whole lifetime of that interpreter.

Every measured symptom of #13539 is a violation of R:

| Writer | Where | Violates R by |
|---|---|---|
| update playbook | `update-all-nodes.yml:307-341, 756-766, 1169-1535` — `unarchive: dest: <ROOT>/` | extracting 2000+ `.py` files over the live tree; the restart is ~300 tasks later at `:1080` |
| resolve job | `api/code_sync.py:402` | `_rsync_component_local(dest_dir=get_default_deployed_dir(component))` |
| drift-resolve endpoint | `api/code_sync.py:1093` (`_drift_resolve_rsync_or_fail`, `:994`) | same destination, different entry point (#15092) |
| shared-first sync | `api/code_sync.py:2925` (`_ensure_autobot_shared_synced`) | rewrites the live `autobot_shared` on **every** backend resolve |
| constraints deploy | `api/code_sync.py:1830` (`_deploy_constraints_dir`) | delete-style rsync into a hardcoded `/opt/autobot/constraints/` |
| root requirements | `api/code_sync.py:1858` (`_deploy_repo_root_requirements`) | `cp` into `_get_deploy_base()` |

**#15092 undercounts.** It names one call site; there are four rsync writers plus two file writers
in `code_sync.py` alone. A design that fixes named call sites will miss some. The design below
fixes the *destination*, and guards the *chokepoint*, so all six are covered by construction.

Shrinking the window is not fixing it. The three measurements are 22 m 00 s, 3 m 44 s, 25 m 36 s —
the variance is the point; it does not converge on "small enough".

---

## 1. Layout

### 1.1 The tree

```
<ROOT>/
  releases/
    <release-id>/                  <- immutable once published; shaped like the repo root
      autobot_shared/
      autobot-backend/
        autobot_shared -> ../autobot_shared        (RELATIVE, see 1.4)
        venv -> ../../../shared/autobot-backend/venv
        .env -> ../../../shared/autobot-backend/.env
        data -> ../../../shared/autobot-backend/data
        logs -> ../../../shared/autobot-backend/logs
        config -> ../../../shared/autobot-backend/config
        .deployed_commit -> ../../../shared/autobot-backend/.deployed_commit
      autobot-slm-backend/         (same shape)
      autobot-npu-worker/  autobot-browser-worker/  autobot-ai-stack/
      constraints/                 <- see 1.5
      requirements.txt             <- see 1.5
      RELEASE.json                 <- see 9
    <release-id>.incomplete/       <- a build in flight; can never be flipped to
  current  -> releases/<release-id>          <- THE pointer. One per node.
  previous -> releases/<older-id>            <- rollback target
  shared/                                    <- host state, outlives every release
    autobot-backend/{venv,.env,.env.*,data,logs,config,.deployed_commit}
    autobot-slm-backend/{...}
  code_source/                               <- unchanged: the git checkout
  autobot-backend  -> current/autobot-backend    <- compatibility symlink (1.6)
  autobot_shared   -> current/autobot_shared     <- compatibility symlink (1.6)
```

`shared/` is Capistrano's `shared/`, and the contents are not invented: they are exactly
`HOST_STATE_EXCLUDES` (`services/deploy_artifacts.py:69-77`) plus `venv`, which every rsync already
excludes as a build artifact. Those are, by the code's own definition, the paths that must survive a
sync — i.e. the paths that must not live inside an immutable release.

### 1.2 What is in scope for v1

`current` covers the **Python import surface**: `autobot_shared`, `autobot-backend`,
`autobot-slm-backend`, `autobot-npu-worker`, `autobot-browser-worker`, `autobot-ai-stack`,
`constraints/`, root `requirements.txt`, `libs/`.

The two frontends stay where they are. They already have an atomic-enough publish from #15430
(`update-all-nodes.yml:513-573`: build into `dist.staging`, verify `index.html`, `mv dist ->
dist.previous`, `mv dist.staging -> dist`), their trees are dominated by `node_modules`/`dist` which
are not source, and nginx re-resolves its `root` per request so no long-lived process pins them.
Folding them in would multiply release size by the largest thing on disk to solve a problem they do
not have.

**Cost of that decision, stated plainly:** the node ends up with two publish mechanisms — a pointer
flip for Python, a directory swap for bundles. Unifying them is future work, not this change.

### 1.3 Naming and env-backed configuration

New env-backed module constants in the new `services/release_layout.py` — the same shape as
`_SNAPSHOT_KEEP` (`api/code_sync.py:2531`) and `backup_retention_count` (`config.py:198`):

| Constant | Env var | Default | Meaning |
|---|---|---|---|
| `RELEASES_DIRNAME` | `AUTOBOT_RELEASES_DIRNAME` | `releases` | directory under `<ROOT>` |
| `CURRENT_LINK_NAME` | `AUTOBOT_CURRENT_LINK` | `current` | the pointer's name |
| `PREVIOUS_LINK_NAME` | `AUTOBOT_PREVIOUS_LINK` | `previous` | rollback pointer |
| `SHARED_STATE_DIRNAME` | `AUTOBOT_SHARED_STATE_DIR` | `shared` | host-state root |
| `RELEASE_KEEP` | `AUTOBOT_RELEASE_KEEP` | `3` | retention (§6) |
| `RELEASE_MIN_FREE_MB` | `AUTOBOT_RELEASE_MIN_FREE_MB` | `2048` | pre-build free-space floor |
| `RELEASE_INCOMPLETE_TTL_H` | `AUTOBOT_RELEASE_INCOMPLETE_TTL_H` | `24` | sweep age for `*.incomplete` |

Release id: `<utc-compact-timestamp>-<short-commit>`, e.g. `20260903T114500Z-6a0f4b296`. Sortable,
unique per deploy even for a redeploy of the same commit, and it carries the commit the playbook
already computes (`deploy_commit_full`, `update-all-nodes.yml:253`).

### 1.4 The `autobot_shared` symlink — a currently-merged blocker

Today the playbook writes an **absolute** link (`update-all-nodes.yml:405, 417, 791, 1554, 1595`):

```yaml
src: /opt/autobot/autobot_shared
dest: /opt/autobot/autobot-backend/autobot_shared
state: link
```

Inside a release that link **escapes the release and points back at the live tree**. Every guarantee
below would be void: a writer could obey "only write into a release" and still mutate what a live
interpreter imports, through one link. This is the same shape as #15092's vacuity trap, from the
other direction.

It must become a relative link inside the release (`autobot-backend/autobot_shared -> ../autobot_shared`),
and the release verifier must reject any symlink in the release whose `realpath` leaves the release
(§8, check V3). This is a prerequisite, not a detail.

### 1.5 `constraints/` and the root `requirements.txt` — solved for free

`autobot-backend/requirements.txt` uses `-c ../constraints/shared.txt` and `-r ../requirements.txt`,
which is why `code_sync.py:1822` hardcodes `/opt/autobot/constraints/` and `:1858` copies into
`_get_deploy_base()`. Because a release is shaped like the repo root, those `../` references resolve
**inside the release** automatically. Two hardcoded paths disappear and dependency pins become part
of the release rather than a shared mutable file.

### 1.6 Compatibility symlinks

`<ROOT>/<component>` becomes a symlink to `current/<component>`. Purpose: nginx configs, logrotate,
sudoers rules, cron, operator muscle memory, and any consumer not yet converted keep working.

**They are also the scheme's weakest point** — a careless writer reaches the live tree through the
old path and nothing is obviously wrong. The resolved-destination guard (§11) is the only thing that
prevents #15092 recurring, which is why it is mandatory rather than nice-to-have.

### 1.7 Relationship to the `dist.staging` precedent (#15430 / PR #15556)

**Same idea, strictly stronger mechanism.** #15430 is "build into a staging directory, verify one
artifact exists, publish only on success, keep the previous output serving on failure" — and the
failure path is exactly right: a failed build never touches `dist`.

Two differences, both forced by the problem:

1. **The publish is atomic here, and it is not there.** #15430 publishes with two `mv`s
   (`update-all-nodes.yml:562, 570`): `dist -> dist.previous`, then `dist.staging -> dist`. Between
   them `dist` does not exist. That is tolerable for nginx — a request in that instant 403s and the
   user retries — and intolerable for an interpreter, where a failed import is cached as a broken
   module and a name that exists reads as missing. The Python scheme uses a **single `rename(2)` on
   a symlink** (§2), which has no instant where the pointer is absent.
2. **Verification has to be semantic, not existential.** `index.html exists` is the right check for
   a bundle. `main.py exists` would not have caught #13539 at all — every file involved existed and
   was byte-identical across three copies. §8 says what the Python equivalent is.

So: generalisation of the same shape, with the publish step upgraded from "two renames" to "one
rename" and the verification step upgraded from "an artifact is present" to "the tree imports".

---

## 2. The flip

### 2.1 Syscall sequence

Performed by one function in `services/release_publisher.py`. All operations use directory file
descriptors so an ancestor rename cannot redirect them mid-sequence.

```
rootfd = open(<ROOT>, O_RDONLY|O_DIRECTORY)

# 1. record the rollback target (idempotent; a crash here is harmless)
symlink("releases/<old-id>", ".previous.tmp.<pid>", dir_fd=rootfd)
rename(".previous.tmp.<pid>", "previous", src_dir_fd=rootfd, dst_dir_fd=rootfd)

# 2. THE FLIP
symlink("releases/<new-id>", ".current.tmp.<pid>", dir_fd=rootfd)
rename(".current.tmp.<pid>", "current", src_dir_fd=rootfd, dst_dir_fd=rootfd)

# 3. make it durable before anything acts on it
fsync(rootfd)
close(rootfd)
```

Targets are **relative** (`releases/<id>`, not `<ROOT>/releases/<id>`) so the whole root is
relocatable and `SLM_DEPLOYED_ROOT` remains meaningful.

### 2.2 Why this is atomic and the obvious alternative is not

`rename(2)` within one directory on one filesystem is atomic with respect to other processes: POSIX
requires that a concurrent lookup of the destination name sees either the old link or the new one,
and that the name is never absent. The kernel swaps one directory entry.

`unlink("current"); symlink(new, "current")` — which is what `rm && ln -s` does, and what `ln -sfn`
may do depending on coreutils version — has a window between the two calls in which `<ROOT>/current`
**does not exist**. A process resolving a path through it in that instant gets `ENOENT`; for the
interpreter that is an `ImportError`/`OSError` on a module that is present on disk — the same
misleading failure class this issue exists to remove, produced by the fix. Worse, a crash in the
window leaves the node with no pointer at all and nothing serving.

The design therefore does not use `ln -s` anywhere for the pointer. A guard test (§11, T4) asserts
this: no `ln -sf`/`ln -sfn` on the pointer name in any ansible task, and the publisher's AST contains
`os.rename`/`os.replace` on the pointer and no `os.unlink` of it. Where a shell equivalent is
genuinely needed, `mv -T <tmp> current` is `rename(2)` and is acceptable.

### 2.3 What each reader observes

| Reader | At instant t-1 | During rename | At instant t+1 |
|---|---|---|---|
| Process pinned to old release (§3) | old tree | **does not read `current` at all** | old tree |
| A newly-exec'd process | old release | resolves one side or the other, never both | new release |
| `open("<ROOT>/current/x/y.py")` | old `y.py` | old or new, never a mix, never ENOENT | new `y.py` |
| An `open` fd taken before the flip | still valid — fds are inode handles, unaffected | | |
| `readlink("<ROOT>/current")` | `releases/<old>` | one or the other | `releases/<new>` |
| nginx / logrotate via a compat symlink | old | old or new per resolution | new |

The flip is **invisible to every running Python process**, which is the whole point, and is why the
next section matters more than this one.

---

## 3. Restart, and the pinning that makes the flip a fix

### 3.1 The flip alone fixes nothing

If the running interpreter's `sys.path` contains `<ROOT>/current/...` as a **string**, the flip makes
the new tree visible to it on the next lazy import, and #13539 reproduces with a window of
flip-to-restart instead of sync-to-restart. Shorter, identical failure. The owner flagged exactly
this on #13539: *"the pinning is the part that must not be dropped in review."*

### 3.2 The launcher

Every managed Python unit's `ExecStart` becomes a launcher shipped **inside the release**
(`autobot_shared/deploy/release_exec.py`, so it versions with the code it launches):

1. `dirfd = os.open(os.path.dirname(__file__), O_RDONLY|O_DIRECTORY)`, then
   `os.readlink(f"/proc/self/fd/{dirfd}")`. This resolves through an **inode handle**, so it names
   the release this launcher was actually loaded from — a flip landing between systemd's exec and
   this line cannot split the process across two releases.
2. Export `AUTOBOT_RELEASE_ROOT=<resolved>` and `AUTOBOT_RELEASE_ID=<id from RELEASE.json>`.
3. Build `PYTHONPATH` from **resolved** paths only. No entry contains the pointer name.
4. `os.chdir(<resolved>/<component>)` — cwd is an inode reference, so it stays pinned to this
   release even if the directory is later renamed or the pointer moves.
5. `os.execv(<venv python>, [...])`.

The interpreter therefore starts with no occurrence of `current` anywhere in its environment,
`sys.path`, or cwd. It imports from its own frozen release for its entire life. Invariant R holds
because that release is never written again: releases are built under `<id>.incomplete` and become
`<id>` by a rename at the moment they are complete.

**Alternative considered and rejected for v1:** systemd `RootDirectory=`/`BindPaths=` to give each
unit a mount namespace where the release is bind-mounted at a fixed path. Strictly stronger — the
process could not reach another release even deliberately — but it breaks `EnvironmentFile`,
`StandardOutput=append:` log paths, and `sudo systemctl` interactions, and makes every debugging
session a namespace-entry exercise. It is the natural v2 if the launcher's pinning is ever shown to
leak.

### 3.3 Ordering

Per node, for the Python components:

```
1. preflight        free space >= floor; pointer is a symlink; no stale .incomplete
2. build            extract/copy into releases/<id>.incomplete   [live system untouched]
3. link shared      .env / data / logs / config / venv / .deployed_commit symlinks
4. verify           §8, run against the STAGED tree             [live system untouched]
5. rename           releases/<id>.incomplete -> releases/<id>   [atomic; still not live]
6. stop             the units that import the tree              [only if step 7 will run]
7. deps             pip install into shared/<component>/venv    [only if deps changed]
8. FLIP             §2.1                                        [atomic]
9. start            the units
10. post-flip gate  health + release-id assertion (§9); auto-rollback once on failure
11. prune           §6
```

**Why steps 1-5 cannot reopen the window:** nothing in them writes to any path a running process can
reach. The release under construction is a directory no live process has ever resolved.

**Why step 6 exists even though pinning makes the flip safe:** in v1 the venv is *shared state*, not
part of the release (§1.1, and see the risk in §13.1). `pip install` mutates `site-packages`, which
**is** in the live processes' import surface — a fresh violation of R by a different route. So when
`python_deps_changed` is true (the playbook already computes this at `update-all-nodes.yml:229`),
units stop first. When it is false, step 7 is skipped, no live import surface is mutated, and
step 6 can be skipped too. One order, one conditional.

**Why step 9 is after step 8 and not before:** a process started before the flip would pin the *old*
release and immediately be stale. Start strictly after.

**Downtime:** the restart, plus `pip install` only on the deploys that change dependencies. Not the
sync. Today's 25 m 36 s window becomes ~seconds of *deliberate, visible* downtime.

**The self-killing component.** `autobot-slm-backend` restarts itself (`code_sync.py:1731`,
`_SELF_SERVICE_NAME`; `_restart_pending` at `:1732`). It flips first, `fsync`es the root directory
(step 8's third call — this is why it is not optional), then issues its own restart. That is safe
precisely because it is pinned: between flip and its own death it keeps importing from its old
release. Without the `fsync`, a power loss at that instant could leave the pointer unflipped and the
new release orphaned.

---

## 4. Both writers

### 4.1 What they share

One implementation, two entry points:

- `services/release_layout.py` — pure path/id logic, no I/O beyond `stat`. Every path derived from
  `SLM_DEPLOYED_ROOT`.
- `services/release_publisher.py` — build, link shared state, verify, rename, flip, prune, rollback.
- `services/release_verifier.py` — §8.
- `tools/release_flip.py` — a thin `__main__` over the publisher with **no third-party imports**, so
  ansible can run it with the system interpreter without a venv.

**Why shared rather than two implementations:** the two writers must agree on three things — where
releases live, what "verified" means, and the exact flip sequence. Any divergence in any of the
three is precisely the #15092 failure mode ("the guarantee is true of one writer and silently false
of the other"), and divergence in the third is a corrupted node. A shared helper makes agreement
structural instead of a review responsibility. The counter-argument — ansible calling into SLM
backend code couples the playbook to the service — is answered by the CLI: the playbook invokes a
**script inside the release it is publishing**, using the system python. The release owns the
definition of how to publish itself, which also makes the migration self-bootstrapping (§10).

### 4.2 The update playbook

The change is smaller than it sounds because the playbook already builds tarballs with `git archive`
(`update-all-nodes.yml:117-119`) and extracts them (`:307-341`, `:756-766`, `:1169-1535`). Extraction
into an **empty release directory** is already a staged build; the only defect is that `dest:` is the
live root.

- Play 0 computes `release_id` once from `deploy_commit_full` and passes it to every play as a fact.
- Every `unarchive: dest: <ROOT>/` for a Python component becomes `dest: <ROOT>/releases/<id>.incomplete/`.
- New tasks after extraction: link shared state, run `tools/release_flip.py verify`, rename to
  `<id>`, stop units (conditional on `python_deps_changed`), pip, `release_flip publish`, start units,
  post-flip release-id assertion.
- The existing explicit restarts (`:1080` backend, `:1114` celery, and the per-component ones at
  `:1209/:1266/:1348/:1468/:1512`) stay explicit. They must **not** become handlers: #15323 measured
  12 handler runs on a deploy that wrote 3,887 `.py` files, of which **zero** were the backend or
  celery restart, because a handler only fires on `changed` and nothing notified it. The playbook
  comment at `:1100-1103` already records this; the design keeps that decision and adds an ordering
  test (§11, T5) so a task inserted later cannot silently land before the flip.

A useful side effect: `git archive` into an empty directory produces a tree with no stale
leftovers, so the "file deleted upstream lingers on the host forever" class disappears for the
playbook path without a delete-style rsync.

### 4.3 Drift-resolve (#15092's AC1)

**Answer: it can build and flip a release, and it should.** Refusing drift-resolve while the release
scheme is active was considered and rejected — an operator resolving drift is usually recovering
from a broken deploy, and removing the recovery tool at that moment is worse than the problem.

The mechanism, and why it is cheap:

```
1. cp -al  <current release>/  ->  releases/<id>.incomplete/     (hardlink copy: near-zero cost/disk)
2. rsync -a --delete <source>/ -> releases/<id>.incomplete/<component>/   (existing argv, new dest)
3. relink shared state; verify (§8); rename to releases/<id>
4. stop (if deps changed) -> pip -> flip -> start -> post-flip gate
```

Step 1 is safe because rsync **replaces files by writing a temp file and renaming it into place**,
which breaks the hardlink rather than mutating the shared inode. This is the standard `--link-dest`
idiom. It is only safe as long as rsync is never given `--inplace` — it is not today
(`_rsync_local_cmd`, `code_sync.py:1504`), and a guard test asserts it never is (§11, T6).

Consequence worth stating: drift-resolve now builds a **whole release**, not a component-shaped one.
That is forced by the pointer being per-root, and it is correct anyway — `autobot_shared` is the
shared import surface and `_ensure_autobot_shared_synced` (`:2925`) already recognises this by
syncing shared ahead of every backend resolve. One release, one flip, one restart set.

The deletion guard (`_resolve_deletion_guard`, `:1511`) and the shared-first sync keep working
unchanged; they now run against the staged copy, so a refused resolve leaves the live tree
untouched by construction rather than by an early return.

**`_snapshot_component` / `_rollback_component` / `_prune_old_snapshots` (`code_sync.py:2530-2594`)
are subsumed and must be retired in the same change.** The previous release *is* the snapshot, and
it is a better one: it is verified, it is what was actually running, and reverting to it is a
rename rather than a delete-style rsync over a live tree. Leaving both in place gives the node two
rollback stories that can disagree — and the weaker one is the one that already had a defect
blessed by a passing test (#15323). Retiring it is also where the line budget for the ratchet comes
from (§12).

---

## 5. Rollback

- `<ROOT>/previous` always names the release that was current before the last flip.
- Reversing a flip is the *same* code path as making one: `release_flip publish --to <id>`, which
  performs §2.1 with old and new exchanged, then restarts. There is no separate, less-tested revert
  path — that is deliberate; the revert path is the one you need when things are already bad.
- `previous` is recomputed from the mtime-sorted release list when the symlink is missing or equal to
  `current` (recoverable from a crash mid-flip, §7).

**Operator surfaces, in order of preference:**

1. **UI** — a Releases panel in the existing maintenance/code-sync screen listing `RELEASE.json` for
   each retained release with `current`/`previous` marked, and a Roll back action hitting
   `POST /code-sync/releases/{id}/activate`. Same surface an operator already uses; no new tool.
2. **Recovery page** — the static `static/recovery.html` surface added by PR #15556 for #15462 exists
   precisely for "the dashboard is what broke". Rollback belongs there too.
3. **CLI** — `tools/release_flip.py --to <id>` on the host, for when nothing is serving.

**What rollback does NOT restore (§13.1, §13.2):** the shared venv, and any applied alembic
migration. `RELEASE.json` records the requirements hash and the alembic head of each release, and
the rollback surface must **say so when they differ** rather than reporting a clean revert. A
rollback that silently claims completeness is worse than no rollback.

---

## 6. Retention

- `AUTOBOT_RELEASE_KEEP`, default `3`. Mirrors `AUTOBOT_SNAPSHOT_KEEP` (`code_sync.py:2531`) and
  `SLM_BACKUP_RETENTION_COUNT` (`config.py:198`) — same shape, so there is one convention.
- Pruned by the publisher **after** step 10 (a successful flip *and* a passing post-flip gate), never
  before. A prune that runs before the gate can delete the tree you are about to roll back to.
- Never pruned, regardless of age or count:
  - the release named by `current`;
  - the release named by `previous`;
  - **any release with a live process in it** — enumerate `readlink /proc/*/cwd` and retain every
    release that appears. Cheap, and it prevents deleting the tree out from under a still-running
    old process, which is the same defect class this whole design exists to remove, in reverse.
- `*.incomplete` directories older than `AUTOBOT_RELEASE_INCOMPLETE_TTL_H` are swept at the start of
  the next build, not at the end of this one (a build that died is evidence; give an operator a day
  to look at it).
- The prune is `rmtree` of whole release directories only. It never descends into `shared/` and never
  removes a symlink at `<ROOT>` level.

---

## 7. Failure modes

| # | Failure | State immediately after | Recovery |
|---|---|---|---|
| F1 | Build dies mid-extract / mid-rsync | `releases/<id>.incomplete` partial; `current`, `previous`, all live processes untouched | Nothing to undo. Next build sweeps `.incomplete` past its TTL. The failing deploy reports the error; the node keeps serving old code. |
| F2 | Verification fails (§8) | Same as F1, plus the verifier's report | The release is never renamed to `<id>` and can never be flipped to. This is the intended catch for #13539 and the case that must be *loud*: the deploy fails with the failing module and symbol named. |
| F3 | Crash between the `previous` rename and the `current` rename | `previous` == the release that is still `current` | Harmless and self-correcting: the next flip rewrites both. If a rollback is needed first, `previous` is recomputed from the mtime-sorted release list. |
| F4 | Crash after the `current` rename, before restart | New release live on disk; processes still pinned to the old one | This is the exact state #15323 measured — and now it is *detectable in one comparison* (§9): the process's release id differs from `current`'s. The post-flip gate restarts; if the deploy died entirely, the divergence detector reports `stale` and the operator restarts. No import can fail in the meantime, because the old processes never read the new tree. |
| F5 | Crash before the `fsync`, then power loss | Pointer may or may not have flipped; both releases complete on disk | Either state is consistent. On boot, units start from whichever release the pointer names, verified and whole. |
| F6 | Disk fills | Preflight refuses when free space < `AUTOBOT_RELEASE_MIN_FREE_MB` + measured build size; if it fills mid-build, F1 | `current` untouched — old code keeps serving, which is the property a flat rsync does not have (a full disk mid-rsync leaves a *half-written live tree*). Prune runs before the preflight check so retention reclaims space first. Releases are source trees (tens of MB), not venvs — see §13.1 for the disk trade this buys. |
| F7 | Release complete and verified but broken at import time anyway | Units fail to start after the flip | `Restart=always` + `StartLimitBurst=5`/`StartLimitInterval=120` (`autobot-backend.service.j2`) bounds this to ~5 attempts in 2 minutes, then `failed` — loud, and it cannot loop an operator out of intervening (the same reasoning #15323 used to make the unconditional restart safe). The post-flip gate then performs **one** automatic rollback to `previous` and restarts; a second failure stops and escalates rather than flapping. Every auto-rollback is recorded in the job row and the release log. |
| F8 | `pip install` fails (deps step) | Units are stopped, release staged and verified, pointer NOT yet flipped | Restart the units — they come back on the **old** release with the old venv, which is a working state. This is strictly better than today's `code_sync.py:410-421`, where a failed pip leaves the live tree rewritten and the job row committed. |
| F9 | Two writers race (a deploy and a drift-resolve) | Both would flip | An exclusive lock (`flock`) on `<ROOT>/.release.lock` held for steps 2-10. The loser fails fast with "a publish is in progress", reusing the existing `_reject_if_deploy_in_progress` 409 path (`code_sync.py:1735`). |

---

## 8. Verification, before the flip

This is the part that decides whether the scheme actually fixes #13539 or merely relocates it.
"Run the tests" is not an answer: the deploy host has no test fixtures, no test DB, and the failure
being prevented is an *import-time name binding against a specific tree*, which a green CI run on a
different machine does not establish.

Four checks, all executed against the **staged** release with cwd and `PYTHONPATH` pinned there.

**V1 — structural (cheap, always).** `RELEASE.json` parses; every component in its manifest exists
and is non-empty; the file count per component is within a sanity band of the previous release (a
90% shrink is a truncated tarball, not a release); every shared-state symlink resolves.

**V2 — compile.** `python -m compileall -q -f <release>` over the staged tree. Catches syntax errors
and unwritable/truncated files. Note honestly: this would **not** have caught #13539 — every file
compiled fine.

**V3 — containment.** Walk every symlink in the release; `realpath` each; fail if any resolves
outside the release, or if it resolves through `<ROOT>/current`. This is what stops the absolute
`autobot_shared` link (§1.4) from silently defeating the whole scheme.

**V4 — the cross-module symbol check. This is the one that catches #13539.**

Static, AST-based, no interpreter, no side effects, runs over ~4k files in seconds:

> For every `from X import a, b` and `import X.y` in the staged tree where `X` resolves to a module
> **inside the staged release**, assert that `a` and `b` are bound at module level in `X` — as a
> `def`, `class`, assignment, re-export, or `__all__` entry.

Applied to the #13539 incident: `api/heartbeat.py:38` has
`from autobot_shared.auth.permissions import is_admin_role` at module scope. In a staged release
where `permissions.py` lacks that symbol, V4 fails naming both the importer and the symbol, and the
release is never flipped. In the incident, the tree that *would* have been staged was internally
consistent — and V4 would have passed, correctly. The failure came from mixing a new consumer with
an old provider, which is exactly what the release boundary prevents and what V4 asserts is not
present *within* one release.

**V5 — fresh-interpreter import sweep (the stronger check, where it can run).** A subprocess with
`PYTHONPATH`/cwd pinned to the staged component, which imports every module under `api/` and
`autobot_shared/` and reports each `ImportError` with its module name. This is exactly the check the
#13539 investigation ran by hand *after* the fact (*"fresh import: OK"*, *"OK api.codebase_analytics
.endpoints.import_tree"*) — the design's contribution is running it **before** the flip instead of
during the post-mortem.

Constraint: it needs the shared-state symlinks in place (for `.env`) and it executes module-level
code, so it must be gated per component by an explicit "importable without side effects" declaration
and run with a read-only-ish env. Where a component is not declared importable, V4 is the floor and
V5 is skipped — with that skip **recorded in `RELEASE.json`**, so nobody later believes a release was
import-verified when it was not.

V1-V4 are mandatory and hard-fail. V5 is mandatory where declared.

---

## 9. The measurement trap (#15323)

#15323 established that three fix verifications (#14866, #14010, #13570) were wrong because the
running process predated the fix, and that the first attempt to detect this was itself wrong twice —
it checked only the first unit per component, and it compared mtimes that rsync preserves from
*source*. The lesson is that "which code is this process running" must be answerable **from the
process**, not inferred from the filesystem.

Three artifacts, in ascending order of trustworthiness:

1. **`RELEASE.json`** in each release: `{id, commit, ref, built_at, built_by, components[],
   requirements_sha256, alembic_head, verifier: {v1..v5 results, skips}}`. Answers *what this tree
   is*. Falsifiable by anyone who edits the file — which is why it is not the primary.
2. **`AUTOBOT_RELEASE_ID`**, exported by the launcher (§3.2) into the process environment and
   surfaced on `/health` and per-component on the existing `GET /code-sync/status`. Answers *what
   this process believes it is running*. Requires the process to be alive and cooperative.
3. **`readlink /proc/<MainPID>/cwd`** — the primary. The launcher `chdir`s into the release before
   `exec`, and cwd is an **inode handle**, not a string. It cannot be falsified by a later flip, by a
   rename, by an mtime, or by a `touch`. It needs no cooperation from the process and works on a
   hung one. Answers *what this process is actually running*, which is the question the three wrong
   verifications got wrong.

**Detector.** Extend `services/process_divergence.py` — already the right home, already deliberately
free of `api.*` imports, already correct about never collapsing "cannot tell" into `healthy`. Add a
release-aware comparison: for each unit, `release_of(MainPID) == readlink(<ROOT>/current)`. This is
exact equality of two ids; no ctime, no monotonic timestamps, no locale parsing. The existing
ctime path stays for components not on the release scheme and for the `unknown` cases. The
conservative aggregation (`stale` > `unknown` > `healthy`) and the multi-unit sweep from #15323's
review are preserved unchanged — both defects that review caught would still be defects here.

**Post-deploy assertion.** #13539's outstanding unticked criterion — *"no managed service's start
time predates the code it is running"* — becomes a one-line comparison per unit, run as step 10 of
§3.3 and as a repo-testable assertion in the playbook. From then on, **a fix verification cites the
release id of the process**, and "the running process predated the fix" is a statement that can be
checked in one command instead of discovered three issues later.

---

## 10. Migration from the live flat layout

The node today has real directories at `<ROOT>/<component>` with host state inside them (`venv`,
`.env`, `data`, `logs`, `config`, `.deployed_commit`). The first release-scheme deploy converts it,
once, per node, with services stopped (authorised).

```
M0  preflight   refuse if <ROOT>/current exists and is NOT a symlink (partial prior migration);
                refuse without -e release_migration_confirm=true; require a fresh host backup;
                emit the full manifest of what M2 will move, before moving anything.
M1  stop        every managed Python unit on the node.
M2  move state  for each component: mkdir <ROOT>/shared/<c>/ and `mv` .env .env.* data logs config
                venv .deployed_commit into it. Same filesystem => rename(2): instantaneous, no
                copy of a multi-GB venv. Idempotent: skip anything already moved.
M3  build       normal build of releases/<id>.incomplete from the tarballs; link shared state; verify.
M4  rename      releases/<id>.incomplete -> releases/<id>
M5  flip        §2.1. previous is unset on a first migration; the flat dirs are still the fallback.
M6  compat      per component, assert the flat dir now contains only tracked source, then replace it
                with a symlink to current/<component> (one rename-based publish each).
M7  units       render the new unit templates (launcher ExecStart, resolved PYTHONPATH),
                daemon-reload, start.
M8  gate        §9 assertion: every unit's release id == current. Then and only then, finish.
```

**No flying start.** Services are down from M1 to M7. The `venv` move in M2 is why the stop is not
optional: a running interpreter survives a rename of its venv (inode handles), but `ExecStart`
strings and `sys.prefix` do not, so a process left running across M2 would be unrestartable.

**Reversibility.** Before M6 the flat directories are still real trees; aborting needs only moving
the state back. **M6 is the point of no return** — after it, the pre-migration layout is not
restorable without the backup M0 required. That is why M0 gates on an explicit flag and a backup,
and why M6 runs after M5 has already proved the release works.

**Inventory required before implementation** (each is a place that names `<ROOT>/<component>` with a
resolved meaning and must be checked against the compat symlinks): nginx `root`/`alias`
(`roles/frontend/templates/nginx-frontend.conf.j2:56`), all unit templates, `_COMPONENT_PIP_PATHS`
(`code_sync.py:1595-1604`, currently two hardcoded literals per component), logrotate, sudoers,
cron, `AUTOBOT_SNAPSHOT_DIR`.

---

## 11. Test strategy

| # | Guarantee | Test |
|---|---|---|
| T1 | No path is hardcoded | With `SLM_DEPLOYED_ROOT` set to a tmpdir, every path returned by `release_layout` is under it; assert `"/opt/autobot"` appears in none of them. |
| T2 | **The vacuity probe (#15092 AC2)** | `test_resolve_destination_is_never_inside_the_live_tree`: take the destination the resolve path actually hands to rsync, `Path(dest).resolve()`, and assert (a) it is under `<ROOT>/releases/<id>` resolved, and (b) `<ROOT>/current` resolved is not one of its parents. |
| T3 | **T2 is not vacuous (#15092 AC3)** | The contrast mutation: create `<ROOT>/current/autobot-backend/releases/pending` — a path *containing* the substring `releases`, reached through the live pointer — and feed it as the destination. A substring assertion (`"releases" in dest`) **passes** this fixture; T2's resolved-path assertion **fails** it. That fixture is checked in as the mutation proving the test has teeth, exactly as #15092's AC3 requires. A second mutation repoints the destination at `<ROOT>/autobot-backend` (the compat symlink) and must also fail. |
| T4 | The flip is atomic | (a) Concurrency: a reader loop `open()`ing `<ROOT>/current/marker` across N flips never sees `ENOENT` and never sees a mixed tree. (b) Static: AST scan of the publisher asserts `os.rename`/`os.replace` on the pointer and no `os.unlink` of it; YAML scan asserts no `ln -sf`/`ln -sfn` targets the pointer name in any task. |
| T5 | Restart never precedes the flip | Repo test parsing `update-all-nodes.yml` (same shape as `repo_tests/update_deps_detection_window_test.py`): no `state: restarted`/`started` task for a code-importing unit appears before the flip task in its play, and no `unarchive.dest` resolves inside the pointer. |
| T6 | Hardlink copy stays safe | Assert the resolve rsync argv never contains `--inplace`, and a functional test that writing through a `cp -al` copy does not mutate the source inode. |
| T7 | **#13539's own regression** | Fixture release containing `from mod import missing_symbol` must fail V4; the contrast fixture with the symbol present must pass. Runs in CI, catches the defect class at PR time and not only at deploy time. |
| T8 | Containment | A release containing an absolute `autobot_shared` symlink (today's merged form, §1.4) must fail V3. |
| T9 | Pinning | The rendered unit content and the launcher's exported env contain no occurrence of the pointer name; every `PYTHONPATH` entry is under `<ROOT>/releases/`. |
| T10 | Retention | Never prunes `current`/`previous`; never prunes a release with a live `/proc/*/cwd`; keeps exactly `AUTOBOT_RELEASE_KEEP`; `.incomplete` swept only past its TTL. |
| T11 | Divergence | A process on release A while `current` is B => `stale`; unresolvable => `unknown`, never `healthy`; multi-unit components aggregate conservatively (preserves #15323's two review fixes). |
| T12 | Rollback is the same path | `publish --to <previous>` and a forward publish execute the identical flip function; asserted structurally, not by duplicated behaviour tests. |

T7 deserves emphasis: it is the first test in this repo that would have failed on #13539's actual
defect, and it runs without a host.

---

## 12. Staging — what cannot be proven in CI

CI can prove the syscall sequence, the path derivation, the verifier and the guards. It cannot prove
the layout works on a node. Before this is trusted, on a host, with output pasted (redacted) onto the
issue:

1. Migration (§10) end to end; then a normal deploy; then **the same release deployed twice** (id
   collision handling).
2. A rollback, and a roll-forward after it.
3. A deploy with `python_deps_changed` true, and one with it false — confirm the stop only happens in
   the first.
4. `SIGKILL` the publisher at three points — mid-build, between the `previous` and `current` renames
   (F3), after the flip before restart (F4) — and confirm each recovers as the table says.
5. Fill the filesystem below the free-space floor; confirm the build refuses **before** touching
   `current` and that the old code keeps serving (F6).
6. `readlink /proc/<MainPID>/cwd` for every managed unit resolves to the release `current` names
   (§9). This is the acceptance evidence, and it replaces every mtime argument.
7. A deliberately broken release (a module importing a symbol removed from its provider) is caught by
   V4 **before** the flip; and separately, one that slips past V4 triggers exactly one auto-rollback
   and then stops (F7).
8. Compat symlinks satisfy nginx, logrotate and sudoers; the SLM backend survives its own flip and
   self-restart (§3.3).
9. A drift-resolve on a live node builds and flips a release; `_resolve_deletion_guard` still refuses
   what it refused before, and refusing now leaves `current` untouched.

---

## 13. Risks, and what I would not do

### 13.1 The venv is shared, so rollback is incomplete — the biggest honesty point

In v1 the venv lives in `shared/<component>/venv`, not in the release. Consequences:

- A release that bumps a dependency mutates the environment the **previous** release runs in. Rolling
  back restores code but not `site-packages`, so the "last known good" you roll back to is not the
  configuration that was last known good.
- The deps step must therefore stop services first (§3.3 step 6), which is the only unavoidable
  downtime beyond a restart.

Why not per-release venvs anyway: multi-GB per release x `RELEASE_KEEP`, a full `pip install` per
deploy instead of an incremental one, and console-script shebangs baked with an absolute path that
must be rehomed after any copy. That is a bigger change than the defect being fixed and would
plausibly not land.

Mitigations that must ship with v1: `RELEASE.json` records `requirements_sha256`; the rollback
surface refuses to describe a revert as complete when the target release's hash differs from the
installed one. The escape hatch is designed in — the venv is reached through a symlink inside the
release, so making it per-release later is a change to one link target and the prune rule, not a
re-architecture.

### 13.2 Alembic migrations are not reversed by a flip

A release that migrates the schema is forward-only in practice. The scheme makes this *more*
dangerous by making rollback feel complete. `RELEASE.json` records the alembic head; the rollback
surface must state when the head differs and require an explicit acknowledgement. I would **not**
auto-downgrade — an automatic schema downgrade during an incident is a data-loss generator.

### 13.3 The compat symlinks are a hole by design

`<ROOT>/autobot-backend -> current/autobot-backend` keeps everything working *and* lets a careless
writer reach the live tree by the old path. Convention will not hold this; T2/T3 are the only
mechanism. If the resolved-destination guard is ever weakened to a substring check, the scheme
silently reverts to today's behaviour — which is precisely how #13539's earlier fix looked correct
while changing nothing.

### 13.4 Debugging gets harder

`ls <ROOT>/autobot-backend` no longer answers "what is running" — you have to ask the process
(§9). That is the trade for correctness, and it is why the three reporting surfaces are mandatory
rather than nice-to-have. Expect one round of confused incident response and write the runbook
(`docs/runbooks/CODE_UPDATE.md`) before, not after.

### 13.5 Two publish mechanisms coexist

Python flips a pointer; frontends swap directories (#15430). A reader will reasonably assume one
mechanism covers the node. The docs must say plainly which surface each covers, and unification
should be filed rather than left implicit.

### 13.6 What I would explicitly not do

- **Not** put the venv in the release in v1 (§13.1).
- **Not** use systemd `RootDirectory=`/namespaces in v1 (§3.2) — stronger, much harder to operate.
- **Not** let drift-resolve build a per-component release. The pointer is per-root; a per-component
  pointer set means N pointers, N flips, and a window between them — the defect, reintroduced with
  extra machinery.
- **Not** keep the snapshot/rollback machinery alongside this (§4.3). Two rollback stories that can
  disagree, and the weaker one already had a defect defended by a passing test.
- **Not** use `ln -sfn` anywhere near the pointer (§2.2).
- **Not** convert the explicit restarts back into ansible handlers (§4.2) — #15323 measured that
  costing 3,887 files' worth of silent staleness.

---

## 14. Scope estimate

### New files (~740 lines)

| File | ~Lines | Contents |
|---|---|---|
| `autobot-slm-backend/services/release_layout.py` | 150 | env-backed paths, id generation, `RELEASE.json` read/write, `release_of_pid` |
| `autobot-slm-backend/services/release_publisher.py` | 250 | build, link shared state, rename, flip, previous, prune, rollback, lock |
| `autobot-slm-backend/services/release_verifier.py` | 200 | V1-V5 |
| `autobot-slm-backend/tools/release_flip.py` | 80 | CLI over the above; stdlib only, runnable by system python |
| `autobot_shared/deploy/release_exec.py` | 60 | the pinning launcher |

Each stays under the 30-line-function rule and well under the size ratchet; split `publisher`
further if it exceeds ~300 lines.

### Modified files (~+320 / -200)

| File | Change |
|---|---|
| `services/drift_checker.py` | split `get_default_deployed_dir` into `get_live_dir` (pointer-resolving, readers) and `get_release_component_dir(release, component)` (writers); ~+25 |
| `api/code_sync.py` | four rsync call sites + two file writers re-pointed at the publisher; **must be net-negative** (see blocker B1) — retiring the snapshot trio at `:2530-2594` funds it |
| `services/process_divergence.py` | release-id comparison path; ~+60 |
| `ansible/playbooks/update-all-nodes.yml` | release fact, `dest:` changes, link/verify/rename/flip/gate tasks, ordering; ~+120 / -40 |
| `ansible/roles/backend/templates/*.service.j2` x3, plus slm-backend / npu / browser / ai-stack units | ExecStart via launcher, resolved PYTHONPATH; ~8 files |
| new `ansible/roles/release/` (or `tasks/release_migrate.yml`) | migration §10; ~120 |
| `pipeline-scripts/hardcoded_values_baseline.txt`, both size-ratchet baselines | mechanical |
| `docs/runbooks/CODE_UPDATE.md`, `docs/developer/ARCHITECTURE_EXCEPTIONS.md` | runbook + the "two publish mechanisms" exception |

### Tests (~650 lines, ~8 files)

T1-T12 above, of which T2/T3 (the #15092 vacuity probe and its mutation) and T7 (the #13539
regression) are the load-bearing ones.

### What can land incrementally, and what cannot

**Independently landable, before anything flips — each valuable on its own:**

1. `release_verifier.py`'s V4 (cross-module symbol check) + T7, run as a CI check over the repo. This
   catches the #13539 defect class **at PR time** and is worth landing even if the rest slips.
2. `release_layout.py` + T1 — pure, inert, no behaviour change.
3. The `/proc/cwd` and `AUTOBOT_RELEASE_ID` reporting in `process_divergence.py` + `/health` — inert
   until releases exist, and it makes the migration observable while it happens.
4. Fixing the absolute `autobot_shared` symlink (§1.4) to relative — correct today, prerequisite
   tomorrow.
5. Unifying the `backend_install_dir` ambiguity (blocker B3) — a correctness fix in its own right.

**Must land atomically, in one change, on one deploy:** the layout migration, the unit templates,
the playbook flip, all six writer call sites, and the `get_default_deployed_dir` split. Splitting
these leaves a host where a unit reads a path no writer maintains, or a writer writes where no unit
reads. That is #15092's rule generalised: a guarantee that is true of one half of the system and
silently false of the other is worse than not having it.

---

## 15. Blockers in existing code

| # | Blocker | Where | Why it blocks |
|---|---|---|---|
| B1 | **The size ratchet is exact.** `api/code_sync.py` is pinned at exactly 6112 lines in two baselines | `repo_tests/python_file_size_ratchet_baseline.py:456`, `scripts/python_file_size_known_large.py:451` | The change cannot add a line to the file it must modify. Feasible only by removing more than is added — retiring the snapshot trio (`:2530-2594`, ~65 lines) and collapsing `_drift_resolve_rsync_or_fail` into a publisher call. Must be planned into the implementation, not discovered during it. |
| B2 | **`get_default_deployed_dir` is one function with ~15 consumers** that would all silently follow the pointer | `services/drift_checker.py:817` | Some consumers want the live tree (drift comparison, divergence scan); writers must be unable to get it. Must be split into two named functions before any writer changes, or the vacuity guard has nothing to assert against. |
| B3 | **`backend_install_dir` means two different things** — `/opt/autobot` in `setup-user-backend.yml:26`, `/opt/autobot/autobot-backend` in `roles/backend/defaults/main.yml:10` — and the unit derives autobot_shared's path as `backend_install_dir \| dirname` | `roles/backend/templates/autobot-backend.service.j2` (PYTHONPATH line) | Under a release root that ambiguity produces a `PYTHONPATH` entry pointing **outside** the release, which silently defeats pinning. Must be one variable with one meaning first. |
| B4 | **The `autobot_shared` symlink is absolute** | `update-all-nodes.yml:405, 417, 791, 1554, 1595` | Inside a release it escapes to the live tree (§1.4). Prerequisite. |
| B5 | **The venv lives inside the deployed component dir** and `_COMPONENT_PIP_PATHS` hardcodes two absolute literals per component | `roles/backend/tasks/main.yml:812-818`; `api/code_sync.py:1595-1604` | Forces the shared-state move (§10 M2) and requires those literals to become derived. They also violate the no-hardcode rule today. |
| B6 | **Hardcoded deploy destinations outside the resolve chokepoint** | `code_sync.py:1822` (`/opt/autobot/constraints/`), `:1858` (`_get_deploy_base()`) | They are writers too, and they are not covered by a guard on `_rsync_local_cmd`. §1.5 resolves them, but only if they are converted in the same change. |
| B7 | **Self-restart never returns** — `_restart_component_services` (`:2477`) and `_restart_pending` (`:1732`) | `api/code_sync.py` | The flip must be complete *and* `fsync`ed before the self-restart is issued (§3.3); ordering here is not stylistic. |
| B8 | **PR #15556 is open and touches `api/code_sync.py`, `api/health.py`, the ratchet baselines and `ARCHITECTURE_EXCEPTIONS.md`** | not yet in `Dev_new_gui` | It lands the `slm_frontend_build.py` staged-build extraction this design cites as precedent, and it moves the same baselines B1 constrains. Sequence behind it or expect conflicts in exactly the files with the tightest budget. |

---

## 16. Answers to #15092's acceptance criteria

- **AC1** — drift-resolve **can** build and flip a release and should; refusing it during an incident
  is worse than the problem. Mechanism in §4.3 (`cp -al` from the current release, rsync the one
  component into the copy, verify, rename, flip, restart). It shares the publisher with the playbook
  end to end.
- **AC2** — T2: assert on the **resolved** destination, under `releases/<id>` and not under a
  resolved `current`.
- **AC3** — T3: the contrast mutation is a fixture path `<ROOT>/current/autobot-backend/releases/pending`,
  which contains the substring `releases` and is nested inside the live tree. A substring check
  passes it; T2 fails it. A second mutation points the destination at the compat symlink.
- **AC4** — this document is the recorded decision. The release scheme closes the defect **category**
  only because all six writers move together; that is stated in §0 and enforced by §14's
  "must land atomically" list.
