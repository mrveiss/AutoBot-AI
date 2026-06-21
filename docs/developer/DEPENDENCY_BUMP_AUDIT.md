<!-- Copyright (c) 2025-2026 mrveiss -->
# Dependency bump-to-latest audit (2026-06-21)

Snapshot of direct dependencies whose **latest** release is a **major-version**
jump beyond the declared `>=` floor. These were deliberately **left for a
controlled upgrade** (not included in the security + safe-minor pass) because a
major bump can break the build or change runtime behaviour.

The safe same-major floor raises (anthropic, beautifulsoup4, fastapi,
llama-index-core, mcp, pillow, pydantic, sqlalchemy, uvicorn, asyncssh) were
applied separately in this PR.

## Major-version gaps (deferred)

| Package | Floor | Latest | Risk | Why deferred / what changes |
|---|---|---|---|---|
| **protobuf** | `>=5.29.6,<7.0.0` | `7.35.1` | **High** | The `<7.0.0` cap is intentional: `grpcio`, `opentelemetry-proto` and other consumers pin `protobuf<7` transitively. Bumping requires those ecosystems to ship protobuf-7-compatible generated code first. protobuf 6→7 also regenerates `*_pb2.py` stubs (the upgrade dropped the pure-python fallback default). **Do not raise the cap until grpcio/opentelemetry support protobuf 7.** |
| **reportlab** | `>=4.0.0` | `5.0.0` | **Medium** | PDF export (transcriber exports, report generation). reportlab 5.0 drops older Python and adjusts some canvas/platypus APIs. Needs a PDF-generation smoke test (export a transcript + any report path) before raising. |
| **structlog** | `>=25.5.0` | `26.1.0` | **Low** | Dev/logging only (`requirements-dev.txt`). CalVer bump (25→26); historically additive. Verify `createLogger`/structlog processor config still initialises, then raise. |

## Recommended upgrade order (when greenlit)
1. **structlog** (lowest blast radius; dev-only) — bump, run the suite, confirm log init.
2. **reportlab** — bump, run a real PDF export end-to-end, eyeball output.
3. **protobuf** — **blocked** until `grpcio` + `opentelemetry-*` drop their `<7`
   pins; regenerate any committed `*_pb2` stubs; full smoke + gRPC path test.

## Transitive note
`pip list --outdated` reports ~166 outdated packages in the resolved env, but the
vast majority are **transitive** (pulled by direct deps). Those float with their
parents and are not pinned here — Dependabot's security updates cover the
vulnerable ones. This audit intentionally scopes to **direct** declared deps.

## How this snapshot was produced
`pip list --outdated --format=json` cross-referenced against the `>=` floors in
`requirements*.txt` + `autobot-backend/requirements*.txt`, split by
major-vs-same-major using the floor (not the stale local install) as the baseline.
