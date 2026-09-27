# Knowledge base round trip — acceptance procedure (#17527)

The criterion, verbatim from #17527:

> a document added by each of the four paths is retrievable via chat **and** via the
> LLC module, with its source identifiable. If any path cannot demonstrate that, it
> is not done.

**This procedure has not been run.** It needs a live instance, and running against
a deployed system is not something an agent session does on its own. It is written
so that whoever has that sanction can execute it without re-deriving the steps, and
so the result is unambiguous either way.

## Why a test suite cannot close this criterion

`knowledge/provenance_test.py` and `llc/tests/test_context_builder_document_sources.py`
pin the *contract*: each intake leg's metadata resolves to an origin, and the LLC
surface exposes it. Neither ingests a document, and neither retrieves one. Counting
wiring has misled on this subsystem repeatedly — an endpoint can exist and be
unreachable, a producer can run with a broken consumer (#17022), and an import count
says nothing about whether a traversal returns. Only the round trip answers it.

## Preconditions

- The instance is reachable and its knowledge base initialised.
- Chroma and Redis are up; a KB write touches both plus the durable fact store.
- An admin credential, because the upload endpoint requires one.
- Reach the instance through its documented API surface via the maintenance UI or
  the code-sync/self-update path. Do not side-channel with ad-hoc shell.

## The five legs

Four paths are named in the criterion; the measured state records **five** intake
legs. Run all five — the discrepancy is in the issue, not in the system, and a leg
skipped because the count said four is a leg nobody checked.

For each leg, ingest one document whose text contains a **unique nonce** (a random
token), so retrieval can be searched for unambiguously rather than by a phrase that
may already exist in the store.

| # | leg | how to ingest |
|---|---|---|
| 1 | Manual entry | the add-text form under `/knowledge/manage` |
| 2 | File upload | the upload tab of `/knowledge/manage`; a `.txt` containing the nonce |
| 3 | Transcriber | upload a short recording, wait for `status=complete`, then Push to KB |
| 4 | Watch folder | configure a watched directory, drop a file containing the nonce into it |
| 5 | Connector | configure any connector against a source you control, containing the nonce |

Record for each: the nonce, the leg, and the returned identifier if the surface
gives one.

## Retrieval A — chat

Ask chat a question whose answer requires the nonce document. Chat reaches the KB
through `KnowledgeBase.search()`, whose results carry `metadata`.

**Pass:** the answer uses the document's content, and the response or its context
names where it came from.

**Fail, and the distinction matters:**
- the nonce is not found at all → the ingest leg did not land, or vectorisation did
  not run;
- the nonce is found and nothing says where it came from → retrieval reached it and
  dropped the provenance. Note which of the two, per leg.

## Retrieval B — the LLC module

Exercise the LLC context path that builds agent context from the KB
(`llc/kb/context_builder.py`). Inspect the returned context for both keys:

- `sources` — company ids, the tenancy answer. Present before this work and unchanged.
- `document_sources` — the document origins, added by #17527.

**Pass:** `document_sources` contains the origin of the nonce document, in the form
the accessor produces for that leg — `recording:<id>`, `file:<name>`,
`connector:<type>:<id>`, or the caller's own string for manual entry.

**Fail:** `document_sources` is empty while the chunk is present. Then read the
chunk's `metadata` directly: if the provenance is there, the accessor does not know
that leg's dialect and needs a case adding; if it is not, the ingest leg wrote none.

## Retrieval C — the graph, once #17588 lands

Until then, a `DOCUMENT` node's `source` is the constant `"ecl_pipeline"`, so the
graph cannot attribute anything. Two cautions for whoever checks it afterwards:

- `DOCUMENT` nodes **already exist** for an unrelated reason: the spaCy mapping sends
  `LAW` and `WORK_OF_ART` to `DOCUMENT`. So "do `DOCUMENT` nodes exist?" answers yes
  and means only that some ingested text mentioned a law or an artwork. Assert the
  node is *this document's*, by its id, not that nodes of the type exist.
- `PipelineContext.document_id` already reaches the loader unused, so the fix is an
  attribution rather than a new field.

## Recording the result

Per leg, per surface, one of: **pass**, **content missing**, or **provenance
missing** — the last two are different failures with different owners, and
collapsing them into "failed" is what has made this subsystem hard to finish.

A leg that passes chat and fails LLC is not a passing leg. The criterion is `and`.

## What a pass licenses

Ticking #17527's last criterion, and only for the legs actually run. A leg not
exercised stays unticked with the reason — an untested leg recorded as passing is
the failure mode this whole issue exists to remove.
