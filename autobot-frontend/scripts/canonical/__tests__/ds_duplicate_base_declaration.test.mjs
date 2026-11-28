// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import * as rule from "../rules/ds_duplicate_base_declaration.mjs";
import { collectTargetFiles, repoRoot } from "../registry.mjs";

/** A throwaway `assets/` tree from { "css/a.css": "..." }. */
async function tree(files) {
  const root = join(await mkdtemp(join(tmpdir(), "dupbase-")), "assets");
  for (const [rel, body] of Object.entries(files)) {
    const p = join(root, rel);
    await mkdir(join(p, ".."), { recursive: true });
    await writeFile(p, body, "utf-8");
  }
  return root;
}

describe("ds-duplicate-base-declaration (#14785)", () => {
  it("TRIPS: a token declared on :root in two stylesheets", async () => {
    const root = await tree({
      "css/design-tokens.css": ":root { --bg-primary: #000; }\n",
      "styles/theme.css": ":root {\n  --bg-primary: #fff;\n}\n",
    });
    expect(await rule.check(join(root, "css/design-tokens.css"))).toEqual([]);
    const found = await rule.check(join(root, "styles/theme.css"));
    expect(found).toHaveLength(1);
    expect(found[0].severity).toBe("block");
    expect(found[0].line).toBe(2);
    expect(found[0].message).toContain("--bg-primary");
    expect(found[0].message).toContain("design-tokens.css");
  });

  it("TRIPS: a bare :root hiding inside a theme selector list", async () => {
    const root = await tree({
      "css/design-tokens.css": ":root { --bg-primary: #000; }\n",
      "css/themes/dark.css": '[data-theme="dark"],\n:root { --bg-primary: #111; }\n',
    });
    expect(await rule.check(join(root, "css/themes/dark.css"))).toHaveLength(1);
  });

  it("TRIPS: a tailwind @theme name that is also a :root token", async () => {
    const root = await tree({
      "css/design-tokens.css": ":root { --radius: 4px; }\n",
      "tailwind.css": "@theme {\n  --radius: 8px;\n}\n",
    });
    expect(await rule.check(join(root, "tailwind.css"))).toHaveLength(1);
  });

  it("TRIPS: the same token twice in one context of the same file", async () => {
    const root = await tree({ "css/design-tokens.css": ":root { --x: 1px; }\n:root { --x: 2px; }\n" });
    expect(await rule.check(join(root, "css/design-tokens.css"))).toHaveLength(1);
  });

  it("PASSES: per-theme overrides behind attribute selectors and media queries", async () => {
    const root = await tree({
      "css/design-tokens.css": ":root { --bg-primary: #000; }\n",
      "css/themes/light.css":
        '[data-theme="light"] { --bg-primary: #fff; }\n@media (prefers-color-scheme: light) {\n  :root:not([data-theme="dark"]) { --bg-primary: #fff; }\n}\n',
      "css/themes/ember.css": '[data-theme-variant="ember"]:root { --bg-primary: #fed; }\n',
    });
    for (const f of ["css/design-tokens.css", "css/themes/light.css", "css/themes/ember.css"]) {
      expect(await rule.check(join(root, f))).toEqual([]);
    }
  });

  it("PASSES: one token restated for @supports in the owner file", async () => {
    const root = await tree({
      "css/design-tokens.css":
        ":root { --c: #3b82f6; }\n@supports (color: oklch(0 0 0)) {\n  :root { --c: oklch(62% 0.19 260); }\n}\n",
    });
    expect(await rule.check(join(root, "css/design-tokens.css"))).toEqual([]);
  });

  it("PASSES: a ; or } inside a string or url() is not structure", async () => {
    const root = await tree({
      "a.css": ':root { --i: url("data:image/svg+xml;base64,AA}"); --j: 1px; }\n',
      "b.css": ":root { --k: 2px; }\n",
    });
    expect(await rule.check(join(root, "a.css"))).toEqual([]);
    expect(rule.declarations(':root { --i: url("data:x;y}"); --j: 1px; }').map((d) => d.name)).toEqual(["--i", "--j"]);
  });

  it("honours its waiver", async () => {
    const root = await tree({
      "css/design-tokens.css": ":root { --x: 1px; }\n",
      "other.css": "/* canonical: ignore ds-duplicate-base-declaration */\n:root { --x: 2px; }\n",
    });
    expect(await rule.check(join(root, "other.css"))).toEqual([]);
  });

  it("the live tree has exactly one base declaration site per token name", async () => {
    const files = (await collectTargetFiles([rule])).filter((f) => f.endsWith(".css"));
    // A list this short means the walk found nothing, not that the tree is clean.
    expect(files.length).toBeGreaterThan(8);
    const live = await rule.baseSites(join(repoRoot(), "autobot-frontend/src/assets"));
    expect(live.size).toBeGreaterThan(500);
    const offenders = [...live].filter(([, l]) => rule.surplus(l).length > 0).map(([n]) => n);
    expect(offenders).toEqual([]);
    for (const f of files) expect(await rule.check(f)).toEqual([]);
  });
});
