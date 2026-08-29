---
tags:
  - index
  - archives
aliases:
  - Archives Index
---

# Archives

Historical documents preserved for reference. Not actively maintained.

## Implementation Plans

Dated design and implementation plans — see [plans/_index.md](plans/_index.md).

## Historical Records

| Document | Description |
| --- | --- |
| [changelog_20250822](changelog_20250822.md) | Session changelog from August 2025 |

## Addressing in these documents was redacted after archival (#15208)

Every plan under `plans/` was written before the placeholder convention #3315 introduced
existed, and each one named the fleet's nodes by literal address — including
role-to-host assignments and database endpoints, which together describe the network
rather than any one machine. #15208 replaced those literals with the role placeholders
defined in [../architecture/VM_ROLES.md](../architecture/VM_ROLES.md), the same form and
the same names #3315 applied to the live documentation.

Read them accordingly: **the placeholders are not what the original documents said.**
Where an archived plan quotes source code, a configuration file or a command, a
placeholder stands in for a literal the historical artifact contained. Nothing else in
these documents was altered — no text was removed, and no value was blanked, so each plan
still explains the layout it was written to explain.

`tools/lint/check_docs_no_fleet_addressing.py` keeps the archives in scope from now on,
which they were not during #3315.
