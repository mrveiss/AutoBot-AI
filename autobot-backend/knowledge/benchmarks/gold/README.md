# Retrieval gate gold sets (#20949)

Versioned query sets for the retrieval benchmark gate (`knowledge/retrieval_gate.py`).

## Files

| Name | Purpose |
|---|---|
| `fixture_<bucket>.jsonl` | Small CI set, one file per bucket: docs, code, memory, facts, patterns, cross. |
| `fixture_corpus.jsonl` | Fixture corpus (`{id, bucket, text}`) the fixture queries point into. |
| `live_<bucket>.jsonl` | Larger set curated by the owner against the live index. Same dir, separate name. Not shipped here. |

The gate loads `<set>_<bucket>.jsonl`; the set is `AUTOBOT_RETRIEVAL_GATE_GOLD_SET` (`fixture` or `live`),
the directory `AUTOBOT_RETRIEVAL_GATE_GOLD_DIR`.

## Row schema

One JSON object per line: `{"id": str, "query": str, "bucket": str, "gold": [doc_id, ...] | {doc_id: gain}}`.
`bucket` must be one of the six above and match the file. `id` is unique across the set. A list means gain 1 each.

## Frozen test split

The dev/test split is derived from the query `id` by SHA-256 (same hash as `rag_benchmarks`), so a query never
changes side when others are added. The test split is the held-out one: never tune on it, and change an existing
`id` or its gold only through a reviewed change, because that moves the baseline.

## Contradiction rate

The contradiction metric needs a detector with no default: the existing one
(`services/knowledge/contradiction_detector.py`) calls an LLM. Live gate runs must supply `has_conflict`
to `run_ablation`; without it the metric is unmeasured (`None`) and the gate rejects. Fixture runs
(`knowledge.retrieval_gate_fixture:factory`) give no answers, so grounding is unmeasured there too: the fixture
set checks the metric and plumbing deterministically, not acceptance.
