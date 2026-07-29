---
name: research
description: Research web articles, GitHub repos, or local files — analyze source then compare against AutoBot codebase
---

# Research Source for AutoBot

Two-phase research skill: first understand the source, then compare against AutoBot to find adoptable patterns, gaps, and opportunities.

## Input

`/research <input> [comments]`

**Input types (auto-detected):**

| Input | Detection | Action |
|-------|-----------|--------|
| `https://github.com/...` | Starts with `github.com` | Fetch README, directory structure, key files |
| `https://...` (other URL) | Starts with `http` | WebFetch the page, strip boilerplate |
| `/path/to/file` or `./file` | Starts with `/` or `./` | Read local file directly |
| Plain text | Everything else | WebSearch for top 3-5 results, fetch and synthesize |

**Comments** after the primary input provide steering context for both phases.

## Capability Tiers

```
┌─────────────────────────────────────────────────────────────┐
│ research                                                      │
├─────────────────────────────────────────────────────────────┤
│ STANDALONE   (always works, zero config)                     │
│   • Analyze a given URL, GitHub repo, or local file          │
│   • web-fetch degradation: Jina Reader → wget → httpx        │
├─────────────────────────────────────────────────────────────┤
│ SUPERCHARGED (unlocks when you connect a provider)           │
│   • SEARXNG_INSTANCE_URL    → topic search (no URL given)    │
│   • BRAVE_SEARCH_API_KEY    → topic search + preferred       │
│                               ranking, SearXNG as fallback   │
└─────────────────────────────────────────────────────────────┘
```

**STANDALONE — always works, zero config**

- Analyze any explicitly-supplied source: a URL (fetched via the `web-fetch`
  skill, which itself degrades Jina Reader → `wget` → `httpx`), a GitHub repo,
  or a local file path.
- Full Phase 1 / Phase 2 comparison against the AutoBot codebase.

**SUPERCHARGED — unlocks per connected provider**

Topic search (a plain-text query with no URL) needs a configured web-search
provider. The runtime registry
([`autobot-backend/agent_loop/search/registry.py`](../../../autobot-backend/agent_loop/search/registry.py))
is credential-gated and degrades in this order:

| Connect this | Unlocks |
|--------------|---------|
| `SEARXNG_INSTANCE_URL` | Topic search via a self-hosted SearXNG instance. |
| `BRAVE_SEARCH_API_KEY` | Topic search via Brave (preferred when both are set); SearXNG becomes the fallback. |
| *(neither set)* | Topic search returns no results — the skill still works on any directly-supplied URL/repo/file. |

The registry never errors on a missing provider: an unconfigured or unreachable
provider degrades to the next one, and an empty chain returns `[]` (no results)
rather than failing.

## Output Contract

Regardless of tier, topic-search research follows a fixed **Summary → findings →
verdict** shape so results are comparable across runs:

```
## Research: <query or source>

**Summary:** one-to-three sentence answer.

### Findings

| # | Source | Provider/Tier | Key point |
|---|--------|---------------|-----------|
| 1 | <title / url> | brave | searxng | direct-url | ... |
| 2 | ...    | ...           | ...       |

**Verdict:** the bottom-line conclusion, with the confidence level and any
caveat (e.g. "no web-search provider configured — direct sources only").
```

Phase 1 (Source Analysis) and Phase 2 (AutoBot Comparison) keep their existing
section structures below; the contract above governs the topic-search entry
point specifically.

## Visible vs Hidden Metrics

Every source advertises its **visible metrics** — benchmarks, stars, features, speed/cost claims. The decisive factors are often **hidden metrics** — costs nobody advertises: maintenance burden, added complexity, coupling/lock-in, operational load, learning curve, failure modes. Like a job offer: the bigger salary (visible) can rationally lose to the job with less stress and more family time (hidden). Both phases below weigh the two explicitly — hidden metrics may outweigh and veto visible wins.

## Phase 1 — Understand Source

Fetch and analyze the input. Produce this structure:

```
## Source Analysis: <title/name>

### What It Is
One-paragraph summary — what this project/article is about, who made it, maturity level.

### Architecture & Key Patterns
- How it's structured (monolith, microservices, plugin-based, etc.)
- Core design patterns used
- Key technologies/libraries

### Notable Implementation Details
- Clever approaches, algorithms, or techniques worth noting
- Code patterns that stand out
- How they solved hard problems

### Strengths
- What they do well

### Weaknesses / Limitations
- What's missing, fragile, or poorly done

### Visible vs Hidden Metrics
- **Visible:** the advertised wins — benchmarks, features, stars, speed/cost claims (flag which are self-reported vs independently verified)
- **Hidden:** the unadvertised costs an adopter inherits — maintenance burden, added complexity, coupling/lock-in, operational load, learning curve, failure modes
- **Weighing:** do the hidden costs undercut the visible wins — for whom, and under what conditions?
```

**Then STOP and ask:** *"Want me to compare this against AutoBot? If so, any specific areas to focus on?"*

Wait for user response before proceeding. User can:
- Say "yes" → Phase 2 with full comparison
- Say "yes, focus on X" → Phase 2 scoped to specific area
- Say "no" → stop here
- Ask follow-up questions about Phase 1

## Phase 2 — Compare to AutoBot

Only after explicit user go-ahead. Read relevant AutoBot files guided by Phase 1 findings and any user focus area.

**How to find relevant AutoBot code:**
- Based on Phase 1's identified patterns/technologies, grep/glob the AutoBot codebase for related modules
- E.g., source about vector search → look at ChromaDB integration, RAG pipeline, embedding code
- E.g., source about task queues → look at Celery workers, workflow engine
- Read the actual files — don't guess at contents

**Produce this structure:**

```
## AutoBot Comparison: <source> → AutoBot

### What We Can Adopt
- Specific patterns, techniques, or approaches from the source
- For each: which AutoBot module/file it would apply to
- For each: already-exists audit — the greps/files checked proving AutoBot lacks it (cite paths)
- For each: visible benefit (the advertised win) AND hidden cost (maintenance, complexity, coupling/lock-in, ops load) — one line each
- For each: verdict — adopt / adopt-with-conditions / rejected-by-hidden-metrics; hidden costs can veto a visibly attractive candidate
- Effort estimate: trivial / moderate / significant

### What We Already Do Better
- Areas where AutoBot's approach is superior
- Why our approach works better for our use case

### Gaps & Opportunities
- Things they have that we lack entirely
- Features or patterns worth considering
- Prioritized by impact to AutoBot

### Specific Code/Files Affected
- Concrete AutoBot file paths that would change
- Brief description of what the change would look like
```

After Phase 2, user decides whether to create design docs or GitHub issues.

## Source-Specific Behavior

### GitHub Repos
For large repos, prioritize reading:
1. README.md
2. Directory structure (top-level + key dirs)
3. Main entry points / config files
4. Files most relevant to user's comments

Do NOT read the entire repo. Focus on architecture and patterns.

### Web Articles
Fetch the page via WebFetch, strip boilerplate, analyze the article content.

### Local Files
Read directly. Works for saved articles, notes, code files, PDFs.

### Topic Search (no URL)
Use WebSearch to find 3-5 most relevant results. Fetch top results via WebFetch. Synthesize across sources. Always cite sources.

### Large Content
If source is too large for single analysis, summarize sections and focus on what's most relevant to user's comments/context.

## Rules

- **Write as you go, don't hold it in the response.** Findings land in
  `docs/research/<topic>.md` incrementally — Phase 1 is on disk *before* the
  Phase 2 gate, so an unapproved or interrupted run still leaves the analysis
  behind. Chat reply is the file path plus a short summary, never the full
  analysis (#12955)
- Phase 2 MUST NOT start without explicit user approval after Phase 1
- Always cite specific files, functions, or sections when making claims
- When comparing to AutoBot, read actual code — don't assume based on file names
- **Audit-first gate:** no item enters "What We Can Adopt" without an already-exists audit (grep + read the candidate AutoBot modules, cite what was checked); capability already exists → it moves to "What We Already Do Better"; partially exists → describe only the missing delta
- **Hidden-metrics gate:** every verdict weighs hidden metrics against visible ones — the option with worse visible metrics wins when hidden costs outweigh the advertised gains; a verdict citing only visible metrics is incomplete
- Keep each section concise — depth over breadth
