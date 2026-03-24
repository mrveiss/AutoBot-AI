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
