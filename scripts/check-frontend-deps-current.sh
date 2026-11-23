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
# declared in package.json must be present under node_modules at the version the
# lockfile records. reka-ui was absent from a long-lived install this way.
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
const pkg = JSON.parse(fs.readFileSync(path.join(ws, "package.json"), "utf-8"));
const lock = JSON.parse(fs.readFileSync(path.join(ws, "package-lock.json"), "utf-8")).packages || {};
const declared = { ...pkg.dependencies, ...pkg.devDependencies };
// Local workspace links are not registry installs and carry no lockfile version.
const names = Object.keys(declared).filter((n) => !/^(file|link|workspace):/.test(declared[n]));
if (names.length === 0) { console.error("error: " + ws + " declares no dependencies"); process.exit(2); }
const bad = [];
for (const n of names) {
  const want = (lock["node_modules/" + n] || {}).version;
  let have = null;
  try { have = JSON.parse(fs.readFileSync(path.join(ws, "node_modules", n, "package.json"), "utf-8")).version; } catch (e) { /* absent */ }
  if (have !== want) bad.push("  " + n + ": installed " + (have || "(absent)") + ", lockfile " + (want || "(unlocked)"));
}
if (bad.length) {
  console.log("STALE -- " + ws + "/node_modules does not match its lockfile (" + bad.length + " of " + names.length + "):");
  console.log(bad.join("\n"));
  console.log("reconcile it: npm --prefix " + ws + " ci");
  process.exit(1);
}
console.log(ws + "/node_modules matches the lockfile (" + names.length + " declared packages)");
' "$WS"
