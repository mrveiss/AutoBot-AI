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

- Output goes to chat only — no file writing unless user asks
- Phase 2 MUST NOT start without explicit user approval after Phase 1
- Always cite specific files, functions, or sections when making claims
- When comparing to AutoBot, read actual code — don't assume based on file names
- Keep each section concise — depth over breadth
