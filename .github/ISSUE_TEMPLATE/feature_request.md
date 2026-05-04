---
name: Feature request
about: Suggest an idea for AutoBot
title: "[FEATURE] "
labels: feature
---

## Description
A clear and concise description of the feature.

## Use Case
Why would this be useful? What problem does it solve?

## Proposed Solution
How should this work?

## Alternatives Considered
Any other approaches you've thought of?

## Additional Context
Any other context?

## Acceptance Criteria — Implementation

What does it take to call the code complete?

- [ ] Code merged to `Dev_new_gui`
- [ ] Unit tests for the new module(s)
- [ ] Linting clean
- [ ] (other implementation-level criteria specific to this feature)

## Acceptance Criteria — Integration (#6836)

What does it take to call the feature **shipped**? Without this section, the issue is at risk of being closed prematurely (see #6836 for the orchestration audit that surfaced 3,906 LOC of completed-but-unwired features).

- [ ] At least one **production** caller imports each new module:
  `grep -rn 'from <new_module>' autobot-backend autobot-frontend --include="*.py" --include="*.ts" --include="*.vue" | grep -v _test` → ≥1 hit
- [ ] At least one **integration test** exercises the production code path
- [ ] Feature flag default documented (or N/A if always-on)
- [ ] Closure comment lists the production caller `path:line` for each new module

> If the feature is genuinely infrastructure-only (Protocol, shared lib, future-feature scaffold) and no caller exists by design, file a follow-up "wire-in" issue **before** closing this one and reference it under a `### Wire-in deferred to #NNNN` header.
