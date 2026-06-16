#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { argv, exit, stderr, stdout } from "node:process";
import { writeFile } from "node:fs/promises";

import { discoverRules, runRules } from "./canonical/registry.mjs";
import { toJson, toPretty } from "./canonical/reporter.mjs";

function parseArgs(rawArgs) {
  const args = { files: [], all: false, format: "pretty", explain: null, output: null };
  for (let i = 0; i < rawArgs.length; i++) {
    const a = rawArgs[i];
    if (a === "--files") {
      while (i + 1 < rawArgs.length && !rawArgs[i + 1].startsWith("--")) {
        args.files.push(rawArgs[++i]);
      }
    } else if (a === "--all") {
      args.all = true;
    } else if (a === "--explain") {
      args.explain = rawArgs[++i];
    } else if (a === "--format") {
      args.format = rawArgs[++i];
    } else if (a === "--output") {
      args.output = rawArgs[++i];
    }
  }
  return args;
}

async function main() {
  const args = parseArgs(argv.slice(2));
  const rules = await discoverRules();

  if (args.explain) {
    const rule = rules.find((r) => r.RULE_ID === args.explain);
    if (!rule) {
      stderr.write(`unknown rule: ${args.explain}\n`);
      return 2;
    }
    stdout.write(`${rule.RULE_ID} (${rule.ISSUE}) [${rule.SEVERITY}]\n`);
    stdout.write(`${rule.DESCRIPTION}\n\nFix:\n${rule.FIX_HINT}\n`);
    return 0;
  }

  if (args.files.length === 0 && !args.all) {
    stderr.write("error: --files or --all required\n");
    return 2;
  }

  // Wave 0: only --files mode is supported. --all walking is a Wave 3 task.
  const files = args.files.filter((f) => /\.(ts|vue|mjs|js)$/.test(f));
  const diagnostics = await runRules(rules, files);

  let out;
  let sink = stderr;
  if (args.format === "pretty") {
    out = toPretty(diagnostics);
  } else if (args.format === "json") {
    out = toJson(diagnostics);
    sink = stdout;
  } else {
    stderr.write(`format ${args.format} not implemented in Wave 0\n`);
    return 2;
  }

  if (args.output) {
    await writeFile(args.output, out, "utf-8");
  } else {
    sink.write(out);
    if (!out.endsWith("\n")) sink.write("\n");
  }

  return diagnostics.some((d) => d.severity === "block") ? 1 : 0;
}

main().then((code) => exit(code)).catch((err) => {
  stderr.write(`${err.stack || err}\n`);
  exit(2);
});
