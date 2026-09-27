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

describe("--all walks the TARGETS trees (#17571)", () => {
  it("reports violations the whole tree contains, not zero", () => {
    // Before this change --all satisfied the "pass something" check and then
    // filtered an empty list, so it printed `0 violations` over a tree it had
    // never opened -- indistinguishable from a clean tree, which is the exact
    // failure the canonical rules exist to catch.
    const r = run("--all", "--format", "json");
    const found = JSON.parse(r.stdout);
    expect(Array.isArray(found)).toBe(true);
    expect(found.length).toBeGreaterThan(0);
  });

  it("refuses to report a clean run when nothing matched", async () => {
    const { collectTargetFiles } = await import("../registry.mjs");
    // A rule whose TARGETS name nothing must not yield a green run.
    const files = await collectTargetFiles([
      { RULE_ID: "x", TARGETS: ["does/not/exist"], EXTENSIONS: [".ts"] },
    ]);
    expect(files).toEqual([]);
  });
});

describe("TARGETS and EXTENSIONS are honoured (#17571)", () => {
  it("a rule does not see a file outside its TARGETS", async () => {
    const { ruleAppliesTo } = await import("../registry.mjs");
    const rule = { RULE_ID: "x", TARGETS: ["autobot-frontend/src"] };
    expect(ruleAppliesTo(rule, "autobot-frontend/src/a.ts")).toBe(true);
    expect(ruleAppliesTo(rule, "autobot-slm-frontend/src/a.ts")).toBe(false);
  });

  it("a prefix match is not a tree match", async () => {
    const { ruleAppliesTo } = await import("../registry.mjs");
    // `autobot-frontend/srcx` starts with `autobot-frontend/src` as a string.
    const rule = { RULE_ID: "x", TARGETS: ["autobot-frontend/src"] };
    expect(ruleAppliesTo(rule, "autobot-frontend/srcx/a.ts")).toBe(false);
  });

  it("a rule declaring EXTENSIONS sees only those", async () => {
    const { ruleAppliesTo } = await import("../registry.mjs");
    const cssRule = { RULE_ID: "c", TARGETS: ["autobot-frontend/src"], EXTENSIONS: [".css"] };
    expect(ruleAppliesTo(cssRule, "autobot-frontend/src/a.css")).toBe(true);
    expect(ruleAppliesTo(cssRule, "autobot-frontend/src/a.ts")).toBe(false);
  });

  it("a rule without EXTENSIONS keeps the default set and never sees CSS", async () => {
    const { ruleAppliesTo } = await import("../registry.mjs");
    const rule = { RULE_ID: "x", TARGETS: ["autobot-frontend/src"] };
    expect(ruleAppliesTo(rule, "autobot-frontend/src/a.ts")).toBe(true);
    expect(ruleAppliesTo(rule, "autobot-frontend/src/a.css")).toBe(false);
  });
});

describe("a rule pointing at nothing is reported, not skipped (#17571)", () => {
  it("names the unreachable target", async () => {
    const { unreachableTargets } = await import("../registry.mjs");
    const missing = await unreachableTargets([
      { RULE_ID: "ghost", TARGETS: ["autobot-frontend/does-not-exist"] },
    ]);
    expect(missing).toEqual([{ ruleId: "ghost", target: "autobot-frontend/does-not-exist" }]);
  });

  it("finds nothing to report for a target that exists", async () => {
    const { unreachableTargets } = await import("../registry.mjs");
    expect(await unreachableTargets([{ RULE_ID: "ok", TARGETS: ["autobot-frontend/src"] }])).toEqual([]);
  });
});

describe("the unloaded-authority rule (#14785)", () => {
  it("blocks on a stylesheet that claims canonicality and is imported by nothing", () => {
    const r = run("--all", "--format", "json");
    const found = JSON.parse(r.stdout);
    const hit = found.filter((d) => d.rule_id === "ds-unloaded-authority");
    expect(hit.length).toBeGreaterThan(0);
    expect(hit[0].severity).toBe("block");
    expect(hit[0].file).toContain("tokens.css");
    // A `block` diagnostic must fail the run; previously nothing did.
    expect(r.status).toBe(1);
  });
});
