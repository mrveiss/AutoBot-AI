# ADR-012: The SLM Is Installed First and Stays Separate

## Status

**Status**: Accepted

Replaces the proposal in [ADR-011](011-one-frontend-admin-namespace.md), which is rejected.

## Date

**Date**: 2026-11-02

## Context

ADR-011 proposed moving the SLM console into the main app under `/admin`, leaving only the SLM backend separate. But the SLM is what installs everything else, so it has to work before the main app exists and while the main app is down. The maintainer ruled: "slm is firs thing user installs and is the point from which other functionality gets installed, we keep it separate".

## Decision

1. The SLM is the first thing installed, and other functionality is installed from it.
2. The SLM stays a separate application, frontend included, reached at `/slm/`.
3. The SLM owns the first login.
4. The SLM keeps working while the main app is down.
5. `/admin` in the main app is for main-app administration only. It does not replace the SLM, and `/slm/` does not redirect to it.

## Consequences

- Two frontends stay, under the shared-code boundary in [ADR-008](008-frontend-shared-code-boundary.md).
- Anything the SLM needs for items 3 and 4 cannot depend on the main app. Gaps found against this are tracked as issues.
- How people link across the two user stores is designed separately (#10193, #10200).
