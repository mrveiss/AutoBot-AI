---
name: web-fetch
version: 1.0.0
description: Fetch and extract clean text content from any public URL using Jina Reader
author: mrveiss
category: internet
tools:
  - fetch_url
  - fetch_url_json
  - fetch_url_text
triggers:
  - fetch URL
  - read webpage
  - get content from URL
  - open link
  - browse to
  - what does this page say
  - summarize URL
  - download webpage
tags:
  - web
  - fetch
  - jina
  - url
  - scraping
  - content-extraction
---

## Capability Tiers

```
┌─────────────────────────────────────────────────────────────┐
│ web-fetch                                                     │
├─────────────────────────────────────────────────────────────┤
│ STANDALONE   (always works, zero config)                     │
│   • Fetch any public URL as clean markdown via Jina Reader   │
│   • wget / httpx fallback when Jina is down or rate-limited  │
│   • JSON + plain-text output modes                           │
├─────────────────────────────────────────────────────────────┤
│ SUPERCHARGED (unlocks when you connect a tool)               │
│   • Jina API key    → higher rate limits, larger responses   │
└─────────────────────────────────────────────────────────────┘
```

**STANDALONE — always works, zero config**

- Fetch and extract clean markdown from any HTTP/HTTPS URL through the public
  Jina Reader endpoint (no key required).
- Automatic graceful degradation: Jina Reader → `wget` → `httpx` if the
  preferred path is unavailable or rate-limited.
- `markdown` (default), `json`, and `text` output modes.

**SUPERCHARGED — unlocks per connected tool**

| Connect this | Unlocks |
|--------------|---------|
| `api_key` — Jina API key | Higher request rate limits and larger extracted-text responses than the anonymous tier. |

Nothing here changes the degradation logic — an unset key simply keeps the skill
on the anonymous STANDALONE tier.

## Output Contract

Every fetch returns this fixed shape so callers can rely on the structure:

```
## Fetched: <page title or URL>

**Source:** <final URL after redirects>
**Tier used:** jina | wget | httpx
**Extracted:** <approx word/char count>

<clean markdown / text / JSON body>
```

- `Tier used` names which path in the fallback chain produced the result.
- On total failure the contract collapses to a single line:
  `Unreachable: <url> — <reason>` (see Fallback Instructions).

## When to Use

Use this skill whenever an agent needs to read the content of a public URL — news
articles, documentation pages, blog posts, or any HTTP-accessible resource.
Prefer this skill over raw curl or wget because Jina Reader returns clean,
LLM-ready markdown without ads, navigation, or boilerplate HTML.

## Workflow

### Primary path — Jina Reader (preferred)

```bash
# Fetch as clean markdown (default)
curl -s 'https://r.jina.ai/{url}'

# Fetch as JSON with title, url, content, and description fields
curl -s -H 'Accept: application/json' 'https://r.jina.ai/{url}'

# Fetch as plain text only
curl -s -H 'X-Return-Format: text' 'https://r.jina.ai/{url}'
```

Steps:
1. Prepend `https://r.jina.ai/` to the target URL.
2. Run the curl command and capture stdout.
3. Pass the clean markdown directly to the LLM context.

### Fallback path — wget (when Jina is unavailable or rate-limited)

```bash
wget -q -O - '{url}'
```

### Fallback path — httpx (async-capable alternative)

```bash
httpx '{url}'
httpx '{url}' --json
```

## Output Format

- **Default (markdown):** Clean article text in CommonMark markdown. Headings, code
  blocks, and lists are preserved. Images are omitted.
- **JSON mode:** Object with keys `title`, `url`, `content` (markdown), and
  `description`. Use for structured extraction.
- **Text mode:** Raw plain text without any markdown formatting.

## Parameters

| Parameter | Type   | Required | Description                        |
|-----------|--------|----------|------------------------------------|
| url       | string | yes      | Fully-qualified HTTP/HTTPS URL     |
| format    | string | no       | `markdown` (default), `json`, `text` |
| api_key   | string | no       | Jina API key for higher rate limits |

## Limitations

- JavaScript-heavy single-page apps may render incompletely; use a browser-based
  tool for those cases.
- Rate limited to ~20 requests/minute without a Jina API key.
- Does not handle URLs that require authentication or session cookies.
- Maximum response size is approximately 100 KB of extracted text.

## Fallback Instructions

If Jina Reader returns an empty response or HTTP 429:
1. Wait 5 seconds and retry once.
2. If still failing, fall back to `wget -q -O - '{url}'`.
3. If wget also fails, report the URL as unreachable and ask the user for
   alternative access (e.g., paste the content manually).
