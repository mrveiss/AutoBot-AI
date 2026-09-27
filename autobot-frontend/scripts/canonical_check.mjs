#!/usr/bin/env node
// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
import { argv, exit, stderr, stdout } from "node:process";
import { writeFile } from "node:fs/promises";

import { relative, resolve } from "node:path";
import { cwd } from "node:process";

import {
  collectTargetFiles,
  discoverRules,
  repoRoot,
  ruleAppliesTo,
  runRules,
  unreachableTargets,
} from "./canonical/registry.mjs";
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

  // A rule's TARGETS are repo-root-relative, so a path given on the command
  // line -- typically relative to autobot-frontend, which is where CI runs
  // this -- has to be rebased before it can be matched against them. Without
  // this every --files invocation would silently match no rule and report a
  // clean run, which is the failure this change exists to remove, reintroduced
  // one layer along.
  // Paths stay as the caller gave them so the rules can open them; runRules
  // derives the repo-root-relative form itself for TARGETS matching.
  const files = args.all ? await collectTargetFiles(rules) : args.files.map((f) => resolve(cwd(), f));

  // A TARGETS entry naming a path that does not exist makes its rule inspect
  // nothing while reporting the same clean run as a rule that found nothing.
  const missing = await unreachableTargets(rules);
  for (const { ruleId, target } of missing) {
    stderr.write(`canonical-check: ${ruleId} targets ${target}, which does not exist\n`);
  }

  if (files.length === 0) {
    stderr.write("canonical-check: no files matched — refusing to report a clean run\n");
    return 2;
  }

  // Having files is not having COVERAGE, and the two modes differ in what that
  // means.
  //
  // `--all` is an AUDIT: it chose the files itself, so nothing in scope means
  // it inspected nothing and reporting success would be a false clean bill --
  // the `--all` bug this PR fixes, one level in. It refuses.
  //
  // `--files` is a FILTER: the caller chose the files, and the pre-commit hook
  // passes every changed `autobot-frontend/**/*.{ts,vue,mjs,js}` including this
  // harness, which no rule targets. Skipping those is correct behaviour, not a
  // concealed pass, so it reports what it skipped and exits 0. Refusing here
  // instead broke the hook on the very commit implementing it.
  const covered = files.filter((f) => {
    const rel = relative(repoRoot(), resolve(f)).split("\\").join("/");
    return rules.some((rule) => ruleAppliesTo(rule, rel));
  });
  if (covered.length === 0) {
    const scope = args.all ? "refusing to report a clean run" : "nothing to check";
    stderr.write(
      `canonical-check: ${files.length} file(s) given, none inside any rule's TARGETS — ${scope}\n`,
    );
    if (args.all) return 2;
    return 0;
  }

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

  // The severity vocabulary is block | warn | audit; `makeDiagnostic` rejects
  // anything else, so a rule cannot opt into failing by inventing a level --
  // it says `block` or it is advisory. An unreachable target fails too: a rule
  // that inspected nothing has not agreed with the tree, it has not looked.
  const failing = diagnostics.some((d) => d.severity === "block");
  return failing || missing.length > 0 ? 1 : 0;
}

main().then((code) => exit(code)).catch((err) => {
  stderr.write(`${err.stack || err}\n`);
  exit(2);
});
