# Knowledge base round trip — acceptance procedure (#17527)

The criterion, verbatim from #17527:

> a document added by each of the four paths is retrievable via chat **and** via the
> Company OS module, with its source identifiable. If any path cannot demonstrate that, it
> is not done.

**This procedure has not been run.** It needs a live instance, and running against
a deployed system is not something an agent session does on its own. It is written
so that whoever has that sanction can execute it without re-deriving the steps, and
so the result is unambiguous either way.

## Why a test suite cannot close this criterion

`knowledge/provenance_test.py` and `llc/tests/test_context_builder_document_sources.py`
pin the *contract*: each intake leg's metadata resolves to an origin, and the Company OS
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

## Retrieval B — the Company OS module

Exercise the Company OS context path that builds agent context from the KB
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

## What this procedure leaves behind, and who can remove it

**Read this before running it.** The procedure writes data into a live knowledge
base, and **no agent removes stored data on its own** — deleting, rewriting or
rotating stored data is proposed by an agent and approved by a human through the
review queue ([#17038](https://github.com/mrveiss/AutoBot-AI/issues/17038)). So every
row below is a human's to clean up, and running this is a decision to create it.

| leg | what remains |
|---|---|
| 1 Manual entry | one fact: Redis projection, Chroma vector, durable fact-store row |
| 2 File upload | the same three, plus the stored file and its page-offset metadata |
| 3 Transcriber | one fact per non-empty segment — a short recording is tens of facts — plus a `kb_pushes` row, plus the recording itself |
| 4 Watch folder | one fact per file, **plus a persisted watch-folder config** under `kb:watch_folder:*` that keeps watching after the run |
| 5 Connector | one fact per fetched item, **plus a persisted connector config** and any stored credential for it |

Two of the five leave **configuration**, not just facts: the watch folder keeps
ingesting anything dropped into it, and the connector keeps its schedule. Those are
the rows to undo first, because they continue producing data after the procedure ends.

The transcriber leg is the largest by volume — its push is one fact per segment, so
the count scales with the recording's length. Use the shortest recording that still
transcribes.

**Recommended:** use a dedicated collection per run, named with the run's date, so
the facts are identifiable as test data afterwards without needing the nonce. The
nonce makes them *findable*; a collection makes them *groupable*, which is what a
human deleting them will want.

## Recording the SHA, twice

State the deployed commit **before and after** the run. A continuously-updated
deployment can move mid-procedure, and a five-leg ingest is not instantaneous — a
result spanning two SHAs is a result about neither. If they differ, the run is
inconclusive and should be repeated, not reported with a range.

## Recording the result

Per leg, per surface, one of: **pass**, **content missing**, or **provenance
missing** — the last two are different failures with different owners, and
collapsing them into "failed" is what has made this subsystem hard to finish.

A leg that passes chat and fails Company OS is not a passing leg. The criterion is `and`.

## What a pass licenses

Ticking #17527's last criterion, and only for the legs actually run. A leg not
exercised stays unticked with the reason — an untested leg recorded as passing is
the failure mode this whole issue exists to remove.

## Reading provenance: one accessor, no canonical write shape yet (#17527, #17618)

Readers ask `knowledge.provenance.document_origin(metadata)` (or `document_origins(chunks)`);
it speaks all five stored dialects and returns `None` for a shape it does not recognise.
**No canonical write shape is introduced here**: every leg still writes what the table above
shows, so stored facts need no migration. The ruling on a canonical vocabulary stays with the
owner (options on #17527); when it lands, the accessor gains the new shape and keeps the old
ones readable.

Consumers migrated: `llc/kb/context_builder.py` (`document_sources`, beside the unchanged
tenancy `sources`) and `knowledge/search_components/agentic_search.py` (citation label).
`repo_tests/provenance_accessor_17527_test.py` fails a hand-rolled read of a dialect-specific
key outside `knowledge/provenance.py`; the files that read one to answer a different question
are listed there with the question each asks.
