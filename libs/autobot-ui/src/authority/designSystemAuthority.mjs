// Copyright 2025-2026 mrveiss
// SPDX-License-Identifier: Apache-2.0
//
// Design-system authority registry (#17571): which module OWNS each design-system
// concept. The frontend analogue of `autobot_shared/store_authority.py`.
//
// It lives in code, not in a document, so it is reachable from the import site
// and readable by the canonical-check rules (autobot-frontend/scripts/canonical).
// The harness does not enforce this table: its rules check kit file names and
// import specifiers against frozen baselines and inline waivers.
// `designSystemOwner()` enforces declared ownership, when a caller invokes it.
// Where this file and any document disagree, this file wins.
//
// Rules, mirroring store_authority:
//   1. Every concept names its owner, or says in `note` why it has none yet.
//   2. Anything else that implements the concept is a copy to drain, not a peer.
//   3. A concept absent from this table is an error at the point of use.
//
// It is a plain .mjs so `node canonical_check.mjs` can import it on any Node the
// CI image ships, with no type-stripping flag; `designSystemAuthority.d.mts`
// carries the types for TypeScript consumers.

/** `canonical`: `owner` is the one module. `undecided`: the population is not yet
 *  reduced to a single home -- `note` and `issue` say who is deciding. */
export const AUTHORITY = Object.freeze({
  "button": { status: "canonical", owner: "libs/autobot-ui/src/components/BaseButton.vue", issue: "#14776" },
  "card": { status: "canonical", owner: "libs/autobot-ui/src/components/BaseCard.vue", issue: "#14776" },
  "badge": { status: "canonical", owner: "libs/autobot-ui/src/components/BaseBadge.vue", issue: "#14776" },
  "empty-state": { status: "canonical", owner: "libs/autobot-ui/src/components/EmptyState.vue", issue: "#14776" },
  "table": { status: "canonical", owner: "libs/autobot-ui/src/components/BaseTable.vue", issue: "#17562" },
  "toast": { status: "canonical", owner: "libs/autobot-ui/src/composables/useToast.ts", issue: "#14907" },
  "token-contract": {
    status: "canonical",
    owner: "libs/autobot-ui/src/tokens/contract.css",
    issue: "#17566",
    note: "The kit's semantic vocabulary (--aui-*). Each app supplies values for it.",
  },
  "base-tokens-main-gui": {
    status: "canonical",
    owner: "autobot-frontend/src/assets/css/design-tokens.css",
    issue: "#14785",
    note: "The one base :root/@theme declaration site in the main GUI; per-theme overrides sit behind attribute selectors.",
  },
  "nav-registry": {
    status: "canonical",
    owner: "autobot-frontend/src/config/navItems.ts",
    issue: "#17561",
    exceptions: [
      {
        path: "autobot-slm-frontend/src/components/common/Sidebar.vue",
        reason: "SLM keeps its nav inline until #17561 moves both onto one registry shape.",
      },
    ],
  },
  "theme-toggle": {
    status: "undecided",
    owner: null,
    issue: "#14780",
    note: "ThemeToggle.vue and EmberThemeToggle.vue both ship; which one survives is the open decision in #14780.",
  },
  "graph-renderer": {
    status: "undecided",
    owner: null,
    issue: "#17569",
    note: "Several graph components, none declared canonical; #17569 picks the renderer.",
  },
  "notification-system": {
    status: "undecided",
    owner: null,
    issue: "#12731",
    note: "Toast has an owner (see `toast`); the bus/config split around it is still being reduced in #12731.",
  },
  "button-class": {
    status: "undecided",
    owner: null,
    issue: "#12731",
    note: "Utility button classes versus BaseButton; reduced under #12731.",
  },
  "date-format": {
    status: "undecided",
    owner: null,
    issue: "#12731",
    note: "Several date formatters; reduced under #12731.",
  },
});

/** The owning module for `concept`. Throws on a concept the table does not know
 *  and on one with no declared owner -- a silent pass is the defect this prevents. */
export function designSystemOwner(concept) {
  const entry = Object.hasOwn(AUTHORITY, concept) ? AUTHORITY[concept] : undefined;
  if (!entry) {
    throw new Error(`design-system concept ${JSON.stringify(concept)} is not declared in AUTHORITY (add it, with an owner or a note)`);
  }
  if (entry.status !== "canonical" || !entry.owner) {
    throw new Error(`design-system concept ${JSON.stringify(concept)} has no canonical owner yet (${entry.issue}): ${entry.note}`);
  }
  return entry.owner;
}

/** Problems with the table itself; empty when it is well-formed. */
export function authorityProblems(table = AUTHORITY) {
  const problems = [];
  for (const [id, e] of Object.entries(table)) {
    if (!/^#\d+$/.test(e.issue ?? "")) problems.push(`${id}: needs an issue link`);
    if (e.status === "canonical") {
      if (!e.owner) problems.push(`${id}: canonical without an owner`);
    } else if (e.status === "undecided") {
      if (e.owner) problems.push(`${id}: undecided but names an owner`);
      if (!e.note?.trim()) problems.push(`${id}: undecided without a note`);
    } else {
      problems.push(`${id}: status must be canonical or undecided`);
    }
    for (const x of e.exceptions ?? []) {
      if (!x.path || !x.reason?.trim()) problems.push(`${id}: an exception needs a path and a stated reason`);
    }
  }
  return problems;
}
