// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { execSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { repoRoot, ruleAppliesTo } from "../registry.mjs";
import * as rule from "../rules/ds_second_font_scale.mjs";

async function scratch(name, body) {
  const dir = await mkdtemp(join(tmpdir(), "font-scale-"));
  const file = join(dir, name);
  await writeFile(file, body, "utf-8");
  return file;
}

describe("ds-second-font-scale (#20390)", () => {
  it("TRIPS on a definition, a use, a fallback and a .ts reference", async () => {
    const file = await scratch(
      "a.css",
      [
        ":root { --font-size-sm: 0.8rem; }",
        ".a { font-size: var(--font-size-xl); }",
        ".b { font-size: var(--font-size-2xl, 1.5rem); }",
        "const t = 'var(--font-size-base)'",
      ].join("\n"),
    );
    const found = await rule.check(file);
    expect(found.map((d) => d.line)).toEqual([1, 2, 3, 4]);
    expect(found.every((d) => d.severity === "block")).toBe(true);
  });

  it("PASSES on --text-*, differently named tokens and the line waiver", async () => {
    const file = await scratch(
      "b.vue",
      [
        ".a { font-size: var(--text-sm); }",
        ".b { font-size: var(--btn-font-size-md); }",
        ".c { font-size: var(--aui-font-size-sm); }",
        ".d { font-size: var(--font-size-xs); } /* canonical: ignore ds-second-font-scale */",
      ].join("\n"),
    );
    expect(await rule.check(file)).toEqual([]);
  });

  it("waives a recorded file up to its recorded count and reports the excess", async () => {
    const dir = await mkdtemp(join(tmpdir(), "font-waiver-"));
    const rel = "autobot-frontend/src/views/llc/CompanySelectorView.vue";
    await mkdir(join(dir, "autobot-frontend/src/views/llc"), { recursive: true });
    const file = join(dir, rel);
    const { count } = rule.waivedFilesForTest().get(rel);
    const line = ".a { font-size: var(--font-size-xs); }";
    await writeFile(file, Array.from({ length: count }, () => line).join("\n"), "utf-8");
    expect(await rule.check(file)).toEqual([]);
    await writeFile(file, Array.from({ length: count + 1 }, () => line).join("\n"), "utf-8");
    expect((await rule.check(file)).map((d) => d.line)).toEqual([count + 1]);
  });

  it("every waiver names a PR and a positive count", () => {
    for (const [file, w] of rule.waivedFilesForTest()) {
      expect(w.pr, file).toMatch(/^#\d+/);
      expect(w.count, file).toBeGreaterThan(0);
    }
  });

  it("is scoped to the main app's .vue, .css and .ts", () => {
    expect(ruleAppliesTo(rule, "autobot-frontend/src/views/A.vue")).toBe(true);
    expect(ruleAppliesTo(rule, "autobot-frontend/src/assets/b.css")).toBe(true);
    expect(ruleAppliesTo(rule, "autobot-frontend/src/c.ts")).toBe(true);
    expect(ruleAppliesTo(rule, "autobot-slm-frontend/src/assets/b.css")).toBe(false);
  });

  it("the main app holds no unwaived --font-size-* reference", async () => {
    const files = execSync("git ls-files autobot-frontend/src", { cwd: repoRoot() })
      .toString()
      .trim()
      .split("\n")
      .filter((f) => ruleAppliesTo(rule, f));
    const found = (await Promise.all(files.map((f) => rule.check(join(repoRoot(), f))))).flat();
    expect(found.map((d) => `${d.file}:${d.line}`)).toEqual([]);
  });
});
