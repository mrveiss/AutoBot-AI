// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { execSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { repoRoot, ruleAppliesTo } from "../registry.mjs";
import * as rule from "../rules/ds_z_index_literal.mjs";

async function scratch(name, body) {
  const dir = await mkdtemp(join(tmpdir(), "z-literal-"));
  const file = join(dir, name);
  await writeFile(file, body, "utf-8");
  return file;
}

describe("ds-z-index-literal (#19907)", () => {
  it("TRIPS on a number, a negative, a one-line rule, a token fallback and calc arithmetic", async () => {
    const file = await scratch(
      "a.vue",
      [
        ".a { z-index: 10; }",
        ".b {\n  z-index: -1;\n}",
        ".c { position: fixed; z-index:9999 !important }",
        ".d { z-index: var(--z-tooltip, 9999); }",
        ".e { z-index: calc(var(--z-modal) + 1); }",
      ].join("\n"),
    );
    const found = await rule.check(file);
    expect(found.map((d) => d.line)).toEqual([1, 3, 5, 6, 7]);
    expect(found.every((d) => d.severity === "block")).toBe(true);
  });

  it("PASSES on tokens, keywords and look-alike names", async () => {
    const file = await scratch(
      "b.css",
      [
        ".a { z-index: var(--z-modal); }",
        ".b { z-index: var(--aui-z-raised) !important; }",
        ".c { z-index: auto; }",
        "  --z-10: 10;",
        ".d { max-z-index: 4; }",
        "/* z-index: 5 is documented here */",
        " * z-index: 6",
      ].join("\n"),
    );
    expect(await rule.check(file)).toEqual([]);
  });

  it("honours the line waiver", async () => {
    const file = await scratch("c.vue", ".a { z-index: 3; } /* canonical: ignore ds-z-index-literal */");
    expect(await rule.check(file)).toEqual([]);
  });

  it("waives a recorded file up to its recorded count and reports the excess", async () => {
    const dir = await mkdtemp(join(tmpdir(), "z-waiver-"));
    const rel = "autobot-frontend/src/components/chat/ChatInput.vue";
    await mkdir(join(dir, "autobot-frontend/src/components/chat"), { recursive: true });
    const file = join(dir, rel);
    const { count } = rule.waivedFilesForTest().get(rel);
    await writeFile(file, Array.from({ length: count }, () => ".a { z-index: 1; }").join("\n"), "utf-8");
    expect(await rule.check(file)).toEqual([]);
    await writeFile(file, Array.from({ length: count + 1 }, () => ".a { z-index: 1; }").join("\n"), "utf-8");
    expect((await rule.check(file)).map((d) => d.line)).toEqual([count + 1]);
  });

  it("every waiver names a PR and a positive count", () => {
    for (const [file, w] of rule.waivedFilesForTest()) {
      expect(w.pr, file).toMatch(/^#\d+/);
      expect(w.count, file).toBeGreaterThan(0);
    }
  });

  it("is scoped to both apps and the kit, .vue and .css only", () => {
    expect(ruleAppliesTo(rule, "autobot-frontend/src/views/A.vue")).toBe(true);
    expect(ruleAppliesTo(rule, "autobot-slm-frontend/src/assets/b.css")).toBe(true);
    expect(ruleAppliesTo(rule, "libs/autobot-ui/src/components/C.vue")).toBe(true);
    expect(ruleAppliesTo(rule, "autobot-frontend/src/views/A.ts")).toBe(false);
    expect(ruleAppliesTo(rule, "docs/design/x.css")).toBe(false);
  });

  it("the trees hold no unwaived literal z-index", async () => {
    const files = execSync("git ls-files autobot-frontend/src autobot-slm-frontend/src libs/autobot-ui/src", {
      cwd: repoRoot(),
    })
      .toString()
      .trim()
      .split("\n")
      .filter((f) => ruleAppliesTo(rule, f));
    // Control: the sweep read a real tree, so "no findings" is not "read nothing".
    expect(files.length).toBeGreaterThan(500);
    const found = [];
    for (const f of files) found.push(...(await rule.check(join(repoRoot(), f))));
    expect(found.map((d) => `${d.file}:${d.line}`)).toEqual([]);
  });
});
