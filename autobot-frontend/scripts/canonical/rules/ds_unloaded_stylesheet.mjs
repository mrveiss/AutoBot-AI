// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readFile } from "node:fs/promises";
import { resolve } from "node:path";

import { makeDiagnostic } from "../diagnostic.mjs";
import { repoRoot } from "../registry.mjs";
import { importEdges, importedBy } from "./ds_unloaded_authority.mjs";

//: One walk of both trees per process, not one per stylesheet checked.
let edgesOnce = null;

export const RULE_ID = "ds-unloaded-stylesheet";
export const ISSUE = "#17613";
//: `block`: a stylesheet nothing imports is live-looking CSS that never reaches
//: a browser. assets/main.css held the RTL overrides, a phone-width header rule
//: and the load-failure banner three views use, and none of it rendered.
export const SEVERITY = "block";
export const TARGETS = ["autobot-frontend/src/assets", "autobot-slm-frontend/src/assets"];
export const EXTENSIONS = [".css"];
export const DESCRIPTION = "a stylesheet under assets/ that no file imports";
export const FIX_HINT =
  "Import it from the entry that loads the app's CSS, fold its rules into a loaded stylesheet, or delete it after proving each rule dead. Do not import it blind: its rules were written assuming it never loaded";

//: `_template.css` is documentation: the copy-me file for a new theme.
//: Exemptions are named with their reason, never by omission.
const EXEMPT_BASENAMES = new Map([
  ["_template.css", "copy-me template for a new theme; documented as not loaded"],
]);

const WAIVER = /\/\*\s*canonical:\s*ignore\s+ds-unloaded-stylesheet\b/;

export const exemptionsForTest = () => new Map(EXEMPT_BASENAMES);

export async function check(filePath) {
  let text;
  try {
    text = await readFile(filePath, "utf-8");
  } catch (err) {
    throw new Error(`${RULE_ID}: cannot read ${filePath}: ${err.message}`);
  }
  const basename = filePath.split("/").pop();
  if (EXEMPT_BASENAMES.has(basename) || WAIVER.test(text)) return [];
  //: One hop: imported by ANY file under either src tree. A chain that starts at
  //: another unloaded file reads as loaded; the entries that load CSS are few and
  //: reviewed, so the gap is the next layer of this rule, not hidden here.
  edgesOnce ??= importEdges(repoRoot());
  if (importedBy(await edgesOnce, resolve(filePath))) return [];
  return [
    makeDiagnostic({
      ruleId: RULE_ID,
      issue: ISSUE,
      severity: SEVERITY,
      file: filePath,
      line: 1,
      col: 0,
      message: `${basename} is imported by no file, so none of its rules reach a browser`,
      snippet: basename,
      fixHint: FIX_HINT,
    }),
  ];
}
