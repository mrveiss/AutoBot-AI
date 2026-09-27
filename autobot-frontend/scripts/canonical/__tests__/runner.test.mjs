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
  // Synthetic, not the live tree. The live instance -- assets/tokens.css --
  // is removed in this same change, so a test asserting "the repo contains a
  // blocking violation" would pass only until the backlog drained and then
  // fail for the best possible reason. RATCHET_BASELINES.md names this: a
  // guard whose population can reach zero tests itself with fixtures.
  it("blocks a stylesheet that claims canonicality and is imported by nothing", async () => {
    const { mkdtemp, writeFile } = await import("node:fs/promises");
    const { tmpdir } = await import("node:os");
    const rule = await import("../rules/ds_unloaded_authority.mjs");

    const dir = await mkdtemp(join(tmpdir(), "canon-"));
    const file = join(dir, "orphan.css");
    await writeFile(file, "/* Canonical CSS Design Tokens */\n:root { --x: 1px; }\n", "utf-8");

    const found = await rule.check(file);
    expect(found).toHaveLength(1);
    expect(found[0].severity).toBe("block");
    expect(found[0].message).toContain("no file imports it");
  });

  it("says nothing about a stylesheet that makes no such claim", async () => {
    const { mkdtemp, writeFile } = await import("node:fs/promises");
    const { tmpdir } = await import("node:os");
    const rule = await import("../rules/ds_unloaded_authority.mjs");

    const dir = await mkdtemp(join(tmpdir(), "canon-"));
    const file = join(dir, "ordinary.css");
    await writeFile(file, "/* component styles */\n.x { color: red; }\n", "utf-8");

    expect(await rule.check(file)).toEqual([]);
  });

  it("honours its waiver", async () => {
    const { mkdtemp, writeFile } = await import("node:fs/promises");
    const { tmpdir } = await import("node:os");
    const rule = await import("../rules/ds_unloaded_authority.mjs");

    const dir = await mkdtemp(join(tmpdir(), "canon-"));
    const file = join(dir, "waived.css");
    await writeFile(
      file,
      "/* canonical: ignore ds-unloaded-authority */\n/* Canonical CSS Design Tokens */\n",
      "utf-8",
    );

    expect(await rule.check(file)).toEqual([]);
  });

  it("the tree is clean of blocking violations", () => {
    // The live assertion, stated as the outcome rather than as the detector's
    // proof: after removing assets/tokens.css nothing blocks, so the gate added
    // to canonical-audit.yml lands green rather than reddening main on arrival.
    const r = run("--all");
    expect(r.status).toBe(0);
  });
});

describe("a run that inspects nothing is refused, not reported clean (#17608 review)", () => {
  it("--files reports what it skipped and exits 0 — it is a filter", () => {
    // The pre-commit hook passes every changed autobot-frontend/**/*.{ts,vue,mjs,js},
    // including this harness, which no rule targets. Skipping those is correct.
    // Refusing here instead broke the hook on the commit implementing it.
    const r = run("--files", join(__dirname, "..", "..", "canonical_check.mjs"));
    expect(r.status).toBe(0);
    expect(r.stderr).toContain("none inside any rule's TARGETS");
    expect(r.stderr).toContain("nothing to check");
  });

  it("still exits 0 for a covered file with no violations", () => {
    expect(run("--files", join(FIXTURES, "negative.ts")).status).toBe(0);
  });
});

describe("import specifiers are resolved, not pattern-matched (#17608 review)", () => {
  async function ruleOn(files, targetName) {
    const { mkdtemp, writeFile, mkdir } = await import("node:fs/promises");
    const { tmpdir } = await import("node:os");
    const root = await mkdtemp(join(tmpdir(), "canon-res-"));
    for (const [rel, body] of Object.entries(files)) {
      const abs = join(root, rel);
      await mkdir(dirname(abs), { recursive: true });
      await writeFile(abs, body, "utf-8");
    }
    return { root, target: join(root, targetName) };
  }

  it("a same-directory @import counts as loaded", async () => {
    // The anchored pattern required a slash and missed this.
    const { isImportedForTest } = await import("../rules/ds_unloaded_authority.mjs");
    // Asserted, not guarded: `return` here made all three tests pass without
    // creating a fixture or resolving a single specifier if the export were
    // ever dropped -- a green suite over an uninspected rule, which is the very
    // reading the rule under test exists to prevent.
    expect(typeof isImportedForTest).toBe("function");
    const { root, target } = await ruleOn(
      {
        "autobot-frontend/src/assets/tokens.css": "/* Canonical CSS Design Tokens */",
        "autobot-frontend/src/assets/index.css": '@import "tokens.css";',
      },
      "autobot-frontend/src/assets/tokens.css",
    );
    expect(await isImportedForTest(target, root)).toBe(true);
  });

  it("a same-named file in another directory does NOT count", async () => {
    const { isImportedForTest } = await import("../rules/ds_unloaded_authority.mjs");
    expect(typeof isImportedForTest).toBe("function");
    const { root, target } = await ruleOn(
      {
        "autobot-frontend/src/assets/tokens.css": "/* Canonical CSS Design Tokens */",
        "autobot-frontend/src/other/tokens.css": "/* unrelated */",
        "autobot-frontend/src/other/index.css": '@import "./tokens.css";',
      },
      "autobot-frontend/src/assets/tokens.css",
    );
    expect(await isImportedForTest(target, root)).toBe(false);
  });

  it("a prefixed name is not a match", async () => {
    // The unanchored substring matched design-tokens.css for tokens.css.
    const { isImportedForTest } = await import("../rules/ds_unloaded_authority.mjs");
    expect(typeof isImportedForTest).toBe("function");
    const { root, target } = await ruleOn(
      {
        "autobot-frontend/src/assets/tokens.css": "/* Canonical CSS Design Tokens */",
        "autobot-frontend/src/assets/design-tokens.css": "/* real one */",
        "autobot-frontend/src/assets/index.css": '@import "./design-tokens.css";',
      },
      "autobot-frontend/src/assets/tokens.css",
    );
    expect(await isImportedForTest(target, root)).toBe(false);
  });
});
