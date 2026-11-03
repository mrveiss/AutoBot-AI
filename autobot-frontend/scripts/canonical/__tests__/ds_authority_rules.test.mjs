// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { existsSync, mkdtempSync, readFileSync, rmSync, writeFileSync } from "node:fs";
import { tmpdir } from "node:os";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

import { collectTargetFiles, repoRoot, ruleAppliesTo, runRules } from "../registry.mjs";
import { kitComponentFiles, readBaseline } from "../kit.mjs";
import * as second from "../rules/ds_second_kit_component.mjs";
import * as imports from "../rules/ds_noncanonical_primitive_import.mjs";
import {
  AUTHORITY,
  authorityProblems,
  designSystemOwner,
} from "../../../../libs/autobot-ui/src/authority/designSystemAuthority.mjs";

const here = dirname(fileURLToPath(import.meta.url));
const fx = (...p) => join(here, "fixtures", "ds_17571", ...p);
const root = repoRoot();

describe("ds-second-kit-component (#17571)", () => {
  it("TRIPS on an app file named like a kit component (the control)", async () => {
    const found = await second.check(fx("fail", "BaseButton.vue"));
    expect(found).toHaveLength(1);
    expect(found[0].severity).toBe("block");
  });

  it("honours the waiver on line 1 only, not one further down the file", async () => {
    const dir = mkdtempSync(join(tmpdir(), "ds-second-"));
    const marker = "canonical: ignore ds-second-kit-component";
    const waived = join(dir, "BaseButton.vue");
    writeFileSync(waived, `<!-- ${marker} -->\n<template />\n`, "utf-8");
    expect(await second.check(waived)).toEqual([]);
    const buried = join(dir, "BaseCard.vue");
    writeFileSync(buried, `<template />\n<!-- ${marker} -->\n`, "utf-8");
    expect(await second.check(buried)).toHaveLength(1);
    rmSync(dir, { recursive: true });
  });

  it("PASSES on a differently named file", async () => {
    expect(await second.check(fx("pass", "ReleaseNotesButton.vue"))).toEqual([]);
  });

  it("covers both apps, and reads the kit listing from the tree", () => {
    expect(ruleAppliesTo(second, "autobot-slm-frontend/src/components/X.vue")).toBe(true);
    expect(ruleAppliesTo(second, "autobot-frontend/src/components/X.vue")).toBe(true);
    expect(kitComponentFiles().has("BaseButton.vue")).toBe(true);
  });
});

describe("ds-noncanonical-primitive-import (#17571)", () => {
  it("TRIPS on a local path and on a dynamic import (the control)", async () => {
    const found = await imports.check(fx("fail", "imports.ts"));
    expect(found.map((d) => d.line)).toEqual([1, 2]);
  });

  it("PASSES on the kit specifier, an unrelated component and a waived line", async () => {
    expect(await imports.check(fx("pass", "imports.ts"))).toEqual([]);
  });
});

describe("ds-noncanonical-primitive-import matcher (#17571)", () => {
  const lines = (text) => imports.findHits(text).map((h) => h.idx + 1);

  it("TRIPS on an import split across lines, reported at the specifier line", () => {
    expect(lines("import {\n  A,\n} from\n  './BaseCard.vue'\n")).toEqual([3]);
    expect(lines("import BaseCard\n  from './BaseCard.vue'")).toEqual([2]);
  });

  it("honours the per-line waiver on a multi-line import's specifier line", () => {
    expect(lines("import {\n  A,\n} from './BaseCard.vue' // canonical: ignore ds-noncanonical-primitive-import")).toEqual([]);
  });

  it("honours the waiver on the specifier line of a split import", () => {
    expect(lines("import {\n  A,\n} from\n  './BaseCard.vue' // canonical: ignore ds-noncanonical-primitive-import")).toEqual([]);
  });

  it("ignores an import-looking string, and reports kit deep paths and look-alike packages", () => {
    expect(lines("const s = \"import('./BaseCard.vue')\"")).toEqual([]);
    expect(lines("const s = 'x from ./BaseCard.vue'")).toEqual([]);
    expect(lines("import B from '@autobot/ui/src/components/BaseCard.vue'")).toEqual([1]);
    expect(lines("import B from '@autobot/ui-fork/BaseCard.vue'")).toEqual([1]);
  });

  it("ignores // and /* */ comments, trailing and multi-line", () => {
    expect(lines("// import X from './BaseCard.vue'")).toEqual([]);
    expect(lines("const a = 1 // import X from './BaseCard.vue'")).toEqual([]);
    expect(lines("/*\n import X from './BaseCard.vue'\n*/")).toEqual([]);
    expect(lines("/* a */ import X from './BaseCard.vue'")).toEqual([1]);
  });

  it("does not treat // inside a string as a comment", () => {
    expect(lines("const u = 'http://x.test'; import X from './BaseCard.vue'")).toEqual([1]);
    expect(lines('const u = "https://x.test/a"\nimport X from "./BaseCard.vue"')).toEqual([2]);
  });
});

describe("a file that cannot be read is never a clean pass (#17571)", () => {
  it("both rules rethrow, so main().catch exits 2", async () => {
    await expect(imports.check(fx("missing", "x.ts"))).rejects.toThrow(/ENOENT/);
    await expect(second.check(fx("missing", "BaseButton.vue"))).rejects.toThrow(/ENOENT/);
  });
});

describe("the baselines are frozen and tight (#17571)", () => {
  it("the whole tree is clean against both baselines -- main stays green", async () => {
    const files = await collectTargetFiles([second, imports]);
    expect(files.length).toBeGreaterThan(100);
    expect(await runRules([second, imports], files)).toEqual([]);
  });

  it("every second-component entry still names a kit-named file, so it can only shrink", () => {
    const kit = kitComponentFiles();
    for (const path of readBaseline("ds_second_kit_component.txt").keys()) {
      expect(existsSync(join(root, path)), `${path} no longer exists -- delete its baseline line`).toBe(true);
      expect(kit.has(path.split("/").pop())).toBe(true);
    }
  });

  it("every import entry records exactly the hits still in the file", () => {
    for (const [path, count] of readBaseline("ds_noncanonical_primitive_import.txt")) {
      expect(existsSync(join(root, path)), `${path} no longer exists -- delete its baseline line`).toBe(true);
      const hits = imports.findHits(readFileSync(join(root, path), "utf-8")).length;
      expect(hits, `${path}: lower the baseline to ${hits}`).toBe(count);
    }
  });
});

describe("the design-system authority registry (#17571)", () => {
  it("is well-formed: issue links, stated reasons, owner or note", () => {
    expect(authorityProblems()).toEqual([]);
  });

  it("every declared owner and exception path exists on disk", () => {
    for (const [id, e] of Object.entries(AUTHORITY)) {
      for (const p of [e.owner, ...(e.exceptions ?? []).map((x) => x.path)].filter(Boolean)) {
        expect(existsSync(join(root, p)), `${id}: ${p} does not exist`).toBe(true);
      }
    }
  });

  it("fails loudly on an unknown concept and on one with no owner yet", () => {
    expect(() => designSystemOwner("carousel")).toThrow(/not declared/);
    expect(() => designSystemOwner("toString")).toThrow(/not declared in AUTHORITY/);
    expect(() => designSystemOwner("constructor")).toThrow(/not declared in AUTHORITY/);
    expect(() => designSystemOwner("graph-renderer")).toThrow(/no canonical owner/);
    expect(designSystemOwner("button")).toBe("libs/autobot-ui/src/components/BaseButton.vue");
  });

  it("rejects an exception without a reason (the control)", () => {
    const bad = { x: { status: "canonical", owner: "a", issue: "#1", exceptions: [{ path: "p", reason: " " }] } };
    expect(authorityProblems(bad)).toHaveLength(1);
  });
});
