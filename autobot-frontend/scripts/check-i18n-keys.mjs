#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
/**
 * check-i18n-keys.mjs
 *
 * Extracts all $t('key') and t('key') usages from .vue and .ts source files,
 * then checks each key against en.json.  Exits with code 1 if any keys used
 * in code are missing from the locale file.
 *
 * Usage:  node scripts/check-i18n-keys.mjs [--quiet]
 */

import { readFileSync, readdirSync, statSync } from 'node:fs';
import { resolve, join, extname } from 'node:path';
import { fileURLToPath } from 'node:url';

const __dirname = fileURLToPath(new URL('.', import.meta.url));
const ROOT = resolve(__dirname, '..');
const SRC = join(ROOT, 'src');
const EN_JSON = join(ROOT, 'src', 'i18n', 'locales', 'en.json');

const quiet = process.argv.includes('--quiet');

// ---------------------------------------------------------------------------
// 1. Load en.json and build a flat set of dot-joined keys
// ---------------------------------------------------------------------------
function flattenKeys(obj, prefix = '') {
  const result = new Set();
  for (const [k, v] of Object.entries(obj)) {
    const key = prefix ? `${prefix}.${k}` : k;
    if (v !== null && typeof v === 'object' && !Array.isArray(v)) {
      for (const nested of flattenKeys(v, key)) result.add(nested);
    } else {
      result.add(key);
    }
  }
  return result;
}

const enJson = JSON.parse(readFileSync(EN_JSON, 'utf8'));
const definedKeys = flattenKeys(enJson);

// ---------------------------------------------------------------------------
// 2. Walk src/ and collect all .vue / .ts files (exclude test and node_modules)
// ---------------------------------------------------------------------------
const EXTENSIONS = new Set(['.vue', '.ts']);
const EXCLUDE_DIRS = new Set(['node_modules', 'dist', '__tests__', 'coverage', 'cypress', 'playwright']);

function walkFiles(dir) {
  const results = [];
  for (const entry of readdirSync(dir)) {
    if (EXCLUDE_DIRS.has(entry)) continue;
    const full = join(dir, entry);
    const stat = statSync(full);
    if (stat.isDirectory()) {
      results.push(...walkFiles(full));
    } else if (EXTENSIONS.has(extname(entry))) {
      results.push(full);
    }
  }
  return results;
}

const sourceFiles = walkFiles(SRC);

// ---------------------------------------------------------------------------
// 3. Extract translation key strings from source files
//
//    Patterns matched:
//      $t('key')          $t("key")          $t(`key`)
//      t('key')           t("key")           t(`key`)
//    Keys with dynamic parts (template literals containing ${...}) are skipped
//    with a warning since they cannot be statically analysed.
// ---------------------------------------------------------------------------

// Matches $t('key') or standalone t('key') with single/double/backtick quotes.
//
// To avoid false positives from other functions ending in "t" (e.g. mount(),
// split(), parseInt()), we require that the "t(" is preceded by one of:
//   - "$"  → template $t(...)
//   - "{"  → object literal / JSX  { t('...') }
//   - whitespace / start-of-line
//   - "," or "(" or "=" or ";" or ":"  → common statement starters
//
// Group 1 = quote char, group 2 = key string.
//
// Additionally, we only accept keys that look like i18n dot-path strings
// (letters, digits, dots, underscores, hyphens) to filter out accidental
// matches on punctuation, CSS selectors, etc.
const KEY_RE = /(?<![a-zA-Z0-9_])\$?t\(\s*(['"`])((?:[^'"`\\]|\\.)*?)\1/g;
const VALID_KEY_RE = /^[a-zA-Z_][\w.]*[\w]$/;
// A dynamic key contains an unescaped ${ inside a backtick string.
const DYNAMIC_RE = /\$\{/;

const usedKeys = new Map(); // key -> Set<file>
const dynamicUsages = []; // { file, raw } for dynamic keys we can't check

for (const file of sourceFiles) {
  const src = readFileSync(file, 'utf8');
  for (const match of src.matchAll(KEY_RE)) {
    const quote = match[1];
    const raw = match[2];
    // Skip interpolated template literals  (e.g.  t(`prefix.${var}`) )
    if (quote === '`' && DYNAMIC_RE.test(raw)) {
      dynamicUsages.push({ file, raw: match[0] });
      continue;
    }
    // Skip strings that don't look like i18n dot-path keys
    if (!VALID_KEY_RE.test(raw)) continue;
    if (!usedKeys.has(raw)) usedKeys.set(raw, new Set());
    usedKeys.get(raw).add(file.replace(ROOT + '/', ''));
  }
}

// ---------------------------------------------------------------------------
// 4. Compare: used keys vs defined keys
// ---------------------------------------------------------------------------

// A key is "missing" if neither the key itself nor any of its ancestors exist
// in en.json.  (This handles pluralisation keys such as `foo.bar` when the
// locale only defines `foo.bar.one` / `foo.bar.other`.)
function isMissingFromLocale(key) {
  if (definedKeys.has(key)) return false;
  // Accept if the key is a namespace prefix of any defined key
  const prefix = key + '.';
  for (const defined of definedKeys) {
    if (defined.startsWith(prefix)) return false;
  }
  return true;
}

const missing = [];
for (const [key, files] of [...usedKeys.entries()].sort()) {
  if (isMissingFromLocale(key)) {
    missing.push({ key, files: [...files].sort() });
  }
}

// ---------------------------------------------------------------------------
// 5. Report
// ---------------------------------------------------------------------------
const relativeEN = EN_JSON.replace(ROOT + '/', '');

if (!quiet) {
  console.log(`i18n key check — locale: ${relativeEN}`);
  console.log(`  Source files scanned : ${sourceFiles.length}`);
  console.log(`  Keys in en.json      : ${definedKeys.size}`);
  console.log(`  Unique keys used     : ${usedKeys.size}`);
  if (dynamicUsages.length) {
    console.log(`  Dynamic keys skipped : ${dynamicUsages.length} (cannot be statically analysed)`);
  }
  console.log('');
}

if (missing.length === 0) {
  if (!quiet) console.log('All translation keys found in en.json.');
  process.exit(0);
}

console.error(`Missing i18n keys: ${missing.length} key(s) used in source but absent from en.json\n`);
for (const { key, files } of missing) {
  console.error(`  MISSING: "${key}"`);
  if (!quiet) {
    for (const f of files) {
      console.error(`    in ${f}`);
    }
  }
}
console.error('');
console.error('Fix: add the missing keys to src/i18n/locales/en.json');
process.exit(1);
