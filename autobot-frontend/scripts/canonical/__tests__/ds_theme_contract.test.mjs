// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { mkdir, mkdtemp, writeFile } from "node:fs/promises";
import { tmpdir } from "node:os";
import { join } from "node:path";
import { describe, expect, it } from "vitest";

import { compare, themeNames } from "../rules/ds_theme_contract.mjs";

describe("ds-theme-contract (#14775)", () => {
  it("reads names from @theme blocks only, comments excluded", () => {
    const css = `:root { --color-autobot-no: 1; }
      /* @theme { --color-autobot-comment: x; } */
      @theme {
        --color-autobot-a: var(--a);
        --color-autobot-b: var(--b);
        --font-x: y;
      }`;
    expect([...themeNames(css)].sort()).toEqual(["--color-autobot-a", "--color-autobot-b"]);
  });

  it("the two apps define exactly the same --color-autobot-* names", async () => {
    const { reference, missingInSlm, extraInSlm } = await compare();
    // Control: not an empty comparison.
    expect(reference.size).toBeGreaterThan(80);
    expect(missingInSlm).toEqual([]);
    expect(extraInSlm).toEqual([]);
  });

  it("TRIPS on a name one app lacks, in either direction", async () => {
    const root = await mkdtemp(join(tmpdir(), "contract-"));
    await mkdir(join(root, "autobot-frontend/src/assets"), { recursive: true });
    await mkdir(join(root, "autobot-slm-frontend/src/assets/styles"), { recursive: true });
    await writeFile(
      join(root, "autobot-frontend/src/assets/tailwind.css"),
      "@theme {\n --color-autobot-a: var(--a);\n --color-autobot-b: var(--b);\n}\n",
      "utf-8",
    );
    await writeFile(
      join(root, "autobot-slm-frontend/src/assets/styles/x.css"),
      "@theme {\n --color-autobot-a: var(--a);\n --color-autobot-c: var(--c);\n}\n",
      "utf-8",
    );
    const r = await compare(root);
    expect(r.missingInSlm).toEqual(["--color-autobot-b"]);
    expect(r.extraInSlm).toEqual(["--color-autobot-c"]);
  });
});
