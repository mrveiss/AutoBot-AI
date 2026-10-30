// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { execSync } from "node:child_process";
import { mkdtemp, mkdir, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { repoRoot, ruleAppliesTo } from "../registry.mjs";
import * as rule from "../rules/fe_native_alert.mjs";

async function scratch(name, body) {
  const dir = await mkdtemp(join(tmpdir(), "native-alert-"));
  const file = join(dir, name);
  await writeFile(file, body, "utf-8");
  return file;
}

describe("fe-native-alert (#19903)", () => {
  it("TRIPS on alert(, window.alert( and a templated alert", async () => {
    const file = await scratch(
      "a.vue",
      ["alert('x')", "  window.alert(msg)", "alert(`File ${name}`)"].join("\n"),
    );
    const found = await rule.check(file);
    expect(found.map((d) => d.line)).toEqual([1, 2, 3]);
    expect(found.every((d) => d.severity === "block")).toBe(true);
  });

  it("PASSES on names that merely contain the word", async () => {
    const file = await scratch(
      "b.ts",
      ["showAlert('x')", " * an inline alert (role) is not a call", "// alert (note)", "dismissAlert(id)", "const alerts = []", "// uses alert for emphasis", "<BaseAlert variant=\"error\" />"].join("\n"),
    );
    expect(await rule.check(file)).toEqual([]);
  });

  it("honours the line waiver", async () => {
    const file = await scratch("c.ts", "alert('x') // canonical: ignore fe-native-alert");
    expect(await rule.check(file)).toEqual([]);
  });

  it("skips test files, which may stub alert", async () => {
    const dir = await mkdtemp(join(tmpdir(), "native-alert-"));
    await mkdir(join(dir, "__tests__"), { recursive: true });
    const spec = join(dir, "x.test.ts");
    const nested = join(dir, "__tests__", "y.ts");
    await writeFile(spec, "alert('x')", "utf-8");
    await writeFile(nested, "alert('x')", "utf-8");
    expect(await rule.check(spec)).toEqual([]);
    expect(await rule.check(nested)).toEqual([]);
  });

  it("is scoped to both app source trees", () => {
    expect(ruleAppliesTo(rule, "autobot-frontend/src/views/A.vue")).toBe(true);
    expect(ruleAppliesTo(rule, "autobot-slm-frontend/src/views/B.vue")).toBe(true);
    expect(ruleAppliesTo(rule, "libs/autobot-ui/src/C.vue")).toBe(false);
  });

  it("both app trees hold zero native alerts", async () => {
    const files = execSync("git ls-files autobot-frontend/src autobot-slm-frontend/src", { cwd: repoRoot() })
      .toString()
      .trim()
      .split("\n")
      .filter((f) => ruleAppliesTo(rule, f));
    // Control: the sweep read a real tree, so "no findings" is not "read nothing".
    expect(files.length).toBeGreaterThan(500);
    const found = [];
    for (const f of files) found.push(...(await rule.check(join(repoRoot(), f))));
    expect(found.map((d) => `${d.file}:${d.line}`)).toEqual([]);
  }, 60_000);
});
