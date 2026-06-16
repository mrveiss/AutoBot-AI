// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { spawnSync } from "node:child_process";
import { fileURLToPath } from "node:url";
import { dirname, join } from "node:path";
import { describe, it, expect } from "vitest";

const __dirname = dirname(fileURLToPath(import.meta.url));
const RUNNER = join(__dirname, "..", "..", "canonical_check.mjs");
const FIXTURES = join(__dirname, "fixtures");

function run(...args) {
  return spawnSync("node", [RUNNER, ...args], { encoding: "utf-8" });
}

describe("frontend canonical-check runner", () => {
  it("exits 0 on clean file", () => {
    const r = run("--files", join(FIXTURES, "negative.ts"));
    expect(r.status).toBe(0);
  });

  it("warns on console.log but exits 0 (severity=warn)", () => {
    const r = run("--files", join(FIXTURES, "positive.ts"));
    expect(r.status).toBe(0);
    expect(r.stderr).toContain("fe-console-log-smoke");
  });

  it("--format json emits a JSON array", () => {
    const r = run("--files", join(FIXTURES, "positive.ts"), "--format", "json");
    expect(r.stdout.trim().startsWith("[")).toBe(true);
    expect(r.stdout).toContain("fe-console-log-smoke");
  });

  it("--explain prints rule metadata", () => {
    const r = run("--explain", "fe-console-log-smoke");
    expect(r.status).toBe(0);
    expect(r.stdout).toContain("fe-console-log-smoke");
  });

  it("--explain unknown rule exits 2", () => {
    const r = run("--explain", "no-such-rule");
    expect(r.status).toBe(2);
  });
});
