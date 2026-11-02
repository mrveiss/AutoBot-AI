// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readFile } from "node:fs/promises";

import { makeDiagnostic } from "../diagnostic.mjs";

export const RULE_ID = "ds-second-font-scale";
export const ISSUE = "#20390";
//: `block`: the tree holds no unwaived reference, so any hit is a new one.
export const SEVERITY = "block";
export const TARGETS = ["autobot-frontend/src"];
export const EXTENSIONS = [".vue", ".css", ".ts"];
export const DESCRIPTION =
  "a --font-size-* token (definition or use) -- --text-* is the one font-size scale, and the font-size preference drives it through --font-scale";
export const FIX_HINT =
  "Use var(--text-xs|sm|base|lg|xl|2xl|3xl) from design-tokens.css. A theme that redefines a --text-* step multiplies it by var(--font-scale). Never add a second scale";

//: Files an open PR holds, recorded by file with the count of references and
//: the PR. Remove the entry in the PR that converts the file; a file with MORE
//: references than recorded is reported again.
const WAIVED_FILES = new Map([["autobot-frontend/src/views/llc/CompanySelectorView.vue", { count: 1, pr: "#20388" }]]);

export const waivedFilesForTest = () => new Map(WAIVED_FILES);

//: Only the scale steps. Differently named tokens (--btn-font-size-md) fail the
//: leading lookbehind; the undefined --font-size-md is tracked by its own baseline.
const SCALE_TOKEN = /(?<![\w-])--font-size-(?:xs|sm|base|lg|xl|2xl|3xl)(?![\w-])/g;
const LINE_WAIVER = /canonical:\s*ignore\s+ds-second-font-scale\b/;

export async function check(filePath) {
  let text;
  try {
    text = await readFile(filePath, "utf-8");
  } catch {
    return [];
  }
  const norm = filePath.split("\\").join("/");
  const waiver = [...WAIVED_FILES].find(([f]) => norm.endsWith(f))?.[1];
  const hits = [];
  text.split(/\r?\n/).forEach((line, idx) => {
    if (LINE_WAIVER.test(line)) return;
    for (const m of line.matchAll(SCALE_TOKEN)) hits.push({ idx, col: m.index, line });
  });
  return hits.slice(waiver ? waiver.count : 0).map(({ idx, col, line }) =>
    makeDiagnostic({
      ruleId: RULE_ID,
      issue: ISSUE,
      severity: SEVERITY,
      file: filePath,
      line: idx + 1,
      col,
      message: "--font-size-* is removed -- use the matching --text-* token",
      snippet: line.trim().slice(0, 120),
      fixHint: FIX_HINT,
    }),
  );
}
