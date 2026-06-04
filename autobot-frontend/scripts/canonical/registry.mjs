import { readdir } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REQUIRED_KEYS = ["RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT", "check"];

export async function discoverRules(rulesDir = join(__dirname, "rules")) {
  let entries;
  try {
    entries = await readdir(rulesDir, { withFileTypes: true });
  } catch {
    return [];
  }
  const rules = [];
  for (const entry of entries) {
    if (!entry.isFile() || !entry.name.endsWith(".mjs") || entry.name.startsWith("_")) continue;
    const url = pathToFileURL(join(rulesDir, entry.name));
    const mod = await import(url.href);
    if (REQUIRED_KEYS.every((k) => k in mod)) {
      rules.push(mod);
    }
  }
  return rules;
}

export async function runRules(rules, files) {
  const diagnostics = [];
  for (const file of files) {
    for (const rule of rules) {
      diagnostics.push(...(await rule.check(file)));
    }
  }
  return diagnostics;
}
