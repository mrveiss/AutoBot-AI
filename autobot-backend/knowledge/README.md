# Knowledge Base & RAG Benchmarks

This directory owns the RAG (retrieval-augmented generation) stack and its
benchmark harness.

## Benchmark Discipline (Issue #5074)

**Any metric published externally must be a `held_out_score`.** Tuning
happens on `dev`; the final score comes from `test`, never the reverse.

### Why this matters

`knowledge/rag_benchmarks.py` and the `POST /rag/benchmark/run` endpoint
let us run a precision@k benchmark over a dataset and report a score. If
we tune hyperparameters on the same set that produces the headline number,
we are silently teaching to the test — the number looks good in isolation
but will not generalise to real user queries.

To prevent this, the dataset is split into two disjoint groups:

- **`dev_ids`** — used for hyperparameter search, reranker thresholds,
  chunk-size experiments, prompt tweaks, etc.  Metrics derived from this
  split are **not** suitable for external reporting.
- **`test_ids`** — held out from all tuning activity.  A metric derived
  from this split, with no dev leakage during the run, is a
  `held_out_score` and is the only number that should appear in docs,
  release blog posts, or dashboards shown to users.

### The split is deterministic

`BenchmarkDataset.from_ground_truth(...)` uses a SHA-256 hash of the
query text modulo 100, with an 80/20 threshold.  The same query always
lands in the same split; adding or removing queries doesn't reshuffle
existing assignments.

### API contract

`POST /rag/benchmark/run` requires a body:

```json
{ "split": "dev" | "test" | "all", "k": 5 }
```

The response shape includes:

- `split_used` — which split was actually run.
- `dev_size`, `test_size` — total queries in each split.
- `tuned_on_dev` — whether the harness has completed a tune() pass.
- `held_out_score` — **True iff** `split_used == "test"` **and** no
  dev-set access occurred during the run.  Any other combination is
  `False`.
- `mean_precision_at_k` — mean precision across results in this run.

### Programmatic use

```python
from knowledge.rag_benchmarks import (
    BenchmarkHarness,
    BenchmarkSplit,
    get_default_dataset,
    run_benchmark_suite,
)

harness = BenchmarkHarness(dataset=get_default_dataset())

# 1. Tune on dev — raises RuntimeError if you touch a test_id.
tune_report = harness.tune(
    lambda ds: run_benchmark_suite(collection, dataset=ds, split=BenchmarkSplit.DEV)
)

# 2. Final held-out score on test — raises RuntimeError if you touch a dev_id.
test_report = harness.score(
    lambda ds: run_benchmark_suite(collection, dataset=ds, split=BenchmarkSplit.TEST)
)
assert test_report.held_out_score is True
```

### Feedback events (Issue #4676 interaction)

`publish_feedback_events()` tags every event written to
`rag:feedback:__global__:<date>` with a `split_used` field.  The
`RetrievalLearner` can therefore exclude `split_used == "test"` events
from any training pass — the test split must never feed back into the
system it is supposed to measure.

### Rules of thumb

- Do **not** iterate on the test split.  If you find yourself re-running
  `split=test` to see whether a change helped, you are (by definition)
  tuning on it.  Go back to `split=dev`.
- If the dev and test means diverge strongly (e.g. dev goes up, test
  goes down), that is overfitting — trust the test number.
- When in doubt, report the test number with the `held_out_score=true`
  flag alongside it.  No exceptions.
