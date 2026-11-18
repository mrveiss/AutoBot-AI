// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readFile } from "node:fs/promises";
import { basename } from "node:path";

import { makeDiagnostic } from "../diagnostic.mjs";
import { kitComponentFiles, readBaseline, relPath } from "../kit.mjs";

export const RULE_ID = "ds-noncanonical-primitive-import";
export const ISSUE = "#17571";
//: `block`: pre-existing imports are frozen per file in baselines/ds_noncanonical_primitive_import.txt;
//: a file with MORE such imports than recorded is reported again.
export const SEVERITY = "block";
export const TARGETS = ["autobot-frontend/src", "autobot-slm-frontend/src"];
export const EXTENSIONS = [".vue", ".ts"];
export const DESCRIPTION =
  "a kit-named component (BaseButton.vue, EmptyState.vue, ...) imported from a path other than '@autobot/ui' -- the import binds to a local copy or reaches into the kit's internals";
export const FIX_HINT =
  "import { <Name> } from '@autobot/ui'. If the local file is a re-export shim, import the kit directly and retire the shim";

const LINE_WAIVER = /canonical:\s*ignore\s+ds-noncanonical-primitive-import\b/;
//: `import X from '...'`, `import { X } from '...'` and `import('...')` forms; only the specifier matters.
//: Run over the whole file (`\s` spans newlines), so a multi-line import is seen. It runs over
//: the text with comments AND string contents blanked, so `from`/`import(` inside a string never
//: matches; it stops at the opening quote and the specifier is read from the original text.
const SPECIFIER = /(?:\bfrom\s*|\bimport\s*\(\s*)(["'])/g;

/** `text` with every JS comment blanked to spaces (newlines kept, so offsets and
 *  line numbers survive). Quoted strings are walked, so `'http://x'` is not a comment.
 *  With `blankStrings`, string contents are blanked too (the quotes stay). */
export function blankComments(text, blankStrings = false) {
  const token = /\/\/|\/\*|["'`]/g;
  let out = "";
  let kept = 0;
  for (let m = token.exec(text); m; m = token.exec(text)) {
    if (m[0].length === 1) {
      const after = skipString(text, m.index);
      if (blankStrings) {
        const close = after - 1 > m.index && text[after - 1] === m[0] ? after - 1 : after;
        out += text.slice(kept, m.index + 1) + text.slice(m.index + 1, close).replace(/[^\r\n]/g, " ");
        kept = close;
      }
      token.lastIndex = after;
      continue;
    }
    const end = m[0] === "//" ? lineEnd(text, m.index) : endOfBlock(text, m.index);
    out += text.slice(kept, m.index) + text.slice(m.index, end).replace(/[^\r\n]/g, " ");
    kept = end;
    token.lastIndex = end;
  }
  return out + text.slice(kept);
}

const lineEnd = (text, from) => {
  const nl = text.indexOf("\n", from);
  return nl < 0 ? text.length : nl;
};

const endOfBlock = (text, from) => {
  const close = text.indexOf("*/", from + 2);
  return close < 0 ? text.length : close + 2;
};

/** Index just past the string opened at `start`; ' and " stop at a line end, ` does not. */
function skipString(text, start) {
  const quote = text[start];
  for (let k = start + 1; k < text.length; k += 1) {
    if (text[k] === "\\") k += 1;
    else if (text[k] === quote) return k + 1;
    else if (text[k] === "\n" && quote !== "`") return k;
  }
  return text.length;
}

/** Every non-kit import of a kit-named component in `text`, split across lines or not. */
export function findHits(text) {
  const kit = kitComponentFiles();
  const lines = text.split(/\r?\n/);
  const starts = lineStarts(text);
  const hits = [];
  for (const m of blankComments(text, true).matchAll(SPECIFIER)) {
    const open = m.index + m[0].length;
    const spec = text.slice(open, text.indexOf(m[1], open));
    if (spec.includes("\n") || !spec.endsWith(".vue") || !kit.has(basename(spec))) continue;
    const idx = lineOf(starts, m.index);
    if (LINE_WAIVER.test(lines[idx]) || LINE_WAIVER.test(lines[lineOf(starts, open)])) continue;
    hits.push({ idx, col: m.index - starts[idx], line: lines[idx] });
  }
  return hits;
}

function lineStarts(text) {
  const starts = [0];
  for (let k = 0; k < text.length; k += 1) if (text[k] === "\n") starts.push(k + 1);
  return starts;
}

const lineOf = (starts, offset) => {
  let lo = 0;
  for (let hi = starts.length - 1; lo < hi; ) {
    const mid = (lo + hi + 1) >> 1;
    if (starts[mid] <= offset) lo = mid;
    else hi = mid - 1;
  }
  return lo;
};

export async function check(filePath) {
  // A read that throws is rethrown (main().catch exits 2): returning [] would let a
  // run exit 0 without having inspected the file.
  const text = await readFile(filePath, "utf-8");
  const hits = findHits(text);
  const allowed = readBaseline("ds_noncanonical_primitive_import.txt").get(relPath(filePath)) ?? 0;
  return hits.slice(allowed).map(({ idx, col, line }) =>
    makeDiagnostic({
      ruleId: RULE_ID,
      issue: ISSUE,
      severity: SEVERITY,
      file: filePath,
      line: idx + 1,
      col,
      message: "kit-named component imported from a non-kit path -- import it from '@autobot/ui'",
      snippet: line.trim().slice(0, 120),
      fixHint: FIX_HINT,
    }),
  );
}
