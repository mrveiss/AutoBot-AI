---
name: rss-reader
version: 1.0.0
description: Parse and monitor RSS and Atom feeds using the feedparser Python library
author: mrveiss
category: internet
tools:
  - parse_feed
  - list_entries
  - get_entry_content
  - check_feed_info
triggers:
  - read RSS feed
  - parse RSS
  - Atom feed
  - subscribe to feed
  - latest news from
  - check blog updates
  - feed URL
  - RSS URL
  - feedparser
tags:
  - rss
  - atom
  - feed
  - feedparser
  - news
  - monitoring
  - content-aggregation
---

## Capability Tiers

```
┌─────────────────────────────────────────────────────────────┐
│ rss-reader                                                    │
├─────────────────────────────────────────────────────────────┤
│ STANDALONE   (always works, zero config)                     │
│   • Parse any public RSS/Atom feed with feedparser           │
│     (tolerant of malformed XML, no auth)                     │
├─────────────────────────────────────────────────────────────┤
│ SUPERCHARGED (unlocks when you connect a tool)               │
│   • atoma parser         → typed Atom objects on strict feeds │
│   • Custom User-Agent /  → feeds that reject the default      │
│     Accept header           request                          │
└─────────────────────────────────────────────────────────────┘
```

**STANDALONE — always works, zero config**

- Parse any public RSS or Atom feed with `feedparser`; both formats are detected
  automatically and malformed XML is tolerated.
- List titles, extract entries as JSON, read full entry content, and inspect
  feed metadata — all without authentication.

**SUPERCHARGED — unlocks per connected tool**

| Connect this | Unlocks |
|--------------|---------|
| `atoma` parser | Strongly-typed Atom entry objects for strict Atom feeds where `feedparser` degrades. |
| Custom `User-Agent` / `Accept` header handler | Feeds that reject the default request (403 / empty body) become readable. |

These are graceful fallbacks — the skill defaults to `feedparser` and only needs
the extras for the minority of feeds that require them.

## Output Contract

Feed reads return this fixed shape:

```
## Feed: <feed title>

**URL:** <feed_url>   **Type:** rss | atom   **Entries:** <n>
**Parser:** feedparser | atoma

| # | Title | Published | Link |
|---|-------|-----------|------|
| 1 | ...   | ...       | ...  |
```

Single-entry content mode returns the raw entry body (HTML or plain text) under
a `## <entry title>` heading.

## When to Use

Use this skill when an agent needs to read news, blog posts, or any content
published via an RSS or Atom feed. feedparser handles both feed formats
automatically, tolerates malformed XML, and requires no authentication for
public feeds.

## Workflow

### List entry titles from a feed

```bash
python3 -c "
import feedparser
d = feedparser.parse('{feed_url}')
for e in d.entries[:10]:
    print(e.title)
"
```

### Get entries as JSON with metadata

```bash
python3 -c "
import feedparser, json
d = feedparser.parse('{feed_url}')
entries = [
    {
        'title': e.title,
        'link': e.link,
        'published': e.get('published', ''),
        'summary': e.get('summary', '')[:200],
    }
    for e in d.entries[:10]
]
print(json.dumps(entries, indent=2))
"
```

### Check feed metadata (title, type, entry count)

```bash
python3 -c "
import feedparser
d = feedparser.parse('{feed_url}')
print('Feed title:', d.feed.get('title', 'N/A'))
print('Feed version:', d.version)
print('Entry count:', len(d.entries))
print('Bozo (parse error):', d.bozo)
"
```

### Get full content of the first entry

```bash
python3 -c "
import feedparser
d = feedparser.parse('{feed_url}')
e = d.entries[0]
content = e.get('content', [{}])[0].get('value', e.get('summary', 'No content'))
print(content)
"
```

### Fallback — atoma (typed objects, Atom feeds only)

```bash
python3 -c "
import atoma, requests
feed = atoma.parse_atom_bytes(requests.get('{feed_url}').content)
for e in feed.entries[:5]:
    print(e.title.value)
"
```

## Output Format

- **List mode:** One entry title per line; suitable for quick enumeration.
- **JSON mode:** Array of entry objects with `title`, `link`, `published`,
  and `summary` fields.
- **Content mode:** Raw HTML or plain text body of the selected entry; pass
  through a markdown converter if needed.

## Entry Fields Reference

| Field                    | Description                              |
|--------------------------|------------------------------------------|
| `title`                  | Entry headline                           |
| `link`                   | URL to the full article                  |
| `summary` / `description`| Entry excerpt or full text               |
| `published` / `updated`  | Date string (not always present)         |
| `author`                 | Author name                              |
| `tags`                   | List of category/tag objects             |
| `content`                | Full content list (Atom feeds only)      |

## Parameters

| Parameter | Type   | Required | Description                                         |
|-----------|--------|----------|-----------------------------------------------------|
| feed_url  | string | yes      | Fully-qualified RSS or Atom feed URL                |
| limit     | int    | no       | Maximum number of entries to return (default 10)    |
| field     | string | no       | Specific field to extract (e.g., `title`, `link`)   |

## Limitations

- feedparser does not execute JavaScript; feeds served via JS redirects will
  parse empty.
- Entry dates are not guaranteed — use `e.get('published', e.get('updated', ''))`
  for safe access.
- Very large feeds (thousands of entries) may be slow; slice with `d.entries[:n]`.
- Some feeds require an `Accept` header or specific `User-Agent`; pass a custom
  handler if the default request is rejected.
- feedparser does not validate feed signatures or SSL certificates beyond the
  system trust store.

## Fallback Instructions

If feedparser returns an empty `entries` list:
1. Check `d.bozo` — if `True`, inspect `d.bozo_exception` for the parse error.
2. Try fetching the feed URL with `curl -s '{feed_url}'` to confirm the server
   returns valid XML.
3. If the feed is a Atom format and feedparser fails, try atoma as the fallback
   parser.
4. If the URL redirects to a login page or requires authentication, report the
   feed as inaccessible and ask the user for credentials or an alternative URL.
