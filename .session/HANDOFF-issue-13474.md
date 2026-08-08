# Handoff: issue-13474

status: complete
pr: #13735
issue: #13474 (part of umbrella #13467)
base_at_push: 319c0012704747b1712872b898693262ff00a95b (origin/Dev_new_gui, 0 commits behind at handoff)
gates: lint=PASS (flake8 clean, all changed files) tests=PASS (163 targeted; api/ suite 1397 passed with 9 pre-existing live-service failures, identical on base)
needs_rebase_before_merge: no

## What landed

`PropertyGraph.shortest_path` had no production caller (#8198 closed on the
implementation, not the wiring). Wired through two surfaces with one
implementation behind both:

- `PropertyGraphMixin.find_path` — name -> node-id resolution + serialisation.
  The ONLY call site of `shortest_path`; REST and MCP both delegate here so they
  cannot drift apart.
- `POST /graph-rag/path` via `GraphRAGService.find_connection_path`.
- `memory.path` MCP tool (`max_depth` clamped to 10).

Two calls beyond a pass-through, both argued in the PR body:

1. `shortest_path` gained `direction` (default `"outgoing"` — no #8198 caller
   changes meaning). Without it the endpoint answers "no path" for pairs one hop
   apart, since only `bidirectional=True` relations are mirrored. Each hop is
   tagged with the direction it was crossed.
2. Traversal failures propagate instead of degrading to `found: false` — an
   outage must not be indistinguishable from an answer.

## Verification artifact

`tests/memory_graph/test_shortest_path_wiring_13474.py` — end-to-end chain with
nothing stubbed between layers (endpoint -> service -> mixin -> PropertyGraph ->
FakeRedis). This is the issue's stated acceptance criterion.

## Known deviation (already stated on the issue and in the PR)

The issue proposed `grep shortest_path | grep -v autobot_memory_graph/` as
verification. That grep still returns nothing and SHOULD: the sole call site is
`property_graph_mixin.py`, inside the package, because that is where name->id
resolution belongs. The equivalent check one layer out (`grep find_path`) returns
the two real production callers. Do not "fix" this by moving resolution into the
service — that leaks node-id concerns into the RAG service and forces the MCP
tool to duplicate it.

## Carried forward, NOT done here

- **#13740** (filed) — `with_error_handling` returns the raw exception type and
  message to HTTP clients across 1913 endpoints. Discovered via this PR's
  failure-propagation test. Off-task, blast radius too wide for this PR.
- **Pre-existing, unchanged:** `get_entity(entity_name=...)` resolves names via
  `search_entities(query=name, limit=1)` — fuzzy, so a near-miss matches a
  different entity instead of reporting `entity_not_found`. Mitigated by echoing
  the resolved id+name in the response. Same behaviour `create_relation` already
  depends on in this mixin.
- No GUI surface — out of scope per the issue.
- #13475 (MCP code-structure tools) is the sibling this was meant to ship
  alongside; still unbuilt.

## Test-double refactor to be aware of

`FakeRedis`/`make_graph` moved out of `test_property_graph.py` into
`tests/memory_graph/graph_test_doubles.py` so the wiring test drives the same
in-memory graph rather than a second copy. The move also cleared 7 unused imports
already dead at base in that file. If you add memory-graph tests, import the
doubles from there.

worktree: .worktrees/issue-13474 (locked; safe to remove after #13735 merges)
