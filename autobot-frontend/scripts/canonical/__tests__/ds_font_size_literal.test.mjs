// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { execSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { repoRoot, ruleAppliesTo } from "../registry.mjs";
import * as rule from "../rules/ds_font_size_literal.mjs";

async function scratch(name, body) {
  const dir = await mkdtemp(join(tmpdir(), "fs-literal-"));
  const file = join(dir, name);
  await writeFile(file, body, "utf-8");
  return file;
}

describe("ds-font-size-literal (#19907)", () => {
  it("TRIPS on rem, px, pt, a one-line rule, a token fallback and calc arithmetic", async () => {
    const file = await scratch(
      "a.vue",
      [
        ".a { font-size: 0.875rem; }",
        ".b {\n  font-size: 13px;\n}",
        ".c { color: red; font-size:12pt !important }",
        ".d { font-size: var(--text-sm, 0.875rem); }",
        ".e { font-size: calc(var(--text-sm) + 2px); }",
      ].join("\n"),
    );
    const found = await rule.check(file);
    expect(found.map((d) => d.line)).toEqual([1, 3, 5, 6, 7]);
    expect(found.every((d) => d.severity === "block")).toBe(true);
  });

  it("PASSES on tokens, relative units, keywords and look-alike names", async () => {
    const file = await scratch(
      "b.css",
      [
        ".a { font-size: var(--text-sm); }",
        ".b { font-size: var(--aui-text-xs) !important; }",
        ".c { font-size: inherit; }",
        ".d { font-size: 0.85em; }",
        ".e { font-size: 90%; }",
        ".f { font-size: calc(var(--aui-avatar-size) * 0.375); }",
        "  --font-size-xs: 0.75rem;",
        "  --btn-font-size: 14px;",
        ".g { line-height: 1.5; }",
        "/* font-size: 13px is documented here */",
        " * font-size: 14px",
      ].join("\n"),
    );
    expect(await rule.check(file)).toEqual([]);
  });

  it("honours the line waiver", async () => {
    const file = await scratch("c.vue", ".a { font-size: 13px; } /* canonical: ignore ds-font-size-literal */");
    expect(await rule.check(file)).toEqual([]);
  });

  it("waives a recorded file up to its recorded count and reports the excess", async () => {
    const dir = await mkdtemp(join(tmpdir(), "fs-waiver-"));
    const [rel, { count }] = [...rule.waivedFilesForTest()][0];
    await mkdir(join(dir, rel, ".."), { recursive: true });
    const file = join(dir, rel);
    const body = (n) => Array.from({ length: n }, () => ".a { font-size: 13px; }").join("\n");
    await writeFile(file, body(count), "utf-8");
    expect(await rule.check(file)).toEqual([]);
    await writeFile(file, body(count + 1), "utf-8");
    expect((await rule.check(file)).map((d) => d.line)).toEqual([count + 1]);
  });

  it("every waiver names an issue and a positive count", () => {
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

  it("the trees hold no unwaived literal font-size, and no waiver is stale", async () => {
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
    // Control: the waivers name files that exist, so the sweep is not passing on an empty match.
    const tracked = new Set(files);
    for (const f of rule.waivedFilesForTest().keys()) expect(tracked.has(f), f).toBe(true);
  });
});
