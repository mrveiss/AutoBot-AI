// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
// AutoBot - AI-Powered Automation Platform
// Author: mrveiss
//
// Label selection for the issue-triage workflow (#13050).
//
// Extracted from .github/workflows/issue-triage.yml so the decision is a pure
// function that can be unit-tested. The workflow keeps the API calls; this file
// only decides which labels a given issue text implies.
//
// #13050: the original matched keywords with `issueText.includes(k)` over the
// concatenated title and body. Two failure modes, both observed on real issues:
//
//   1. Substring matching fires inside longer words. 'orm' matches "platform",
//      "format", "information" and "performance"; 'ui' matches "build",
//      "require" and "guide". Ordinary backend prose therefore triggered
//      frontend and backend labels regardless of content.
//   2. Several keywords are ordinary backend vocabulary in their own right.
//      "interface", "component", "comment" and "optimization" appear constantly
//      in backend issues — #13032-#13036 were labelled frontend, docs and
//      advanced for exactly this.
//
// The fix is word-boundary matching, a narrowed keyword set, and a preference
// for applying no label over applying a wrong one.

'use strict';

// Skill-area labels this module may assign. Used by the workflow to decide
// whether an issue was already triaged by a human.
const SKILL_LABELS = ['frontend', 'backend', 'infrastructure', 'docs', 'testing'];
const DIFFICULTY_LABELS = ['good-first-issue', 'intermediate', 'advanced'];

// Conventional-commit scopes that state the area outright, e.g.
// "bug(backend): ..." or "perf(ci): ...". An explicit scope always wins over
// prose inference — it is the author's own statement of where the work lives.
const SCOPE_TO_LABEL = {
  frontend: 'frontend',
  ui: 'frontend',
  gui: 'frontend',
  backend: 'backend',
  api: 'backend',
  llc: 'backend',
  kb: 'backend',
  knowledge: 'backend',
  chat: 'backend',
  voice: 'backend',
  security: 'backend',
  deploy: 'infrastructure',
  ci: 'infrastructure',
  infra: 'infrastructure',
  infrastructure: 'infrastructure',
  docs: 'docs',
  tests: 'testing',
  test: 'testing',
};

// Keyword sets. Every entry must be specific enough that a word-boundary match
// is genuine evidence on its own. Deliberately dropped from the originals:
//   frontend: 'interface', 'component', 'ui'   (ordinary backend words / too short)
//   backend:  'orm', 'api'                     (substring hazards, 'api' too generic)
//   docs:     'comment', 'example'             ('comment' is universal; 'example' was listed twice)
//   advanced: 'optimization', 'performance', 'architecture', 'refactor'
//             (all name packages or routine backend work — see #13032-#13036)
const KEYWORDS = {
  frontend: ['vue', 'frontend', 'typescript', 'css', 'vite', 'dashboard', 'button', 'modal', 'sidebar', 'tsx'],
  backend: ['fastapi', 'python', 'database', 'async', 'backend', 'endpoint', 'sqlalchemy', 'websocket', 'redis', 'celery'],
  infrastructure: ['docker', 'ansible', 'deploy', 'deployment', 'infrastructure', 'devops', 'kubernetes', 'systemd', 'runner'],
  docs: ['readme', 'documentation', 'changelog', 'tutorial'],
  testing: ['pytest', 'vitest', 'coverage', 'fixture', 'regression test', 'unit test', 'integration test'],
};

const DIFFICULTY_KEYWORDS = {
  'good-first-issue': ['beginner', 'good first issue', 'newcomer', 'starter task', 'onboarding'],
  intermediate: ['intermediate', 'moderate complexity'],
  advanced: ['deep knowledge', 'far-reaching', 'cross-cutting rewrite'],
};

/** Escape a keyword for use inside a RegExp. */
function escapeRegExp(text) {
  return text.replace(/[.*+?^${}()|[\]\\]/g, '\\$&');
}

/**
 * True when `keyword` appears in `text` as a whole word.
 *
 * `\b` is used rather than `includes()` so 'orm' cannot match "platform" and
 * 'ui' cannot match "build" — the #13050 defect. Multi-word keywords work
 * unchanged because the boundaries sit at the ends of the phrase.
 */
function matchesWord(text, keyword) {
  return new RegExp(`\\b${escapeRegExp(keyword)}\\b`, 'i').test(text);
}

/**
 * Extract the conventional-commit scope from a title, if present.
 *
 * "bug(backend): streamed replies are dropped" -> "backend"
 * Returns null when the title carries no scope.
 */
function scopeFromTitle(title) {
  const match = /^[a-zA-Z]+\(([^)]+)\)\s*:/.exec((title || '').trim());
  if (!match) {
    return null;
  }
  // A scope may name a path segment, e.g. "chat-history" or "llc/scheduler".
  return match[1].toLowerCase().split(/[\/,\s-]/)[0];
}

/**
 * Decide which labels to add for an issue.
 *
 * @param {{title?: string, body?: string, labels?: Array<{name: string}|string>}} issue
 * @returns {{labels: string[], reason: string}} labels to add, and why. An
 *   empty list with a reason is a valid, preferred outcome — #13050 asks for
 *   no label over a wrong one.
 */
function selectLabels(issue) {
  const title = issue.title || '';
  const body = issue.body || '';
  const text = `${title}\n${body}`;
  const existing = (issue.labels || []).map((l) => (typeof l === 'string' ? l : l.name));

  // #13050: an author who labelled the issue themselves has already triaged it.
  // The old guard was `labels.length > 3`, which let issues created with three
  // explicit labels through to be mislabelled anyway.
  if (existing.some((name) => SKILL_LABELS.includes(name))) {
    return { labels: [], reason: 'issue already carries a skill-area label; leaving triage to the author' };
  }

  const labels = [];

  // An explicit scope is the author's own statement — trust it over prose.
  const scope = scopeFromTitle(title);
  const scopedLabel = scope ? SCOPE_TO_LABEL[scope] : null;
  if (scopedLabel) {
    labels.push(scopedLabel);
  } else {
    for (const [label, words] of Object.entries(KEYWORDS)) {
      if (words.some((word) => matchesWord(text, word))) {
        labels.push(label);
      }
    }
    // Prose that implies three or more areas is not evidence, it is noise.
    // Adding all of them is worse than adding none (#13050).
    if (labels.length >= 3) {
      return { labels: [], reason: `prose matched ${labels.length} skill areas; too ambiguous to label` };
    }
  }

  for (const [label, words] of Object.entries(DIFFICULTY_KEYWORDS)) {
    if (words.some((word) => matchesWord(text, word))) {
      labels.push(label);
    }
  }

  const deduped = [...new Set(labels)].filter((l) => !existing.includes(l));
  const reason = deduped.length
    ? scopedLabel
      ? `scope "${scope}" in title`
      : 'keyword match on word boundaries'
    : 'no confident signal';
  return { labels: deduped, reason };
}

module.exports = { selectLabels, matchesWord, scopeFromTitle, SKILL_LABELS, DIFFICULTY_LABELS };
