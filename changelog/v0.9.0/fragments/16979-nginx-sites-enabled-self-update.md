---
type: fix
scope: infrastructure
issue: 16979
pr: 0000
---
Self-update now makes every re-rendered nginx site live, not just the SLM site: a node whose `sites-enabled` entry was a stale regular file kept serving a frozen config indefinitely, because the steps that replaced and linked it ran only on a full provision. The render and the enable now live in the same ansible task file for the SLM site, the frontend site, and the co-located re-render path, each asserting afterward that `sites-enabled` resolves to the rendered file and failing loudly if it does not. A new guard test enforces this pairing across the whole ansible tree so a future site render cannot reintroduce the gap.
