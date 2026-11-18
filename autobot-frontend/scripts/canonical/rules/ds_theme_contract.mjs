// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readFile, readdir } from "node:fs/promises";
import { join } from "node:path";

import { makeDiagnostic } from "../diagnostic.mjs";
import { repoRoot } from "../registry.mjs";

export const RULE_ID = "ds-theme-contract";
export const ISSUE = "#14775";
//: `block`: a component written against `bg-autobot-bg-card` or `text-autobot-error`
//: must mean the same in both apps. A name one app lacks renders nothing there and
//: no build step says so.
export const SEVERITY = "block";
//: The SLM stylesheets are the files checked; the user frontend's tailwind.css is
//: the reference. It is listed so a change there re-runs the rule, and checking it
//: reports nothing against itself.
export const TARGETS = ["autobot-slm-frontend/src/assets/styles", "autobot-frontend/src/assets/tailwind.css"];
export const EXTENSIONS = [".css"];
export const DESCRIPTION = "a --color-autobot-* name the user frontend's @theme defines and the SLM's does not (or the reverse)";
export const FIX_HINT =
  "Add the missing alias to the other app's @theme, with that app's own value behind the var(). The names are the contract; the values are each app's identity (#14775)";

const WAIVER = /\/\*\s*canonical:\s*ignore\s+ds-theme-contract\b/;
const REFERENCE = "autobot-frontend/src/assets/tailwind.css";
const SLM_STYLES = "autobot-slm-frontend/src/assets/styles";
const NAME = /(--color-autobot-[\w-]+)\s*:/g;

const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, "");

/** The `--color-autobot-*` names declared inside @theme blocks of `text`. */
export function themeNames(text) {
  const names = new Set();
  const css = stripComments(text);
  for (const m of css.matchAll(/@theme\b[^{]*\{([^{}]*)\}/g)) {
    for (const n of m[1].matchAll(NAME)) names.add(n[1]);
  }
  return names;
}

async function slmNames(root) {
  const dir = join(root, SLM_STYLES);
  const names = new Set();
  for (const e of await readdir(dir, { withFileTypes: true })) {
    if (!e.isFile() || !e.name.endsWith(".css")) continue;
    for (const n of themeNames(await readFile(join(dir, e.name), "utf-8"))) names.add(n);
  }
  return names;
}

export async function compare(root = repoRoot()) {
  const reference = themeNames(await readFile(join(root, REFERENCE), "utf-8"));
  const slm = await slmNames(root);
  return {
    reference,
    missingInSlm: [...reference].filter((n) => !slm.has(n)).sort(),
    extraInSlm: [...slm].filter((n) => !reference.has(n)).sort(),
  };
}

export async function check(filePath) {
  if (filePath.endsWith(REFERENCE)) return [];
  const text = await readFile(filePath, "utf-8");
  if (WAIVER.test(text)) return [];
  // Reported once, on the file that holds the SLM's @theme, so a stylesheet that
  // has no @theme in it is not blamed for the set it is not part of.
  if (themeNames(text).size === 0) return [];
  const { reference, missingInSlm, extraInSlm } = await compare();
  // Control: an empty reference would make "nothing missing" mean "nothing read".
  if (reference.size < 20) throw new Error(`${RULE_ID}: read only ${reference.size} reference names from ${REFERENCE}`);
  return [...missingInSlm.map((n) => [n, "defined by the user frontend, missing here"]), ...extraInSlm.map((n) => [n, "defined here, missing in the user frontend"])].map(
    ([name, why]) =>
      makeDiagnostic({
        ruleId: RULE_ID,
        issue: ISSUE,
        severity: SEVERITY,
        file: filePath,
        line: 1,
        col: 0,
        message: `${name}: ${why}`,
        snippet: name,
        fixHint: FIX_HINT,
      }),
  );
}
