#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Runs ON the remote test node (#20935). Checks the pushed SHA (ref refs/runs/<job> in the node's mirror) out
# into a private work dir, runs the command, and removes the work dir and the ref on success,
# failure, timeout and every signal (EXIT INT TERM HUP), including the loss of the SSH session. Usage:
#   remote_job.sh <base> <slots> <timeout_s> <ttl_min> <job-id> -- <command...>
# <ttl_min> is derived from the effective --timeout by run.py. Exit: the command's status, 124 timeout, 75 node not provisioned.
set -uo pipefail

base="$1"; slots="$2"; limit="$3"; ttl="$4"; job="$5"; shift 6
mkdir -p "$base" && base=$(cd "$base" && pwd) || exit 1  # absolute: the command runs from the work dir
workdir=""; child=""; cleaned=0
parent=$PPID
mirror="$base/mirror.git"

cleanup() {
  [ "$cleaned" = "1" ] && return
  cleaned=1
  if [ -n "$child" ]; then
    kill -TERM -- "-$child" 2>/dev/null
    sleep 1
    kill -KILL -- "-$child" 2>/dev/null
  fi
  [ -n "$workdir" ] && rm -rf -- "$workdir"
  git --git-dir="$mirror" update-ref -d "refs/runs/$job" 2>/dev/null
}
trap cleanup EXIT
trap 'cleanup; exit 143' INT TERM HUP

sweep_stale() {
  # A run killed with SIGKILL, or with the node's power, leaves its dir. Only a dir that is old by THIS run's ttl
  # and whose liveness lock nobody holds is abandoned: another run may use a longer timeout (and so a longer ttl)
  # than this one, and its lock stays held for as long as the run or any process it started is alive.
  local dir
  for dir in "$base"/runs/*/; do
    [ -d "$dir" ] || continue
    [ -n "$(find "$dir" -maxdepth 0 -mmin "+$ttl" 2>/dev/null)" ] || continue
    # the ref goes with the dir: left behind it keeps the run's objects reachable for git gc
    { (
      flock -n 7 || exit 0
      if git --git-dir="$mirror" update-ref -d "refs/runs/$(basename "$dir" | sed 's/^job\.//')" 2>/dev/null; then
        rm -rf -- "$dir"
      else
        echo "remote_job: could not delete the ref of stale run $(basename "$dir"); its dir stays" >&9
      fi
    ) 7>>"${dir}.live"; } 9>&2 2>/dev/null  # fd 9 keeps the one message visible while the rest stays quiet
  done
}

gc_mirror() {
  # Runs refs/runs/* are deleted per job, so their objects turn unreachable; collect them once a week (git's
  # default 2-week prune grace keeps anything a concurrent job still reads), one collector at a time.
  local stamp="$base/mirror.gc-stamp"
  [ -n "$(find "$stamp" -mtime -7 2>/dev/null)" ] && return 0
  (
    flock -n 8 || exit 0
    git --git-dir="$mirror" gc --quiet 2>/dev/null && touch "$stamp"
  ) 8>>"$base/mirror.gc-lock"
}

take_slot() {
  local i
  mkdir -p "$base/slots"
  while :; do
    session_lost && { cleanup; exit 129; }  # a queued job whose caller left must not take a slot later
    for ((i = 1; i <= slots; i++)); do
      exec 9>>"$base/slots/slot-$i"
      flock -n 9 && { printf 'slot %s of %s\n' "$i" "$slots" >&2; return 0; }
    done
    exec 9>&-
    sleep 2
  done
}

session_lost() {
  # The SSH session is the job's parent; once it vanishes the job is reparented and nobody wants its result.
  # An empty answer (no ps on the node) means the parent is unknown, which is not a lost session.
  local now
  now=$(ps -o ppid= -p $$ 2>/dev/null | tr -d ' ')
  [ -n "$now" ] && [ "$now" != "$parent" ]
}

wait_child() {
  # Polls instead of `wait` so a vanished SSH session ends the run.
  while kill -0 "$child" 2>/dev/null; do
    session_lost && { cleanup; exit 129; }
    sleep 1
  done
  wait "$child"
}

mkdir -p "$base/runs"
{ [ -x "$base/venv/bin/python" ] && [ -d "$mirror" ]; } || { echo "remote test node is not provisioned" >&2; exit 75; }
sweep_stale
gc_mirror
take_slot
workdir="$base/runs/job.$job"; mkdir -p "$workdir/tree"
exec 7>>"$workdir/.live"; flock -n 7  # liveness lock: held until this run and what it started are gone (sweep_stale)
checkout_commit() {
  # A real repository over the mirror's objects (alternates, no copy): the guards read git state, and
  # concurrent jobs share nothing writable. origin/main is the mirror's base branch, as on a developer tree.
  local tree="$workdir/tree"
  git init -q "$tree" || return 1
  printf '%s\n' "$mirror/objects" > "$tree/.git/objects/info/alternates"
  git -C "$tree" update-ref refs/remotes/origin/main "$(git --git-dir="$mirror" rev-parse refs/heads/main)" || return 1
  git -C "$tree" checkout -q --detach "$(git --git-dir="$mirror" rev-parse "refs/runs/$job^{commit}")"
}
checkout_commit || { echo "could not check out the pushed commit" >&2; exit 1; }
cd "$workdir/tree" || exit 1
PATH="$base/venv/bin:$PATH" setsid timeout -k 10 "$limit" "$@" &
child=$!
wait_child
