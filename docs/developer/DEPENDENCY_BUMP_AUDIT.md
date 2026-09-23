<!-- Copyright (c) 2025-2026 mrveiss -->
# Dependency bump-to-latest audit (2026-06-21) — DISCHARGED

**Status: historical. All three deferrals below have landed. Nothing here is a
standing instruction; do not read a "deferred" row as a live block.**

This was a snapshot of direct dependencies whose **latest** release was a
major-version jump beyond the declared `>=` floor, deliberately left for a
controlled upgrade rather than folded into the security + safe-minor pass.
Re-checked against the tree in #15622: every row has since been raised, so the
table is kept as the record of *why* each was held and *what* released it.

The safe same-major floor raises (anthropic, beautifulsoup4, fastapi,
llama-index-core, mcp, pillow, pydantic, sqlalchemy, uvicorn, asyncssh) were
applied separately at the time.

## Major-version gaps — all resolved

| Package | Floor then | Declared now | What released it |
|---|---|---|---|
| **protobuf** | `>=5.29.6,<7.0.0` | `>=7.36.0,<8.0.0` | The consumers raised their own ceiling. See the rule below — the cap moved because `opentelemetry-proto` and `googleapis-common-protos` moved, not because protobuf was re-judged (#15070, #10678, #3973). |
| **reportlab** | `>=4.0.0` | `>=5.0.1` | Raised past the 5.0 major; declared in both `autobot-backend/requirements.txt` and `requirements-ci/document.txt`, so the PDF-export paths are covered by CI rather than by the manual smoke test this row once asked for. |
| **structlog** | `>=25.5.0` | `>=26.1.0` | CalVer bump taken; declared at `>=26.1.0` in `requirements-dev.txt`, `autobot-backend/requirements.txt` and the ai-stack/npu-worker images, pinned `==26.1.0` in `requirements-ci/monitoring.txt`. |

## The protobuf cap is a mirror, not a judgement

The row above originally ended *"do not raise the cap until grpcio/opentelemetry
support protobuf 7"*. That instruction outlived its truth, and re-checking it
turned up two things worth writing down so the next bump does not repeat the
mistake:

1. **`grpcio` was never a constraint.** It is named in the original rationale as
   a blocker pinning `protobuf<7` transitively, but grpcio declares no protobuf
   dependency at all — verified against the resolved metadata of both grpcio
   versions installed across the deployed venvs, which carry zero
   `Requires-Dist: protobuf` lines. Waiting on grpcio would have been waiting on
   a package that was never gating.

2. **The real constraint holders are the proto consumers, and the cap simply
   copies them.** `opentelemetry-proto` declares `protobuf<8.0,>=5.0` and
   `googleapis-common-protos` declares `protobuf<8.0.0,>=4.25.8` (1.75.1:
   `>=6.33.5`). The cap read `<7.0.0` when those packages said `<7`; it reads
   `<8.0.0` because those packages now say `<8`.

**The durable rule:** the protobuf ceiling is whatever the lowest upper bound
declared by protobuf's own transitive consumers is — today `opentelemetry-proto`
and `googleapis-common-protos`. It is not a considered opinion about protobuf N,
so it is never raised by deciding protobuf N is fine. Raise it when, and only
when, those consumers publish a higher ceiling; check their metadata rather than
this sentence, because this sentence is what went stale last time.

The floor moves for a different reason: `>=7.36.0` is where it sits because the
OTLP exporter regenerated its protos (#3973) and `googleapis-common-protos`
1.75.1 requires `>=6.33.5`. Floor and ceiling are independent.

`requirements.txt`, `autobot-backend/requirements.txt` and the ai-stack
`requirements-ai.txt` all declare the same `protobuf>=7.36.0,<8.0.0`; the first
two are held identical by `tools/lint/check_requirements_pin_parity.py`, and
`.github/dependabot.yml` mirrors the ceiling as `versions: [">=8.0.0"]`. A cap
change touches all of them.

## Transitive note
`pip list --outdated` reported ~166 outdated packages in the resolved env at
snapshot time, but the vast majority are **transitive** (pulled by direct deps).
Those float with their parents and are not pinned here — Dependabot's security
updates cover the vulnerable ones. This audit scoped to **direct** declared deps.

## How this snapshot was produced
`pip list --outdated --format=json` cross-referenced against the `>=` floors in
`requirements*.txt` + `autobot-backend/requirements*.txt`, split by
major-vs-same-major using the floor (not the stale local install) as the
baseline. The #15622 re-check instead read the metadata pip actually resolved
into the deployed venvs, which is what caught the grpcio claim.
