// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readdir, readFile, stat } from "node:fs/promises";
import { dirname, join, relative, sep } from "node:path";

import { makeDiagnostic } from "../diagnostic.mjs";
import { repoRoot } from "../registry.mjs";

export const RULE_ID = "ds-duplicate-base-declaration";
export const ISSUE = "#14785";
//: `block`: two live declarations of one token name is the fork itself. Which
//: one wins is an accident of import order and selector specificity, and it
//: flips silently when either file is reordered.
export const SEVERITY = "block";
export const TARGETS = ["autobot-frontend/src/assets"];
export const EXTENSIONS = [".css"];
export const DESCRIPTION =
  "a design token declared as a base value (:root / @theme) in more than one place";
export const FIX_HINT =
  "Keep the one declaration in css/design-tokens.css and delete the other. A per-theme change belongs behind an attribute selector ([data-theme=...], [data-accent=...]) or a prefers-color-scheme media query, never on a bare :root";

const WAIVER = /\/\*\s*canonical:\s*ignore\s+ds-duplicate-base-declaration\b/;
const MASTER_NAME = "design-tokens.css";

/** The stylesheet tree this rule compares against. Peers are all the CSS that
 *  can reach the same page, so the comparison cannot be made one file at a time. */
function assetsRootFor(filePath) {
  const live = join(repoRoot(), "autobot-frontend", "src", "assets");
  if (filePath.startsWith(live + sep)) return live;
  let dir = dirname(filePath);
  while (dir !== dirname(dir)) {
    if (dir.split(sep).pop() === "assets") return dir;
    dir = dirname(dir);
  }
  return dirname(filePath);
}

/** Comments out, newlines kept, so a reported line still points at the file. */
const stripComments = (s) => s.replace(/\/\*[\s\S]*?\*\//g, (m) => m.replace(/[^\n]/g, " "));

/** Top-level comma split that respects (), [] and strings. */
function splitSelectors(prelude) {
  const out = [];
  let depth = 0;
  let quote = "";
  let cur = "";
  for (const ch of prelude) {
    if (quote) {
      if (ch === quote) quote = "";
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "(" || ch === "[") depth++;
    else if (ch === ")" || ch === "]") depth--;
    else if (ch === "," && depth === 0) {
      out.push(cur.trim());
      cur = "";
      continue;
    }
    cur += ch;
  }
  out.push(cur.trim());
  return out;
}

/**
 * Every `--token:` declaration with its enclosing preludes, outermost first.
 * A real tokenizer rather than a pattern: `;` inside url(data:...;base64) and
 * braces inside strings are not structure.
 */
export function declarations(source) {
  const text = stripComments(source);
  const found = [];
  const stack = [];
  let buf = "";
  let bufLine = 1;
  let line = 1;
  let paren = 0;
  let quote = "";
  const flush = () => {
    const m = /^\s*(--[\w-]+)\s*:/.exec(buf);
    if (m && stack.length) found.push({ name: m[1], line: bufLine, stack: [...stack] });
    buf = "";
  };
  for (const ch of text) {
    if (ch === "\n") line++;
    if (quote) {
      if (ch === quote) quote = "";
    } else if (ch === '"' || ch === "'") quote = ch;
    else if (ch === "(") paren++;
    else if (ch === ")") paren = Math.max(0, paren - 1);
    else if (paren === 0 && ch === "{") {
      stack.push(buf.replace(/\s+/g, " ").trim());
      buf = "";
      continue;
    } else if (paren === 0 && ch === "}") {
      flush();
      stack.pop();
      continue;
    } else if (paren === 0 && ch === ";") {
      flush();
      continue;
    }
    if (!buf.trim() && !/\s/.test(ch)) bufLine = line;
    buf += ch;
  }
  return found;
}

/**
 * Whether a declaration is a BASE value for its token name, and under what
 * context. Base means: `:root`/`html` on its own, or inside `@theme`, with only
 * `@supports`/`@layer` around it. Anything behind a `@media` query or an
 * attribute-qualified selector is an override and is exempt -- that is what
 * per-theme files are for.
 */
export function baseContext(decl) {
  const rule = decl.stack[decl.stack.length - 1];
  const outer = decl.stack.slice(0, -1);
  if (outer.some((p) => !/^@(supports|layer)\b/.test(p))) return null;
  const ctx = outer.join(" | ");
  if (/^@theme\b/.test(rule)) return outer.length === 0 ? "@theme" : null;
  if (rule.startsWith("@")) return null;
  return splitSelectors(rule).some((s) => s === ":root" || s === "html") ? ctx : null;
}

async function cssFilesUnder(dir) {
  const out = [];
  const stack = [dir];
  while (stack.length) {
    const d = stack.pop();
    for (const e of await readdir(d, { withFileTypes: true })) {
      if (e.name === "node_modules" || e.name.startsWith(".")) continue;
      const p = join(d, e.name);
      if (e.isDirectory()) stack.push(p);
      else if (e.name.endsWith(".css")) out.push(p);
    }
  }
  return out.sort();
}

/** name -> [{file, line, ctx}] over every stylesheet under `dir`. */
export async function baseSites(dir) {
  const sites = new Map();
  for (const file of await cssFilesUnder(dir)) {
    const src = await readFile(file, "utf-8");
    if (WAIVER.test(src)) continue;
    for (const d of declarations(src)) {
      const ctx = baseContext(d);
      if (ctx === null) continue;
      if (!sites.has(d.name)) sites.set(d.name, []);
      sites.get(d.name).push({ file, line: d.line, ctx });
    }
  }
  return sites;
}

/** The site allowed to hold `name`: the master file if it is involved, else the first. */
const ownerOf = (list) => list.find((s) => s.file.endsWith(`${sep}${MASTER_NAME}`)) ?? list[0];

/** Sites of `name` that are a second declaration -- same-context repeats of the owner's file count too. */
export function surplus(list) {
  const owner = ownerOf(list);
  const seen = new Set();
  const extra = [];
  for (const s of list) {
    const key = `${s.file}|${s.ctx}`;
    const sameFile = s.file === owner.file;
    // The owner's file may restate a token once per context (plain + @supports).
    if (sameFile && !seen.has(key)) seen.add(key);
    else extra.push(s);
  }
  return extra;
}

//: `check` is called once per stylesheet and each call compared against ALL of them,
//: so a run re-parsed the whole tree N times (3.3s for 19 files). The sites are now
//: computed once per tree and reused until a stylesheet's size or mtime changes.
const sitesCache = new Map();

async function signature(dir) {
  const parts = [];
  for (const file of await cssFilesUnder(dir)) {
    const info = await stat(file);
    parts.push(`${file}:${info.size}:${info.mtimeMs}`);
  }
  return parts.join("|");
}

async function cachedBaseSites(dir) {
  const sig = await signature(dir);
  const hit = sitesCache.get(dir);
  if (hit && hit.sig === sig) return hit.sites;
  const sites = await baseSites(dir);
  sitesCache.set(dir, { sig, sites });
  return sites;
}

export async function check(filePath) {
  let own;
  try {
    own = await readFile(filePath, "utf-8");
  } catch (err) {
    throw new Error(`${RULE_ID}: cannot read ${filePath}: ${err.message}`);
  }
  if (WAIVER.test(own)) return [];
  const root = assetsRootFor(filePath);
  const sites = await cachedBaseSites(root);
  const out = [];
  for (const [name, list] of sites) {
    if (list.length < 2) continue;
    const owner = ownerOf(list);
    for (const s of surplus(list)) {
      if (s.file !== filePath) continue;
      out.push(
        makeDiagnostic({
          ruleId: RULE_ID,
          issue: ISSUE,
          severity: SEVERITY,
          file: filePath,
          line: s.line,
          col: 0,
          message: `${name} is already a base declaration in ${relative(root, owner.file)}:${owner.line}`,
          snippet: name,
          fixHint: FIX_HINT,
        }),
      );
    }
  }
  return out.sort((a, b) => a.line - b.line);
}
