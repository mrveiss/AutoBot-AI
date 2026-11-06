#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# Runs ON the remote test node (#20935). Checks the pushed SHA (ref refs/runs/<job> in the node's mirror) out
# into a private work dir, runs the command, and removes the work dir and the ref on success,
# failure, timeout and every signal (EXIT INT TERM HUP), including the loss of the SSH session. Usage:
#   remote_job.sh <base> <slots> <timeout_s> <ttl_min> <job-id> -- <command...>
# Exit: the command's status, 124 timeout, 75 node not provisioned.
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
  # A run killed with SIGKILL, or with the node's power, leaves its dir; no live run outlives the ttl.
  find "$base/runs" -mindepth 1 -maxdepth 1 -type d -mmin "+$ttl" -exec rm -rf -- {} + 2>/dev/null
}

take_slot() {
  local i
  mkdir -p "$base/slots"
  while :; do
    for ((i = 1; i <= slots; i++)); do
      exec 9>>"$base/slots/slot-$i"
      flock -n 9 && { printf 'slot %s of %s\n' "$i" "$slots" >&2; return 0; }
    done
    exec 9>&-
    sleep 2
  done
}

wait_child() {
  # Polls instead of `wait` so a vanished SSH session (parent reparented) ends the run.
  while kill -0 "$child" 2>/dev/null; do
    [ "$(ps -o ppid= -p $$ | tr -d ' ')" = "$parent" ] || { cleanup; exit 129; }
    sleep 1
  done
  wait "$child"
}

mkdir -p "$base/runs"
{ [ -x "$base/venv/bin/python" ] && [ -d "$mirror" ]; } || { echo "remote test node is not provisioned" >&2; exit 75; }
sweep_stale
take_slot
workdir="$base/runs/job.$job"; mkdir -p "$workdir/tree"
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
