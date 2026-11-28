# Research: Modular Business-App Platform Patterns

Status: Phase 1 and Phase 2 (overlapping areas) complete.

## Source Analysis: a large open-source modular business-application suite (reference work)

### What It Is

A mature (~20 major versions, very active — commits daily) Python + PostgreSQL web platform
from a commercial vendor that ships a framework core plus ~640 installable add-on modules
(CRM, accounting, inventory, website, POS, HR…). Each add-on is a self-describing package that
extends the shared data model and UI; installing several yields a full integrated suite.
Licence is mixed (open core). The repo also ships a small library of agent skills for
AI-assisted development against the framework.

### Architecture & Key Patterns

- **Modular monolith.** One process/DB, but every feature is an add-on with a declarative
  manifest (`name`, `version`, `depends`, ordered `data` files, assets). The core resolves a
  **dependency graph** (`modules/module_graph.py`: nodes with `depth` = longest path to the
  root module, `phase`, demo-installability) and loads modules in topological order.
- **Inheritance-based extension of a shared ORM.** Modules extend existing models/fields/views
  by name rather than subclassing at import site; the registry composes the final class at
  load time (`orm/registry.py`, `orm/model_classes.py`).
- **Per-module, per-version data migrations.** `migrations/<version>/{pre,post,end}-*.py`
  scripts, each exposing `migrate(cr, installed_version)`; a special `0.0.0` folder runs on
  any version change (`modules/migration.py`, `MigrationManager`).
- **Source-code codemods per release.** `upgrade_code/<version>-<name>.py` scripts each expose
  `upgrade(file_manager)` and rewrite the codebase when the framework API changes; a CLI
  command selects and runs them (`cli/upgrade_code.py`). Explicitly best-effort.
- **Database neutralization.** Each module may ship `data/neutralize.sql`; the `neutralize`
  CLI runs the snippets for every installed module to make a prod DB copy safe for
  staging (disable outbound mail servers and fetchers, delete push keys, truncate queues).
  `--stdout` prints the SQL instead of applying it (`modules/neutralize.py`, `cli/neutralize.py`).
- **Serialization-failure retry around each request.** `http/retrying.py` runs the handler in
  a loop, rolling back and retrying on serialization/integrity/concurrency errors, up to 5
  tries with randomized exponential backoff, resetting request-scoped state between tries.
- **Declarative security data per module:** model-access rows and record rules shipped as
  data files alongside the code, loaded with the module.
- **Rich CLI** (`cli/`): `scaffold`, `shell`, `db`, `deploy`, `duplicate`, `neutralize`,
  `obfuscate`, `i18n`, `cloc`, `upgrade_code`.
- **Shipped agent skills** (`skills/`): review, security-audit, git, coding and web
  guidelines in the open skill format, designed to be installed together.

### Notable Implementation Details

- Neutralization is **distributed ownership**: the module that creates an external side
  effect owns the SQL that disables it, so the list stays complete as modules are added.
- Migration stage ordering (`pre` → module init → `post` → `end` after all modules) solves
  cross-module data dependencies without a global migration sequence.
- The security skill frames audit as "sweep for pattern → judge each hit against a section",
  with completion defined as "every pattern swept and every hit judged" — an explicit
  completion criterion rather than a vague review.
- Retry helper documents *why* (two transactions committing incompatible writes) and resets
  side-channel state (the request session) between attempts.

### Strengths

- Extremely consistent extension model; one manifest format for 640 modules.
- Upgrade story covers both data (migrations) and code (codemods).
- Prod→staging safety is a first-class, per-module concern.
- Mature CLI tooling for operators.

### Weaknesses / Limitations

- Inheritance-by-name extension makes behaviour non-local: the effective model is the
  composition of every installed module, hard to reason about and to type-check.
- Tight coupling to PostgreSQL and its own ORM; little room for alternative stores.
- Codemods are regex/text rewrites ("best-effort, not silver bullets").
- Neutralization is raw SQL per module with no verification that it covered every side
  effect — a module that forgets its file silently leaks prod behaviour to staging.
- Version regex in the migration manager carries legacy encoding of decade-old version
  schemes (including a FIXME for year 2106).

### Visible vs Hidden Metrics

- **Visible:** ~55k stars, 640 modules, full ERP coverage, daily commits, a public CI
  service (all self-reported / repo-observable; star count verified via API).
- **Hidden:** the composition-by-inheritance model imposes a steep learning curve and
  debugging cost (any installed module can change any model); upgrades across majors are
  costly enough that the vendor ships codemods *and* sells migration services; the
  monolith's single DB is both its consistency strength and its scaling ceiling.
- **Weighing:** the whole-framework model is a poor fit to adopt wholesale for an AI-agent
  platform. The cheap, decoupled patterns — per-module neutralization, staged per-version
  migrations, serialization-retry, a codemod directory, and pattern-sweep audit skills —
  carry the visible wins without the hidden coupling cost.

## AutoBot Comparison: reference work → AutoBot (overlapping areas only)

Scope: the six areas where both systems solve the same problem — add-on loading, schema
migrations, concurrent-write retry, codemods, prod-data safety for non-prod copies, and
agent review skills.

### What We Can Adopt

| # | Pattern | AutoBot target | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|---|
| 1 | Dependency-ordered add-on load (topological sort on `depends`, reverse order on shutdown, cycle = hard error) | `autobot_shared/plugin_sdk/plugin_manager.py` (`startup`, `shutdown`), `autobot_shared/plugin_sdk/loader.py` (`discover_plugins`) | `PluginManifest.dependencies` exists (`plugin_sdk/base.py:121`) and `_check_dependencies` (`loader.py:446`) rejects a plugin whose deps are not *yet* loaded; but `discover_plugins` returns `rglob("plugin.json")` filesystem order and `startup` loads in that order, `shutdown` unloads in registry order. No `graphlib`/toposort anywhere in the SDK. | A plugin that depends on another loads regardless of directory order; dependents stop before their dependencies | ~40 lines with stdlib `graphlib.TopologicalSorter`; no new dependency | **adopt** → #18502 | trivial |
| 2 | Per-component neutralization of a restored data copy (each component owns the snippet that disables its outbound side effects; one command runs all, with a print-only mode) | SLM backup/restore lifecycle (#10016), `autobot-infrastructure/shared/scripts/backup_manager.py` | Grep for `neutraliz`, `scrub`, `sanitiz*_db` over code: no hit outside unrelated text-sanitizers. `backup_manager.py` has backup/incremental functions, no restore-side scrub. | A restored copy cannot send messages, run scheduled jobs or call LLM providers with production credentials | Only pays off if a production backup is ever restored onto a test/dev node — **I don't know whether that workflow exists here**; if it does not, this is speculative | **adopt-with-conditions**: only once restore-to-another-node is a supported path | moderate |

### What We Already Do Better

- **Migrations.** AutoBot's Alembic chain (`autobot-backend/migrations/versions/`, 103
  revisions) has guards (`migrations/guards.py`), a baseline adopter for never-stamped
  databases (`migrations/baseline.py`) and a CI migration gate. The reference work's
  per-module `pre/post/end` staging fixes cross-module ordering that AutoBot does not have,
  since it is not composed from independently versioned DB modules. Its real weakness is
  that migrations live in four places (`migrations/versions`, `backend/migrations`,
  `database/migrations`, `autobot-slm-backend/migrations`). That's already tracked in #16464,
  #15866, #15891 and #15899, so this research doesn't add a finding there.
- **Concurrent-write retry.** Redis optimistic-lock retry already exists
  (`autobot_shared/coordination/shared_runtime_bag.py:178`, `takeover_manager.py:537`).
  Postgres access runs at the default isolation level (no `isolation_level` overrides outside
  DDL), so serialization failures, which the reference work's request-retry loop exists to
  absorb, are not a failure mode AutoBot currently produces. **Rejected by hidden metrics:**
  a blanket retry around handlers would replay non-idempotent side effects (LLM calls,
  outbound HTTP).
- **Agent review skills.** AutoBot's `secreview` (findings-first table) and `review-fleet`
  (finder and verifier agents) go further than the reference work's single-pass pattern
  sweep.

### Gaps & Opportunities (by impact)

1. Plugin load order (#1 above): a real correctness gap with a trivial fix.
2. Neutralization (#2): conditional on a restore-to-non-prod workflow existing.
3. **Codemods directory: rejected by hidden metrics.** The reference work needs codemods
   because hundreds of third-party add-ons consume its API. AutoBot's API changes are made
   in-repo and enforced by ratchets (`docs/developer/RATCHET_BASELINES.md`); one-off
   rewrites like `scripts/migrate_spacing_tokens.py` cover the rare case. A framework would
   be maintenance without a consumer.

### Specific Code/Files Affected

- `autobot_shared/plugin_sdk/plugin_manager.py`: `startup()` iterates a topologically
  sorted manifest list; `shutdown()` unloads in reverse; a dependency cycle or unknown
  dependency is logged as a per-plugin failure, never swallowed.
- `autobot_shared/plugin_sdk/loader.py`: a helper (≤30 lines) that orders manifests by
  `dependencies` using `graphlib`.
- (Conditional) the SLM restore path: a per-role neutralize hook, run after restore when
  the target node differs from the source.

## Linked issues

Issues this research produced or is the analysis for (#18967). Each one links back to this document.

- #18502 — fix(plugins): startup loads plugins in filesystem order, so a plugin discovered before its dependency is rejected
