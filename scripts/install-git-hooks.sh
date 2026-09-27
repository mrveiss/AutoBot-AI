#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# install-git-hooks.sh — install AutoBot's git hooks as REAL files (copied),
# never as symlinks into a worktree.
# ============================================================================
#
# Why this exists (Issue #11598):
#   The old tools/git-hooks/install_hooks.sh symlinked each hook into
#   .git/hooks/ pointing at a *worktree* path. When that worktree was deleted
#   the symlink dangled and the hook silently stopped running. On top of that
#   core.hooksPath had been pinned to a machine-specific absolute path, which
#   is neither portable nor the git default.
#
# What this installer guarantees:
#   * Real copied hook files (self-contained) — survive worktree deletion.
#   * Portable — repo root and hooks dir are derived from git, never hardcoded.
#   * core.hooksPath removed whenever it is set at all (#16812) — including a
#     value that already points at the default hooks dir. git behaves the same
#     either way; `pre-commit install` refuses while the key merely exists.
#   * Dangling symlinks in the hooks dir are detected, reported, and replaced.
#   * Idempotent — safe to re-run; a second run is a no-op when up to date.
#   * The installed `pre-commit` runs the branch guard, then dispatches staged
#     files to the `pre-commit` framework binary if it's on PATH (#16923) —
#     see tools/git-hooks/pre-commit for the logic; this installer just copies
#     it verbatim, same as every other managed hook.
#
# Usage:
#   bash scripts/install-git-hooks.sh          # install/refresh hooks
#   HOOKS_DEST=/tmp/x bash scripts/install-git-hooks.sh   # override dest (tests)
#   bash scripts/install-git-hooks.sh --sync pre-push     # #17578, see below
#
# `--sync <hook>...` is the mode the post-checkout and post-merge hooks call.
# It differs from a full run in two ways, both deliberate:
#
#   * it does NOT call normalise_hooks_path. Unsetting core.hooksPath is a
#     config mutation, and a checkout is not the moment to perform one behind
#     the operator's back. A full run still does it.
#   * it is silent unless it actually replaces something. A hook that prints on
#     every checkout is a hook the third person to see it disables.
#
# Why it exists (#17578): hooks are COPIED, not symlinked (#11598), and nothing
# kept .git/hooks/pre-push in step with tools/git-hooks/pre-push. Measured on a
# live checkout: the installed copy was the tracked file as of 4bae334f12, two
# revisions behind, missing #16912's two `could_not_run` branches AND #17035's
# `REPO_ROOT="$PWD"`. The second is why this is not tidiness -- the old spelling
# resolves through `git rev-parse --show-toplevel`, which an inherited GIT_DIR
# outranks, so the running hook could verify a DIFFERENT CHECKOUT than the one
# being pushed.
#
# Related: #4113 (branch guard), #11581, #11593.

set -uo pipefail

# #15246: this repo's own checkouts are all worktrees, and the pre-push hook
# exports GIT_DIR (pointing at the pushing worktree's own git directory) with
# no GIT_WORK_TREE. Every `git` call below would then answer for THAT
# directory instead of wherever this script is actually run from --
# `--show-toplevel` silently returning the wrong root is what made
# repo_tests/git_hooks_installer_test.py install hooks into the live repo
# instead of its throwaway fixture. Unset once, up front, same as
# autobot_shared.paths.scrubbed_git_env() does for the Python side.
unset GIT_DIR GIT_WORK_TREE GIT_COMMON_DIR GIT_INDEX_FILE GIT_OBJECT_DIRECTORY GIT_ALTERNATE_OBJECT_DIRECTORIES

RED='\033[0;31m'; YELLOW='\033[1;33m'; GREEN='\033[0;32m'; CYAN='\033[0;36m'; NC='\033[0m'
# QUIET (set by --sync) suppresses progress, never a change or a problem:
# `changed`, `warn` and `fail` always print. A sync that replaced a stale hook
# must leave a trace, or the drift this mode exists to remove becomes invisible
# in the other direction -- corrected silently, with nobody told it was wrong.
QUIET=""
info()  { [ -n "$QUIET" ] && return 0; printf "${CYAN}[install-hooks]${NC} %s\n" "$*"; }
ok()    { [ -n "$QUIET" ] && return 0; printf "${GREEN}[install-hooks]${NC} %s\n" "$*"; }
changed() { printf "${GREEN}[install-hooks]${NC} %s\n" "$*"; }
warn()  { printf "${YELLOW}[install-hooks WARN]${NC} %s\n" "$*" >&2; }
fail()  { printf "${RED}[install-hooks FAIL]${NC} %s\n" "$*" >&2; }

# Hooks this installer manages. Each name must exist as a real file under
# tools/git-hooks/<name>. commit-msg (#17029) strips co-author trailers and
# rejects a subject without the `<type>(scope): ... (#NNNN)` convention; it was
# a hand-installed local file until then, present on one machine and nowhere else.
MANAGED_HOOKS="pre-commit pre-push commit-msg"

# --sync <hook>... : the subset to bring into step, quietly. Validated against
# MANAGED_HOOKS below, so a typo fails loudly instead of syncing nothing --
# which would read exactly like a clean sync.
SYNC_ONLY=""
# An unknown option must FAIL, never fall through to a full install. #17578's
# own near miss: the hooks live in ONE shared .git/hooks while this installer is
# per worktree, so a hook installed from a tree that has --sync gets invoked
# from trees that do not. An older copy ignored the unknown argument, ran
# `main "$@"`, and performed a full install -- including normalise_hooks_path,
# the config mutation --sync exists to avoid. Observed live: a merge in another
# worktree did exactly that. Failing here kills the class; the hooks also probe
# for support before calling, which handles the older-installer direction.
case "${1:-}" in
    -*)
        if [ "$1" != "--sync" ]; then
            fail "unknown option: $1 (supported: --sync <hook>...)"
            exit 2
        fi
        ;;
esac
if [ "${1:-}" = "--sync" ]; then
    shift
    SYNC_ONLY="$*"
    [ -n "$SYNC_ONLY" ] || { fail "--sync needs at least one hook name"; exit 2; }
    QUIET=1
    for _requested in $SYNC_ONLY; do
        case " $MANAGED_HOOKS " in
            *" $_requested "*) ;;
            *) fail "--sync: '$_requested' is not one of: $MANAGED_HOOKS"; exit 2 ;;
        esac
    done
fi

# --- Locate the repo and its canonical hook templates (portable) -----------
REPO_ROOT="$(git rev-parse --show-toplevel 2>/dev/null || echo "")"
if [ -z "$REPO_ROOT" ]; then
    fail "not inside a git repository"
    exit 1
fi
HOOKS_SRC="$REPO_ROOT/tools/git-hooks"
if [ ! -d "$HOOKS_SRC" ]; then
    fail "hook template directory missing: $HOOKS_SRC"
    exit 1
fi

# --- Resolve the hooks destination (worktree-aware, absolute) --------------
# --git-common-dir points at the MAIN repo's .git even from inside a worktree,
# so hooks land in the shared hooks dir rather than a per-worktree one.
resolve_hooks_dest() {
    if [ -n "${HOOKS_DEST:-}" ]; then
        printf '%s\n' "$HOOKS_DEST"
        return
    fi
    local common_dir
    common_dir="$(git rev-parse --git-common-dir 2>/dev/null || echo "")"
    case "$common_dir" in
        /*) printf '%s/hooks\n' "$common_dir" ;;
        *)  printf '%s/hooks\n' "$(cd "$common_dir" && pwd)" ;;
    esac
}
HOOKS_DEST="$(resolve_hooks_dest)"

# --- Normalise core.hooksPath ----------------------------------------------
# If it is pinned to anything other than the resolved default hooks dir (e.g.
# an absolute machine-specific path — the #11598 bug), unset it so git falls
# back to its default. We only touch the LOCAL repo config, never global.
normalise_hooks_path() {
    local configured
    # --get-all, not --get (#16812): `--get` exits non-zero on a multi-valued
    # key and prints nothing, so a doubled entry read as "unset" and survived.
    configured="$(git config --local --get-all core.hooksPath 2>/dev/null | head -n 1 || true)"
    [ -z "$configured" ] && return 0

    local resolved="$configured"
    case "$configured" in
        /*) : ;;
        *)  resolved="$REPO_ROOT/$configured" ;;
    esac
    # #16812: unset on PRESENCE, not on failing to resolve to the default. This
    # used to `return 0` when the value already pointed at the default hooks
    # dir, on the reasoning that such a key changes nothing. True for git --
    # and fatal for `pre-commit`, which refuses whenever the key exists AT ALL:
    # "Cowardly refusing to install hooks with `core.hooksPath` set". So a
    # redundant key silently disabled every hook in .pre-commit-config.yaml
    # (flake8, autoflake, mypy, the local guards) while looking like hygiene,
    # and the old equal-to-default test scored exactly that state as clean.
    #
    # Removing it is also what #15961 concluded on independent grounds: an
    # override is a `--no-verify` that leaves no trace, and the premise for
    # adding one is false because git already shares hooks with worktrees.
    if [ "$resolved" = "$HOOKS_DEST" ]; then
        warn "core.hooksPath was set to the default hooks dir: $configured"
        warn "  unsetting it — pre-commit refuses to install while the key exists at all (#16812)"
    else
        warn "core.hooksPath was pinned to a non-default path: $configured"
        warn "  unsetting it so git uses the default hooks dir: $HOOKS_DEST"
    fi
    # --unset-all: `--unset` fails on a multi-valued key, and `|| true` would
    # then swallow the failure and leave the key in place.
    git config --local --unset-all core.hooksPath 2>/dev/null || true
}

# --- Replace one hook with the real template file --------------------------
# Detects and clears dangling/foreign symlinks, backs up unmanaged regular
# files, and copies the template verbatim. Idempotent by content.
install_one_hook() {
    local name="$1"
    local src="$HOOKS_SRC/$name"
    local dest="$HOOKS_DEST/$name"

    if [ ! -f "$src" ]; then
        warn "template missing, skipping: $src"
        return 0
    fi

    # Never clobber a pre-commit-FRAMEWORK-managed hook. When `pre-commit
    # install` has written .git/hooks/<name>, that hook already runs the FULL
    # quality suite (black/flake8/mypy/function-length/... AND target-branch-
    # guard). Our standalone is only a FALLBACK for when the `pre-commit`
    # binary isn't installed, so leave the framework hook in place (#11598).
    if [ -f "$dest" ] && [ ! -L "$dest" ] \
        && grep -q "generated by pre-commit" "$dest" 2>/dev/null; then
        warn "$name is managed by the pre-commit framework — leaving it in place"
        warn "  (it already runs target-branch-guard + the full quality suite)"
        return 0
    fi

    if [ -L "$dest" ]; then
        local target; target="$(readlink "$dest" 2>/dev/null || echo "")"
        if [ ! -e "$dest" ]; then
            warn "removing DANGLING symlink: $name -> $target"
        else
            warn "removing symlink (installing a real file instead): $name -> $target"
        fi
        rm -f "$dest"
    elif [ -f "$dest" ]; then
        if cmp -s "$src" "$dest"; then
            chmod +x "$dest" || { fail "failed to chmod +x $dest"; return 1; }
            ok "$name already up to date"
            return 0
        fi
        if ! grep -q "AutoBot" "$dest" 2>/dev/null; then
            local backup="$dest.bak.$(date +%Y%m%d-%H%M%S)"
            mv "$dest" "$backup"
            warn "backed up existing unmanaged $name -> $(basename "$backup")"
        fi
    fi

    cp "$src" "$dest" || { fail "failed to copy $name into $dest"; return 1; }
    chmod +x "$dest" || { fail "failed to chmod +x $dest"; return 1; }
    # `changed`, not `ok`: a replacement is reported even under --sync.
    changed "installed $name"
}

main() {
    info "repo root:   $REPO_ROOT"
    info "hooks dest:  $HOOKS_DEST"
    mkdir -p "$HOOKS_DEST"
    # #17578: a --sync run touches hooks only. See the note at the top for why
    # config normalisation is not a side effect of a checkout.
    [ -z "$SYNC_ONLY" ] && normalise_hooks_path
    local rc=0
    for hook in ${SYNC_ONLY:-$MANAGED_HOOKS}; do
        install_one_hook "$hook" || rc=1
    done
    if [ -n "$SYNC_ONLY" ]; then
        [ "$rc" -ne 0 ] && fail "hook sync failed for one or more of: $SYNC_ONLY"
        return "$rc"
    fi
    echo ""
    if [ "$rc" -ne 0 ]; then
        fail "one or more hooks failed to install"
        return 1
    fi
    ok "done. Bypass a hook only when you must: git commit/push --no-verify"
}

main "$@"
