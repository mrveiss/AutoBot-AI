// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { repoRoot } from "../registry.mjs";
import { check } from "../rules/ds_unloaded_stylesheet.mjs";
import { exemptionsForTest } from "../rules/ds_unloaded_stylesheet.mjs";
import { isImportedAnywhere } from "../rules/ds_unloaded_authority.mjs";
import { execSync } from "node:child_process";

describe("ds-unloaded-stylesheet (#17613)", () => {
  it("every stylesheet under both assets trees is imported, bar the named exemptions", async () => {
    const files = execSync("git ls-files autobot-frontend/src/assets autobot-slm-frontend/src/assets", {
      cwd: repoRoot(),
    })
      .toString()
      .trim()
      .split("\n")
      .filter((f) => f.endsWith(".css"));
    // Control: the list is not empty, so "no findings" is not "read nothing".
    expect(files.length).toBeGreaterThan(10);
    const found = [];
    for (const f of files) found.push(...(await check(join(repoRoot(), f))));
    expect(found.map((d) => d.file)).toEqual([]);
  });

  it("TRIPS: a stylesheet nothing imports; PASSES once something does", async () => {
    // check() resolves against the real repo root, so use the primitive on a
    // throwaway root the way the authority rule's own tests do.
    const root = await mkdtemp(join(tmpdir(), "unloaded-"));
    const src = join(root, "autobot-frontend/src");
    await mkdir(join(src, "assets"), { recursive: true });
    const orphan = join(src, "assets/orphan.css");
    await writeFile(orphan, ".x { color: red; }\n", "utf-8");
    await writeFile(join(src, "main.ts"), "import './assets/other.css'\n", "utf-8");
    expect(await isImportedAnywhere(orphan, root)).toBe(false);
    await writeFile(join(src, "main.ts"), "import './assets/orphan.css'\n", "utf-8");
    expect(await isImportedAnywhere(orphan, root)).toBe(true);
  });

  it("TRIPS through check(): a stylesheet no file in the repo imports", async () => {
    const dir = await mkdtemp(join(tmpdir(), "orphan-"));
    const file = join(dir, "orphan.css");
    await writeFile(file, ".x { color: red; }\n", "utf-8");
    const found = await check(file);
    expect(found).toHaveLength(1);
    expect(found[0].severity).toBe("block");
    expect(found[0].message).toContain("orphan.css");
  });

  it("names its exemptions with a reason", () => {
    for (const [name, reason] of exemptionsForTest()) {
      expect(name.endsWith(".css")).toBe(true);
      expect(reason.length).toBeGreaterThan(10);
    }
  });
});
