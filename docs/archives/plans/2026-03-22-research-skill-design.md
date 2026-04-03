# Research Skill Design (#1982)

**Date:** 2026-03-22
**Status:** Approved
**Skill location:** `.claude/skills/research/SKILL.md`

## Overview

A Claude Code slash command (`/research`) that analyzes web articles, GitHub repos, or local files to extract patterns and insights applicable to AutoBot.

## Design Decisions

### Two-Phase Interactive Flow
- **Phase 1 — Understand Source:** Fetch and analyze the input, present structured findings, pause for user reaction
- **Phase 2 — Compare to AutoBot:** Only on user approval, dig into AutoBot codebase and produce actionable comparison

**Why two phases:** User stays in control. Can skip Phase 2 if source isn't relevant. Can steer Phase 2 to specific areas.

### Input Flexibility
Accepts four input types, auto-detected:
- GitHub repo URLs → fetches README, structure, key files
- Web article URLs → WebFetch + content extraction
- Local file paths → direct Read
- Plain text topics → WebSearch + fetch top results

### Chat-Only Output
No file writing. User reviews findings in conversation, then decides whether to create design docs or GitHub issues.

### Source-Specific Strategies
- **Large repos:** Prioritize README, directory structure, entry points, files matching user comments
- **Topic search:** WebSearch for 3-5 results, fetch and synthesize with citations
- **Large content:** Summarize sections, focus on relevance to user context

## Output Structure

### Phase 1
- What It Is (summary, maturity)
- Architecture & Key Patterns
- Notable Implementation Details
- Strengths
- Weaknesses / Limitations

### Phase 2
- What We Can Adopt (with effort estimates)
- What We Already Do Better
- Gaps & Opportunities (prioritized by impact)
- Specific Code/Files Affected
