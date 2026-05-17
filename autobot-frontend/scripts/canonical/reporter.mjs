export function toPretty(diagnostics) {
  if (diagnostics.length === 0) return "canonical-check: 0 violations\n";
  const counts = { block: 0, warn: 0, audit: 0 };
  for (const d of diagnostics) counts[d.severity]++;
  const lines = [
    `canonical-check: ${diagnostics.length} violations (block=${counts.block}, warn=${counts.warn}, audit=${counts.audit})`,
  ];
  const grouped = new Map();
  for (const d of diagnostics) {
    if (!grouped.has(d.file)) grouped.set(d.file, []);
    grouped.get(d.file).push(d);
  }
  for (const [file, ds] of [...grouped.entries()].sort()) {
    for (const d of ds.sort((a, b) => a.line - b.line || a.col - b.col)) {
      lines.push(`  ${file}:${d.line}  ${d.rule_id}  (${d.issue}) [${d.severity}]`);
      lines.push(`    ${d.message}`);
    }
  }
  return lines.join("\n") + "\n";
}

export function toJson(diagnostics) {
  return JSON.stringify(diagnostics, null, 2);
}
