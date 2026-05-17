// Mirror of tools/lint/canonical/diagnostic.py
const VALID_SEVERITIES = new Set(["block", "warn", "audit"]);

export function makeDiagnostic({
  ruleId, issue, severity, file, line, col, message, snippet,
  fixHint = "", autoFixable = false,
}) {
  if (!VALID_SEVERITIES.has(severity)) {
    throw new Error(`severity must be one of [block, warn, audit], got ${severity}`);
  }
  return Object.freeze({
    rule_id: ruleId,
    issue,
    severity,
    file: String(file),
    line,
    col,
    message,
    snippet,
    fix_hint: fixHint,
    auto_fixable: autoFixable,
  });
}
