// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// What the design-system rules need to know about the kit (#17571): the names of
// its components, and the frozen baselines that hold the pre-existing
// population. Derived from the tree each run, never copied into a rule, so a new
// kit component is protected the day it lands.
import { readFileSync, readdirSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

import { repoRoot } from "./registry.mjs";

export const KIT_COMPONENTS_DIR = "libs/autobot-ui/src/components";
export const KIT_IMPORT_SPECIFIER = "@autobot/ui";

const BASELINE_DIR = join(dirname(fileURLToPath(import.meta.url)), "baselines");

let kitNames;
/** Basenames (`BaseButton.vue`) of every component the kit ships. */
export function kitComponentFiles(root = repoRoot()) {
  if (root !== repoRoot()) return readKit(root);
  kitNames ??= readKit(root);
  return kitNames;
}

function readKit(root) {
  // Stories and tests are not components; a rule that treated them as such would
  // flag every `*.stories.ts` sibling's name.
  const names = readdirSync(join(root, KIT_COMPONENTS_DIR), { withFileTypes: true })
    .filter((e) => e.isFile() && e.name.endsWith(".vue"))
    .map((e) => e.name);
  if (names.length === 0) {
    // An empty kit listing would make every rule below pass vacuously.
    throw new Error(`canonical-check: ${KIT_COMPONENTS_DIR} lists no components -- refusing to report a clean run`);
  }
  return new Set(names);
}

/** A baseline: `path<TAB>count` lines (count defaults to 1), `#` comments. */
export function readBaseline(name) {
  const entries = new Map();
  const text = readFileSync(join(BASELINE_DIR, name), "utf-8");
  for (const raw of text.split(/\r?\n/)) {
    const line = raw.trim();
    if (!line || line.startsWith("#")) continue;
    const [path, count] = line.split("\t");
    entries.set(path, Number(count ?? 1));
  }
  return entries;
}

export const relPath = (file, root = repoRoot()) => {
  const norm = file.split("\\").join("/");
  const r = root.split("\\").join("/");
  return norm.startsWith(`${r}/`) ? norm.slice(r.length + 1) : norm;
};
