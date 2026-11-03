// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readFile } from "node:fs/promises";
import { basename } from "node:path";

import { makeDiagnostic } from "../diagnostic.mjs";
import { kitComponentFiles, readBaseline, relPath } from "../kit.mjs";

export const RULE_ID = "ds-second-kit-component";
export const ISSUE = "#17571";
//: `block`: the pre-existing copies are frozen in baselines/ds_second_kit_component.txt,
//: so any hit is a new second implementation.
export const SEVERITY = "block";
export const TARGETS = ["autobot-frontend/src", "autobot-slm-frontend/src"];
export const EXTENSIONS = [".vue"];
export const DESCRIPTION =
  "an app component file with the same name as a component in the shared kit (libs/autobot-ui) -- a second implementation of a declared-canonical primitive";
export const FIX_HINT =
  "Import the kit component from '@autobot/ui' and delete this file, or give the component a name that says how it differs. The owner of each concept is declared in libs/autobot-ui/src/authority/designSystemAuthority.mjs";

const LINE_WAIVER = /canonical:\s*ignore\s+ds-second-kit-component\b/;

export async function check(filePath) {
  const name = basename(filePath);
  if (!kitComponentFiles().has(name)) return [];
  const rel = relPath(filePath);
  if (readBaseline("ds_second_kit_component.txt").has(rel)) return [];
  // A read that throws is rethrown (main().catch exits 2): returning [] would let a
  // run exit 0 without having inspected the file.
  const text = await readFile(filePath, "utf-8");
  if (LINE_WAIVER.test(text)) return [];
  return [
    makeDiagnostic({
      ruleId: RULE_ID,
      issue: ISSUE,
      severity: SEVERITY,
      file: filePath,
      line: 1,
      col: 0,
      message: `${name} already exists in the shared kit -- import it from '@autobot/ui' instead of writing a second one`,
      snippet: rel,
      fixHint: FIX_HINT,
    }),
  ];
}
