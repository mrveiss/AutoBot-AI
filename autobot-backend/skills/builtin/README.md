# Built-in Agent Skills — Authoring Guide

This directory holds AutoBot's built-in **agent runtime skills**. Each skill is a
`SKILL.md` file (`<skill-name>/SKILL.md`) that the agent reads to learn *when* to
use a capability and *how* to run it. These are distinct from the developer
workflow skills under `.claude/skills/` — those drive Claude Code sessions; these
drive the running agent.

## File layout

```
autobot-backend/skills/builtin/
├── README.md                       ← this guide
├── web_fetch/SKILL.md
├── github_search/SKILL.md
├── youtube_transcript/SKILL.md
└── rss_reader/SKILL.md
```

## SKILL.md structure

Only the YAML front-matter (delimited by `---` lines at the top) is machine-parsed
by [`manifest_parser.py`](../manifest_parser.py). The markdown body below the
front-matter is free-form prose read by the agent. Required front-matter fields:
`name`, `version`, `description`; recommended: `category`, `tools`, `triggers`,
`tags`, `author`.

The body should follow this section order:

1. `## Capability Tiers` — **required** (see below)
2. `## When to Use`
3. `## Workflow`
4. `## Output Format` / `## Output Contract` — **output contract required** for
   skills that return findings (research, search, KB lookups)
5. `## Parameters`
6. `## Limitations`
7. `## Fallback Instructions`

## Capability Tiers convention (required)

Every skill declares two capability tiers so users can see what works out of the
box versus what a connected tool unlocks. Document the **real** behavior of the
skill's graceful-degradation chain — never invent tool integrations.

- **STANDALONE** — always works, zero config. What the skill can do with no keys,
  no login, and no external service configured (including its built-in fallback
  chain, e.g. Jina Reader → `wget` → `httpx`).
- **SUPERCHARGED** — unlocks per connected tool. What each optional
  provider/connector/credential adds on top. An unset connector must simply keep
  the skill on the STANDALONE tier — connecting a tool never changes the
  degradation logic itself.

Lead the section with a small ASCII capability box, then spell out each tier:

```
## Capability Tiers

┌─────────────────────────────────────────────────────────────┐
│ <skill-name>                                                 │
├─────────────────────────────────────────────────────────────┤
│ STANDALONE   (always works, zero config)                     │
│   • <what works with nothing connected>                      │
├─────────────────────────────────────────────────────────────┤
│ SUPERCHARGED (unlocks when you connect a tool)               │
│   • <connector> → <what it adds>                             │
└─────────────────────────────────────────────────────────────┘

**STANDALONE — always works, zero config**
- ...

**SUPERCHARGED — unlocks per connected tool**

| Connect this | Unlocks |
|--------------|---------|
| <credential / connector> | <capability it adds> |
```

(Fence the box with triple backticks in the real file so it renders literally.)

## Output Contract convention (required for result-returning skills)

Skills that return findings (research, search, KB lookups) must document a fixed
output shape so callers and downstream summarizers can rely on the structure.
Match Anthropic's **Summary → findings table → verdict** discipline:

```
## Output Contract

## <title>

**Summary:** one-to-three sentence answer.

### Findings

| # | Source | Provider/Tier | Key point |
|---|--------|---------------|-----------|
| 1 | ...    | ...           | ...       |

**Verdict:** bottom-line conclusion + confidence + any caveat
(e.g. "no provider configured — direct sources only").
```

Always include a `Tier used` / `Provider` marker in the output so consumers can
see which point in the fallback chain produced the result. Define the degraded
single-line shape too (e.g. `Unreachable: <url> — <reason>`).

## Rules

- Document **only real behavior**. Read the skill's actual fallback chain (and,
  for topic search, the credential-gated
  [`agent_loop/search/registry.py`](../../agent_loop/search/registry.py)) — do
  not fabricate integrations.
- STANDALONE must genuinely require zero config. If a capability needs a key or
  login, it belongs in SUPERCHARGED.
- Keep the ASCII box aligned and the tables valid markdown.
