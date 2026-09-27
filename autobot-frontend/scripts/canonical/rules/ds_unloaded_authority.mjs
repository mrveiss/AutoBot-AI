// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readdir, readFile } from "node:fs/promises";
import { dirname, join, resolve } from "node:path";

import { makeDiagnostic } from "../diagnostic.mjs";
import { repoRoot } from "../registry.mjs";

export const RULE_ID = "ds-unloaded-authority";
export const ISSUE = "#14785";
//: `block`, because a stylesheet that names itself canonical and never loads
//: misdirects the next person standardising tokens. The vocabulary is
//: block | warn | audit -- `error` is rejected by makeDiagnostic, so a rule
//: labelled that way crashes the run rather than reporting.
export const SEVERITY = "block";
export const TARGETS = ["autobot-frontend/src/assets", "autobot-slm-frontend/src/assets"];

//: This rule reads stylesheets. Without declaring it the harness would hand it
//: only .ts/.vue/.mjs/.js and it would never see a CSS file at all.
export const EXTENSIONS = [".css"];
export const DESCRIPTION =
  "a stylesheet that claims to be the canonical token source but is imported by nothing";
export const FIX_HINT =
  "Import it, fold it into the loaded source, or delete it — a file that names itself canonical and never loads is the worst possible signpost for the next person standardising tokens";

/** Wording that asserts this file is the token authority. */
const CLAIMS_AUTHORITY = /canonical\s+(?:css\s+)?design\s+tokens|design\s+tokens?\s+canonical|master\s+design\s+tokens|primary\s+reference\s+for\s+all\s+design\s+tokens|single\s+source\s+of\s+truth/i;

const WAIVER = /\/\*\s*canonical:\s*ignore\s+ds-unloaded-authority\b/;

/**
 * Whether any file in the two frontends imports the stylesheet at `targetAbs`.
 *
 * Import specifiers are RESOLVED against the importing file's directory and
 * compared as absolute paths. Two earlier versions got this wrong in opposite
 * directions, which is why it is done properly rather than with a pattern:
 *
 *   - an unanchored substring matched `design-tokens.css` when looking for
 *     `tokens.css`, so the unloaded file read as loaded -- and telling those
 *     two apart is this rule's entire job;
 *   - anchoring on a preceding `/` then missed a legitimate same-directory
 *     `@import "tokens.css"`, and could still match a different `tokens.css`
 *     in another directory.
 *
 * Resolution has neither failure: `./tokens.css` from `assets/` and
 * `../assets/tokens.css` from `assets/css/` both resolve to the same file, and
 * a same-named file elsewhere resolves to a different one.
 */
//: The keyword is captured because it decides what a BARE specifier means.
//: In CSS, `@import "tokens.css"` is relative to the importing stylesheet. In
//: JavaScript, a bare specifier is a package. Treating both the same way is
//: what made the resolved version miss a legitimate same-directory import.
const SPECIFIER = /(@import\s+(?:url\()?|from\s+|import\s+)['"]([^'"]+)['"]/g;

export const isImportedForTest = (t, r) => isImportedAnywhere(t, r);

async function isImportedAnywhere(targetAbs, root) {
  const roots = ["autobot-frontend/src", "autobot-slm-frontend/src"];
  const stack = roots.map((r) => [r, true]);
  while (stack.length) {
    const [rel, isRoot] = stack.pop();
    let entries;
    try {
      entries = await readdir(join(root, rel), { withFileTypes: true });
    } catch (err) {
      // ENOENT on a TOP-LEVEL target means the tree is absent, which
      // `unreachableTargets` already reports -- skipping it is not a silent
      // loss. Anything else is a directory that exists and could not be read,
      // and that must not shrink the audit into a clean result.
      if (err.code === "ENOENT" && isRoot) continue;
      throw new Error(`cannot read ${rel}: ${err.message}`);
    }
    for (const e of entries) {
      if (e.name === "node_modules" || e.name.startsWith(".")) continue;
      const child = `${rel}/${e.name}`;
      if (e.isDirectory()) {
        stack.push([child, false]);
        continue;
      }
      if (!/\.(css|ts|mjs|js|vue)$/.test(e.name)) continue;
      const abs = join(root, child);
      if (abs === targetAbs) continue;
      let text;
      try {
        text = await readFile(abs, "utf-8");
      } catch (err) {
        throw new Error(`cannot read ${child}: ${err.message}`);
      }
      for (const [, keyword, spec] of text.matchAll(SPECIFIER)) {
        const isCssImport = keyword.trimStart().startsWith("@import");
        const relativeish = spec.startsWith(".") || spec.startsWith("/") || isCssImport;
        if (!relativeish && !spec.startsWith("@/")) continue;
        const from = spec.startsWith("@/")
          ? join(root, "autobot-frontend/src", spec.slice(2))
          : resolve(dirname(abs), spec);
        if (from === targetAbs) return true;
      }
    }
  }
  return false;
}

export async function check(filePath) {
  let text;
  try {
    text = await readFile(filePath, "utf-8");
  } catch (err) {
    // `[]` here is "this stylesheet is fine", returned for a stylesheet nobody
    // read. That is the exact reading this harness exists to make impossible,
    // and it was sitting in the one function that does the reading. The two
    // traversal paths above already throw for this; so does this now.
    throw new Error(`${RULE_ID}: cannot read ${filePath}: ${err.message}`);
  }
  if (!CLAIMS_AUTHORITY.test(text) || WAIVER.test(text)) return [];

  const basename = filePath.split("/").pop();
  if (await isImportedAnywhere(resolve(filePath), repoRoot())) return [];

  const lines = text.split(/\r?\n/);
  const line = lines.findIndex((l) => CLAIMS_AUTHORITY.test(l));
  return [
    makeDiagnostic({
      ruleId: RULE_ID,
      issue: ISSUE,
      severity: SEVERITY,
      file: filePath,
      line: line >= 0 ? line + 1 : 1,
      col: 0,
      message: `${basename} claims to be the canonical token source and no file imports it`,
      snippet: (lines[line] || "").trim().slice(0, 120),
      fixHint: FIX_HINT,
    }),
  ];
}
