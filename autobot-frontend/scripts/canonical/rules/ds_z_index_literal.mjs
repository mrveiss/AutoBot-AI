// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readFile } from "node:fs/promises";

import { makeDiagnostic } from "../diagnostic.mjs";

export const RULE_ID = "ds-z-index-literal";
export const ISSUE = "#19907";
//: `block`: the tree holds zero unwaived literals, so any hit is a new one.
export const SEVERITY = "block";
export const TARGETS = ["autobot-frontend/src", "autobot-slm-frontend/src", "libs/autobot-ui/src"];
export const EXTENSIONS = [".vue", ".css"];
export const DESCRIPTION =
  "a literal z-index value -- layering is decided by the --z-* / --aui-z-* scale, and a number written in place cannot be compared with the layers around it";
export const FIX_HINT =
  "Use var(--z-*) in the apps or var(--aui-z-*) in the kit (design-tokens.css / libs/autobot-ui/src/tokens/contract.css). For a local stacking tier use --z-raised / --aui-z-raised; add a new token to the scale once, never a number to a file";

//: Files that still hold a literal because an open PR owns them. Recorded by
//: file with the count of literal lines and the PR, so the rule can land while
//: those PRs are open. Remove an entry in the PR that converts the file; a
//: file with MORE literals than recorded is reported again.
const WAIVED_FILES = new Map([
  ["autobot-frontend/src/components/audit/AuditLogTable.vue", { count: 1, pr: "#20000" }],
  ["autobot-frontend/src/components/charts/ImportTreeChart.vue", { count: 3, pr: "#20018" }],
  ["autobot-frontend/src/components/chat/ChatInput.vue", { count: 2, pr: "#19949" }],
  ["autobot-frontend/src/components/chat/MCPPromptTemplatePicker.vue", { count: 1, pr: "#20018" }],
  ["autobot-frontend/src/components/chat/PresetFormBody.vue", { count: 1, pr: "#20018" }],
  ["autobot-frontend/src/components/knowledge/KnowledgeGraph.vue", { count: 2, pr: "#20000" }],
  ["autobot-frontend/src/components/plugins/CapabilityApprovalDialog.vue", { count: 1, pr: "#20018" }],
  ["autobot-frontend/src/views/llc/HeartbeatMonitor.vue", { count: 1, pr: "#20000" }],
  ["autobot-slm-frontend/src/components/monitoring/GrafanaDashboard.vue", { count: 2, pr: "#20018" }],
  ["libs/autobot-ui/src/components/ToastContainer.vue", { count: 1, pr: "#19949" }],
]);

export const waivedFilesForTest = () => new Map(WAIVED_FILES);

const DECLARATION = /(?<![\w-])z-index\s*:\s*([^;}]*)/g;
const LINE_WAIVER = /canonical:\s*ignore\s+ds-z-index-literal\b/;
const COMMENT_LINE = /^\s*(?:\*|\/\/|\/\*|<!--)/;
//: The only tokens a z-index may be built from.
const TOKEN_REF = /var\(\s*--(?:aui-)?z-[\w-]+\s*\)/g;

/** A value is a literal unless every part of it is a z token reference. */
export function isLiteral(value) {
  const rest = value.replace(TOKEN_REF, "").replace(/!important|calc|[()\s]/g, "");
  return /\d/.test(rest) || /var/.test(rest) || /[+*/-]/.test(rest);
}

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
    if (COMMENT_LINE.test(line) || LINE_WAIVER.test(line)) return;
    for (const m of line.matchAll(DECLARATION)) {
      if (isLiteral(m[1])) hits.push({ idx, col: m.index, line });
    }
  });
  return hits.slice(waiver ? waiver.count : 0).map(({ idx, col, line }) =>
    makeDiagnostic({
      ruleId: RULE_ID,
      issue: ISSUE,
      severity: SEVERITY,
      file: filePath,
      line: idx + 1,
      col,
      message: "literal z-index -- use a --z-* / --aui-z-* token",
      snippet: line.trim().slice(0, 120),
      fixHint: FIX_HINT,
    }),
  );
}
