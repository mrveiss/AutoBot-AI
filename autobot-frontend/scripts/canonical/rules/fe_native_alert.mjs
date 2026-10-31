// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readFile } from "node:fs/promises";

import { makeDiagnostic } from "../diagnostic.mjs";

export const RULE_ID = "fe-native-alert";
export const ISSUE = "#19903";
//: `block`: the count is zero, so any hit is a new native alert(). The
//: vocabulary is block | warn | audit.
export const SEVERITY = "block";
export const TARGETS = ["autobot-frontend/src", "autobot-slm-frontend/src"];
export const DESCRIPTION =
  "a native alert() in either app -- it blocks the thread, cannot be themed, translated or dismissed, and is invisible to the toast stack";
export const FIX_HINT =
  "Use useToast().showToast(message, type) from @/composables/useToast, or the app's confirm dialog where the alert gated an irreversible action";

//: `\balert(` exactly as the issue's acceptance grep spells it, so window.alert(
//: is caught and showAlert( / dismissAlert( are not.
const PATTERN = /\balert\s*\(/;
const WAIVER = /canonical:\s*ignore\s+fe-native-alert\b/;
//: A comment line that talks about "an alert (" is prose, not a call.
const COMMENT_LINE = /^\s*(?:\*|\/\/|\/\*|<!--)/;
//: Tests may stub or assert on alert; the grep excludes them too.
const TEST_FILE = /(?:\.test\.[cm]?[jt]s$|\/__tests__\/)/;

export async function check(filePath) {
  if (TEST_FILE.test(filePath.split("\\").join("/"))) return [];
  let text;
  try {
    text = await readFile(filePath, "utf-8");
  } catch {
    return [];
  }
  const diagnostics = [];
  text.split(/\r?\n/).forEach((line, idx) => {
    if (PATTERN.test(line) && !COMMENT_LINE.test(line) && !WAIVER.test(line)) {
      diagnostics.push(makeDiagnostic({
        ruleId: RULE_ID,
        issue: ISSUE,
        severity: SEVERITY,
        file: filePath,
        line: idx + 1,
        col: line.search(PATTERN),
        message: "native alert() -- use a toast, or the confirm dialog if it gated an action",
        snippet: line.trim().slice(0, 120),
        fixHint: FIX_HINT,
      }));
    }
  });
  return diagnostics;
}
