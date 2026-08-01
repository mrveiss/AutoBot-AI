# Session audit — secreview skill and CI review gate

**Date:** 2026-07-30
**Scope:** work delivered across #12951, #12955, #12956, #12973 (PRs #12952, #12970, #12974)
**Reason:** post-delivery review for regressions, canonical-standard violations, and
consolidation opportunities.

## 1. Defect in merged code — wrong auth mechanism (#12983, fixed here)

`ai-security-review.yml` gated on an `ANTHROPIC_API_KEY` secret. That is the
metered-API auth path; this project runs on a **Claude Code subscription**, whose
headless/CI credential is a long-lived OAuth token from `claude setup-token`,
stored as `CLAUDE_CODE_OAUTH_TOKEN`.

**Impact:** the merged workflow would have skipped on every PR forever. The
skip-safe design hid the error — no red check, no failure, just silent
permanent inertness. Worse, had the API-key secret ever been added to "fix" it,
reviews would have billed per token against a separate account instead of using
the subscription already paid for.

**Root cause:** I assumed the auth mechanism instead of confirming it. The
acceptance criteria I wrote encoded the same assumption, so nothing in the
issue or PR caught it. A criterion asserting the *wrong* prerequisite is worse
than a missing one — it launders the assumption as a requirement.

**Fixed** in this change: gate, `env:`, notice text, and header comment now use
`CLAUDE_CODE_OAUTH_TOKEN`, with a note not to reintroduce the API key.

## 2. Duplication I introduced — PR comment upsert (#12984)

The marker-based comment upsert in `ai-security-review.yml` duplicates
`ssot-coverage.yml:122-145`, which already implements the same
listComments → find → update-else-create pattern. I did not check for an
existing implementation before writing mine, which is a direct violation of
Core Rule 2 (Reuse).

Two implementations of one concept, and they differ in ways that matter:

| | `ssot-coverage.yml` | `ai-security-review.yml` |
|---|---|---|
| Identifies its comment by | visible heading substring | invisible HTML marker |
| Pagination | `listComments` unpaginated | `github.paginate` |

So the newer one is more correct, which is the worst version of duplication —
the divergence is a silent upgrade that the older caller never receives.

Filed as a discovery issue: extract a composite action and converge both.
`.github/actions/` already hosts `free-disk-space` and `setup-python-ci`, so
the pattern exists and nothing new needs inventing.

## 3. Pre-existing bug found while comparing — unpaginated comment lookup (#12984)

`ssot-coverage.yml:122` calls `listComments` without pagination. GitHub returns
30 per page by default, so on a PR with more than 30 comments the existing
report falls off page one and the workflow appends a **new** comment every run
instead of updating. Its heading-substring match is also brittle: changing the
heading orphans the old comment and silently restarts the append behaviour.

Not hypothetical for this repo — long-running PRs accumulate bot comments from
several workflows.

## 4. Pre-existing duplication — path filter lists (#12986)

The Python-backend path list is repeated **7 times across 6 workflows**:

```
security.yml:43            phase_validation.yml:10
startup-import-smoke.yml:19, :55
api-wiring.yml:28, :68     ai-security-review.yml:48
```

There is no single source of truth for "which paths are backend Python code".
Any new backend directory has to be remembered in seven places, and a miss is
silent — the gate simply stops running on that path. I added the seventh
instance rather than noticing the pattern.

## 5. Highest-impact discovery — two diverged router-prefix parsers (#12985)

`scripts/audit_api_wiring.py` and
`autobot-backend/api/codebase_analytics/api_endpoint_scanner.py` both derive
served API paths from source, with **separate regexes for the same grammar**:

| Concept | audit_api_wiring.py | api_endpoint_scanner.py |
|---|---|---|
| `include_router(prefix=)` | `INCLUDE_ROUTER_RE` | `_ROUTER_INCLUDE_RE` |
| `APIRouter(prefix=)` | `ROUTER_PREFIX_RE` | `_APIROUTER_PREFIX_RE` |
| registry tuple entries | `ROUTER_CONFIG_ENTRY_RE` | `_SIMPLE_TUPLE_RE`, `_FOUR_ELEMENT_TUPLE_RE`, `_FIVE_ELEMENT_TUPLE_RE` |

They have already diverged. The scanner received two rounds of fixes for
registry-mounted **packages** — #12945 (package prefix comes from the package's
own router) and #12956 (recurse into nested subpackages). `audit_api_wiring.py`
received neither. Its `_registry_module_prefixes` (line 226) still does:

```python
for py in registry_dir.glob("*.py"):        # flat glob, no packages
    module_prefix[mod.replace(".", "/") + ".py"] = prefix.rstrip("/")
```

Registry entries are assumed to be module *files*; a package entry such as
`("llc.api", "", …)` resolves to a non-existent `llc/api.py` and contributes no
prefix at all.

**Why this outranks the rest:** `api-wiring` is a *required, blocking* gate
(`api-wiring.yml` header: "BLOCKING gate since #9864"), and repo convention
holds that its reds are genuine unwired calls rather than noise to baseline.
A prefix resolver that silently under-resolves registry-mounted packages either
produces false reds or masks real contract drift — and the fix for exactly that
bug already exists 40 lines away in a different file.

## Answers to the review questions

**Best implementation, no regression?** No — item 1 was a genuine defect in
merged code, now fixed. Item 2 means the implementation was *duplicative* even
where it was correct. No behavioural regression to existing code: every change
this session was additive (a new workflow, a new skill, two doc lines) except
the `api-wiring.yml` anchor removal, which is inert (a YAML anchor with no alias
has no effect) and verified by `actionlint` passing on all workflows.

**Issue states correct?** Yes, verified: #12951, #12955, #12956, #12973 all
`CLOSED` with merge evidence. #12956 was closed by someone else via PR #12970;
confirmed genuinely fixed rather than merely closed, and its closing note
records the bug was latent (no nested router subpackages exist today) rather
than live — my original report overstated impact.

**Enum or class consolidation?** None in what I touched — this session's
deliverables were YAML and Markdown, with no Python class or enum surface. The
consolidation opportunities are the regex/parser duplication in item 5 and the
workflow-level duplication in items 2 and 4.

**Canonical standards followed?** Partially. Conventions honoured: SHA-pinned
third-party actions, tag-ref first-party actions, `ubuntu-latest` over the
self-hosted singleton, `env:`-passed inputs instead of `run:` interpolation,
issue → worktree → PR for every repo change, commit-message format, no
trailers. Violated: Rule 2 (Reuse) in item 2, and Rule 1 (Check Before Writing)
in items 2 and 4 — in both cases I wrote a new instance without first grepping
for an existing one, which is precisely the check the rule exists to force.

## Filed

Every finding above is tracked; none left as prose only.

| # | Finding | Priority |
|---|---|---|
| #12983 | Wrong auth mechanism (fixed in this PR) | high |
| #12985 | Two diverged router-prefix parsers; `audit_api_wiring` missing #12945/#12956 | high |
| #12984 | Diverged PR-comment upserts; `ssot-coverage` appends past 30 comments | medium |
| #12986 | Backend-Python path filter duplicated 7x | low |
