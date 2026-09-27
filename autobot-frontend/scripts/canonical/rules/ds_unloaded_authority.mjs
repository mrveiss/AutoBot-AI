// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readdir, readFile } from "node:fs/promises";
import { join } from "node:path";

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
 * Whether anything in the two frontends imports `basename`.
 *
 * The rule reads the import graph itself rather than taking it from the
 * harness: `check(filePath)` is called with one argument, so a rule that
 * needed repo-wide context passed in would get `undefined` and return no
 * diagnostics -- a rule that cannot answer, reporting the same clean result as
 * a rule that found nothing.
 *
 * A substring test over both spellings, not a resolver: a stylesheet reaches
 * the browser through `@import './x.css'` in another stylesheet OR through
 * `import './x.css'` in an entry module, and a resolver that understood only
 * one would report the other as dead.
 */
async function isImportedAnywhere(basename, root) {
  // Anchored on a path boundary. An unanchored substring made `tokens.css`
  // match `design-tokens.css`, which IS imported -- so the unloaded file read
  // as loaded and the rule reported nothing. The two names differ by a prefix
  // and that is exactly the pair this rule exists to tell apart.
  const needle = new RegExp(`['"][^'"]*(?:^|/)${basename.replace(".", "\\.")}['"]`);
  const stack = ["autobot-frontend/src", "autobot-slm-frontend/src"];
  while (stack.length) {
    const rel = stack.pop();
    let entries;
    try {
      entries = await readdir(join(root, rel), { withFileTypes: true });
    } catch {
      continue;
    }
    for (const e of entries) {
      if (e.name === "node_modules" || e.name.startsWith(".")) continue;
      const child = `${rel}/${e.name}`;
      if (e.isDirectory()) {
        stack.push(child);
        continue;
      }
      if (!/\.(css|ts|mjs|js|vue)$/.test(e.name) || e.name === basename) continue;
      let text;
      try {
        text = await readFile(join(root, child), "utf-8");
      } catch {
        continue;
      }
      if (needle.test(text)) return true;
    }
  }
  return false;
}

export async function check(filePath) {
  let text;
  try {
    text = await readFile(filePath, "utf-8");
  } catch {
    return [];
  }
  if (!CLAIMS_AUTHORITY.test(text) || WAIVER.test(text)) return [];

  const basename = filePath.split("/").pop();
  if (await isImportedAnywhere(basename, repoRoot())) return [];

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
