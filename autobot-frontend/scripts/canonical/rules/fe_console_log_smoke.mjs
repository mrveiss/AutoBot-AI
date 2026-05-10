import { readFile } from "node:fs/promises";

import { makeDiagnostic } from "../diagnostic.mjs";

export const RULE_ID = "fe-console-log-smoke";
export const ISSUE = "#7458";
export const SEVERITY = "warn";
export const TARGETS = ["autobot-frontend/src", "autobot-frontend/scripts/canonical/__tests__/fixtures"];
export const DESCRIPTION = "console.log() in frontend code — pipeline smoke-test rule";
export const FIX_HINT = "Use the canonical logger from @/utils/logger";

const PATTERN = /\bconsole\.log\s*\(/;
const WAIVER = /\/\/\s*canonical:\s*ignore\s+fe-console-log-smoke\b/;

export async function check(filePath) {
  let text;
  try {
    text = await readFile(filePath, "utf-8");
  } catch {
    return [];
  }
  const lines = text.split(/\r?\n/);
  const diagnostics = [];
  lines.forEach((line, idx) => {
    if (PATTERN.test(line) && !WAIVER.test(line)) {
      diagnostics.push(makeDiagnostic({
        ruleId: RULE_ID,
        issue: ISSUE,
        severity: SEVERITY,
        file: filePath,
        line: idx + 1,
        col: line.search(PATTERN),
        message: "console.log() in production code — use logger",
        snippet: line.trim().slice(0, 120),
        fixHint: FIX_HINT,
      }));
    }
  });
  return diagnostics;
}
