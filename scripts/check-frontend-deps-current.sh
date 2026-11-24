#!/usr/bin/env bash
# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
#
# Is a frontend workspace's node_modules the install its package-lock.json
# describes? Reads only; never installs (#22135).
#
# The mtime test pr-preflight.sh used (`package-lock.json` newer than
# `node_modules/.package-lock.json`) misses a tree installed before a dependency
# was added whenever the lockfile's mtime moved for another reason, and it is not
# consulted at all by a bare `npx vitest`. This compares CONTENT: every package
# the lockfile records, transitive ones included, must be present under
# node_modules at that version. reka-ui was absent from a long-lived install this way.
#
# Usage: scripts/check-frontend-deps-current.sh [workspace-dir]   (default: autobot-frontend)
# Exit 0 current; 1 stale (offenders listed, with the one command that fixes it); 2 cannot run.

set -euo pipefail

WS="${1:-autobot-frontend}"
[ -f "$WS/package.json" ] && [ -f "$WS/package-lock.json" ] || { echo "error: no package.json/package-lock.json in $WS" >&2; exit 2; }
command -v node >/dev/null || { echo "error: node not found" >&2; exit 2; }

node -e '
const fs = require("fs"), path = require("path");
const ws = process.argv[1];
const lock = JSON.parse(fs.readFileSync(path.join(ws, "package-lock.json"), "utf-8")).packages || {};
// EVERY locked package, not just the declared ones: a bump that moves only a transitive
// package (an `overrides` entry, a re-resolved subtree) changes the lockfile and nothing in package.json.
// Links and entries with no version are not registry installs; an absent OPTIONAL package is a
// platform skip, not drift (a present one at the wrong version still is).
const entries = Object.entries(lock).filter(([k, v]) => k.startsWith("node_modules/") && v.version && !v.link);
if (entries.length === 0) { console.error("error: " + ws + " lockfile has no installable packages"); process.exit(2); }
const bad = [];
for (const [key, meta] of entries) {
  let have = null;
  try { have = JSON.parse(fs.readFileSync(path.join(ws, key, "package.json"), "utf-8")).version; } catch (e) { /* absent */ }
  if (have === null && meta.optional) continue;
  if (have !== meta.version) bad.push("  " + key.slice("node_modules/".length) + ": installed " + (have || "(absent)") + ", lockfile " + meta.version);
}
if (bad.length) {
  console.log("STALE -- " + ws + "/node_modules does not match its lockfile (" + bad.length + " of " + entries.length + " locked packages):");
  console.log("reconcile it: npm --prefix " + ws + " ci");
  console.log(bad.join("\n"));
  process.exit(1);
}
console.log(ws + "/node_modules matches the lockfile (" + entries.length + " locked packages)");
' "$WS"
