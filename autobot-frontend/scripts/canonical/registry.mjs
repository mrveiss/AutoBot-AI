// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readdir, stat } from "node:fs/promises";
import { fileURLToPath, pathToFileURL } from "node:url";
import { dirname, join, relative, resolve } from "node:path";

const __dirname = dirname(fileURLToPath(import.meta.url));
const REQUIRED_KEYS = ["RULE_ID", "ISSUE", "SEVERITY", "TARGETS", "DESCRIPTION", "FIX_HINT", "check"];

/** Extensions a rule sees when it does not declare its own `EXTENSIONS`. */
export const DEFAULT_EXTENSIONS = [".ts", ".vue", ".mjs", ".js"];

/** The repository root: two levels above `autobot-frontend/scripts/`. */
export const repoRoot = () => join(__dirname, "..", "..", "..");

/** Whether `file` lies inside `target`, both repo-root-relative POSIX paths. */
function under(file, target) {
  const t = target.replace(/\/+$/, "");
  return file === t || file.startsWith(`${t}/`);
}

/** The extensions `rule` inspects. */
export function extensionsFor(rule) {
  return Array.isArray(rule.EXTENSIONS) && rule.EXTENSIONS.length ? rule.EXTENSIONS : DEFAULT_EXTENSIONS;
}

/** Whether `rule` applies to `file` -- inside its TARGETS and of its extension. */
export function ruleAppliesTo(rule, file) {
  if (!Array.isArray(rule.TARGETS) || rule.TARGETS.length === 0) return false;
  if (!rule.TARGETS.some((t) => under(file, t))) return false;
  return extensionsFor(rule).some((ext) => file.endsWith(ext));
}

/**
 * Every repo-root-relative file under the rules' TARGETS.
 *
 * `--all` previously walked nothing: the flag satisfied the "pass something"
 * check and then filtered an empty list, so the run reported `0 violations`
 * over a tree it never opened -- indistinguishable from a clean tree, which is
 * the exact failure the canonical rules exist to catch (#17571).
 */
export async function collectTargetFiles(rules, root = repoRoot()) {
  const wanted = new Set();
  for (const rule of rules) for (const ext of extensionsFor(rule)) wanted.add(ext);
  const roots = [...new Set(rules.flatMap((r) => (Array.isArray(r.TARGETS) ? r.TARGETS : [])))];

  const found = new Set();
  for (const target of roots) {
    const abs = join(root, target);
    let info;
    try {
      info = await stat(abs);
    } catch {
      // A TARGETS entry naming nothing is a rule bug, not a clean tree. It is
      // surfaced by `unreachableTargets` rather than skipped in silence.
      continue;
    }
    if (info.isFile()) {
      found.add(abs);
      continue;
    }
    const stack = [[target, true]];
    while (stack.length) {
      const [rel, isRoot] = stack.pop();
      let entries;
      try {
        entries = await readdir(join(root, rel), { withFileTypes: true });
      } catch (err) {
        // ENOENT on the target itself is an absent tree, reported by
        // `unreachableTargets`. Anything else is a directory that exists and
        // could not be read, and swallowing that shrank the audit silently --
        // the run still said "0 violations", the reading this harness exists
        // to make impossible.
        if (err.code === "ENOENT" && isRoot) continue;
        throw new Error(`canonical-check: cannot traverse ${rel}: ${err.message}`);
      }
      for (const e of entries) {
        if (e.name === "node_modules" || e.name.startsWith(".")) continue;
        const child = `${rel}/${e.name}`;
        if (e.isDirectory()) stack.push([child, false]);
        else if ([...wanted].some((ext) => e.name.endsWith(ext))) found.add(join(root, child));
      }
    }
  }
  return [...found].sort();
}

/** TARGETS entries that resolve to nothing on disk. A rule that points at a
 *  missing path checks nothing and says so nowhere. */
export async function unreachableTargets(rules, root = repoRoot()) {
  const missing = [];
  for (const rule of rules) {
    for (const target of Array.isArray(rule.TARGETS) ? rule.TARGETS : []) {
      try {
        await stat(join(root, target));
      } catch {
        missing.push({ ruleId: rule.RULE_ID, target });
      }
    }
  }
  return missing;
}

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

/**
 * Run each rule over the files it declares.
 *
 * TARGETS used to be decorative: every rule ran against every file handed in,
 * so a rule scoped to one tree silently inspected another, and its extension
 * set meant nothing. Honouring it is what lets a CSS rule and a TypeScript rule
 * coexist without each seeing the other's files.
 */
export async function runRules(rules, files, root = repoRoot()) {
  const diagnostics = [];
  for (const file of files) {
    // Matched on the repo-root-relative form, because TARGETS are written that
    // way; OPENED as given, because a rule calls readFile and the process cwd
    // is wherever CI invoked it. Rebasing the path for matching and then
    // handing the rebased path to the rule made every read miss, and a rule
    // that cannot open its file returns no diagnostics -- a clean run.
    const rel = relative(root, resolve(file)).split("\\").join("/");
    for (const rule of rules) {
      if (!ruleAppliesTo(rule, rel)) continue;
      diagnostics.push(...(await rule.check(file)));
    }
  }
  return diagnostics;
}
