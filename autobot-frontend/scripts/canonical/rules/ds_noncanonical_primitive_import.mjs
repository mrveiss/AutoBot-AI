// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { readFile } from "node:fs/promises";
import { basename } from "node:path";

import { makeDiagnostic } from "../diagnostic.mjs";
import { KIT_IMPORT_SPECIFIER, kitComponentFiles, readBaseline, relPath } from "../kit.mjs";

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
const SPECIFIER = /(?:\bfrom\s*|\bimport\s*\(\s*)(["'])([^"']+\.vue)\1/g;

/** Every non-kit import of a kit-named component in `text`. */
export function findHits(text) {
  const kit = kitComponentFiles();
  const hits = [];
  text.split(/\r?\n/).forEach((line, idx) => {
    if (LINE_WAIVER.test(line)) return;
    for (const m of line.matchAll(SPECIFIER)) {
      const spec = m[2];
      if (spec.startsWith(KIT_IMPORT_SPECIFIER)) continue;
      if (kit.has(basename(spec))) hits.push({ idx, col: m.index, line });
    }
  });
  return hits;
}

export async function check(filePath) {
  let text;
  try {
    text = await readFile(filePath, "utf-8");
  } catch {
    return [];
  }
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
