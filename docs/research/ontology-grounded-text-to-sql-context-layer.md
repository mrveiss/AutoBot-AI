# Ontology-grounded text-to-SQL context layer

## Linked issues

- #20808 Umbrella: answer correctness — measured, grounded NL→SQL and KB answers that say 'cannot answer'
- #20809 security(nl-database): the read-only guard is a keyword filter only — INTO OUTFILE passes, connections are writable, no timeout
- #20810 feat(nl-database): answerability gate and schema-slice grounding — return coverage and uncovered entities before generating SQL
- #20811 feat(nl-database): validate → precheck → repair loop with an explicit 'unconstructable' outcome
- #20812 feat(rag): question-level entity coverage on knowledge-base answers
- #16982 security(secrets): Secret.is_accessible_by has no production caller (sighting D2 added as a comment)

## Source Analysis: an open-source ontology context layer for agents querying SQL databases

Read on 2026-11-04 from the reference work's public source tree (read-only, no clone). The files read
were the overview docs, the compile pipeline, the answerability grader, the text-to-SQL agent graph,
SQL validation and execution, the connector base, and the tool server. Everything else is known from the
file tree only. Benchmark claims are self-reported.

### What It Is
A self-hosted service from a hardware vendor that runs next to enterprise SQL databases. It compiles
their metadata into an ontology with three kinds of definition: business **terms** mapped to columns,
reviewed **SQL attributes** (measures such as margin or a rolling total), and inferred **relationships**
(joins and bridge tables). Agents then query through tools over the ontology instead of having the raw
schema pasted into their context. People review and *certify* the definitions in a web UI. The project
is about six months old, under active development, and maintained by the vendor.

### Architecture & Key Patterns
- **Five services:** a web frontend that is also the auth gateway, a Python API hosting the text-to-SQL
  agent, a separate ingestion and compile service, a read-only tool server for agents, and a relational
  store with a vector extension (catalog, ontology, embeddings). An optional secrets vault holds
  connection credentials.
- **Three-stage lifecycle:**
  1. *Generate:* ingest schemas, profile and sample columns, extract terms with an LLM per table, infer
     foreign keys and relationships, suggest SQL attributes from query history, then embed.
  2. *Certify:* human review in the UI or over the API.
  3. *Answer:* a graph-based agent.
- **Model roles, not model names:** reasoning, non-reasoning, embedding and rerank roles. Each role has its
  own endpoint, key and model setting, and falls back to a shared default. Any OpenAI-compatible endpoint
  works.
- **Ten SQL connectors** (warehouses, lakehouse engines, embedded databases), each with its own statement
  timeout.
- **Import and export** through an open YAML standard for semantic models.
- **The agent tool surface is read-only by design.** Readiness, term search and lookup, table description,
  `check_answerable` and `ask_question` are reads. Writes go only through the authenticated REST API.

### Notable Implementation Details
- **Answerability as a number.** The agent extracts the entities a question names, then vector-searches
  column attributes, SQL attributes and saved analyses. Hits beyond a distance threshold are dropped, and
  `coverage = covered entities / named entities` is returned with the list of *uncovered* entities. After
  extraction the score is cheap and deterministic, and it gives the agent a concrete reason to ask for
  clarification ("nothing covers *ad spend*").
- **Text-to-SQL as a state machine with typed repair loops:**
  1. Intent, then entity extraction, then candidate retrieval, then evidence refinement.
  2. SQL construction, then parse validation.
  3. A combined precheck against the live database: literal values, join paths and JSON paths.
  4. Execution, then an empty-`LIKE` check and a value-repair check, then formatting.

  A failed check routes back to a reconstruct step under an attempt limit. An explicit *unconstructable*
  terminal makes "this cannot be answered from this data" a first-class outcome rather than a timeout.
- **Vacuous-SQL detection:** a SQL-parser check rejects queries that select only constants or NULLs instead
  of real data, a known failure mode of LLM text-to-SQL.
- **Value anchors:** literals in the question that match schema phrases pull the owning tables into scope
  when retrieval missed them.
- **Deterministic ordering under parallel LLM work:** tables are compiled concurrently, but term commits
  pass through an ordered commit queue, so ownership of colliding names is the same on every run.
  Cancellation drains the backlog in about one table's time, and a per-run sampling circuit breaker
  resets each run.
- **Agent skills split by job** (setup, management, query). Each skill has a "sources of truth, do not
  duplicate" table, so a skill never turns into a second API catalogue or a second installer.
- **PII flagging at ingest:** catalog columns carry a PII-processed marker.

### Strengths
- The answerability score and the explicit unconstructable path directly target confident wrong answers.
- The human certification loop gives one governed, auditable definition per business concept.
- Live-database prechecks of values and join paths run before execution and catch the commonest
  text-to-SQL errors cheaply.
- The evaluation is honest: the same model is run with the schema in the prompt and with the ontology, an
  execution-match verifier scores both, and the report lists the questions that were fixed *and* the ones
  that broke.
- Strong ops packaging: a cluster chart, a compose file, an OpenAPI spec, the tool server, agent skills and
  per-role model endpoints.

### Weaknesses / Limitations
- **Internal services are unauthenticated.** The agent API trusts a user-id header forwarded by the
  frontend, and the ingest, delete, reset and compile endpoints have no authentication of their own.
  Security rests entirely on keeping those ports on a private network.
- **No read-only SQL enforcement was found in the files read.** Validation checks for vacuous selects, not
  for the statement type, and no read-only transaction guard appeared in the execution path or the
  connector base. Not every connector was read, so this is unverified either way. The project probably
  relies on the database role's permissions.
- **Very large modules:** several files are between 60 and 80 KB, which makes them costly to maintain and
  hard to review.
- **Data egress to a hosted predictor:** predictive questions upload the connected tables to an external
  service once that service's key is set, with no row cap by default.
- **Scope is structured SQL only:** no documents and no unstructured knowledge.

### Visible vs Hidden Metrics
- **Visible:** fewer wrong answers on public text-to-SQL benchmarks (self-reported, with a public harness,
  not independently verified), ten connectors, an agent tool server and skills, and wide community
  attention.
- **Hidden:**
  - Five services, plus the store and an optional vault, to operate.
  - An LLM compile pass per database. Its cost scales with table count, and it must be re-run when the
    schema drifts.
  - A standing human curation workload: the ontology is only as trustworthy as the review effort spent
    on it.
  - A network-only security boundary between the internal services.
  - Coupling to an agent-graph framework.
- **Weighing:** the service pays off for an organisation where many analysts ask ad-hoc questions of a
  wide, stable warehouse and staff are available to curate definitions. For a small-team platform the
  operating and curation cost dominates. The transferable value is in the *patterns*: the coverage score,
  the typed repair loop, the vacuous-SQL check and the live prechecks. The service itself is not.

## AutoBot Comparison: the reference work → AutoBot

Audited against `origin/main` at 92572eba98. AutoBot's closest surface is the natural-language→SQL
service, `autobot-backend/services/nl_database_service.py`, behind `autobot-backend/api/nl_database.py`.
Its `query()` (lines 349-390) pastes the whole schema DDL into one prompt (`_build_sql_prompt`), takes
one generation, runs a keyword read-only check, and executes the query. That is exactly the
*schema-in-the-prompt* control arm the reference work's evaluation compares against.

Searches for `text.?to.?sql|nl2sql|ontology|answerab|unconstructable|vacuous` over the non-test files in
`autobot-backend/` and `autobot_shared/` found no answerability grader and no SQL repair loop.

### What We Can Adopt

| # | Pattern | AutoBot target | Already-exists audit | Visible benefit | Hidden cost | Verdict | Effort |
|---|---|---|---|---|---|---|---|
| G1 (#20810) | **Answerability gate and schema-slice grounding.** Extract the question's entities, retrieve only the matching tables and columns (plus value anchors), and return `coverage` and `uncovered_entities` so the caller can ask for clarification instead of guessing. | `nl_database_service.py` `query()` and `_build_sql_prompt` | `query()` goes straight to `_generate_sql` with the full DDL (lines 371-372). There is no entity extraction or coverage. | Fewer confident wrong numbers, and smaller prompts on wide external databases. | An extra LLM call per question, an embedded schema index that goes stale when the schema drifts, and threshold tuning. The gain is unmeasurable until the NL→SQL eval exists (#13415). | Adopt with conditions: after #13415 lands, behind a measured A/B. | Moderate |
| G2 (#20811) | **Validate → precheck → repair loop** with an explicit *unconstructable* outcome. Parse the SQL to an AST, reject vacuous constant-only selects, feed execution errors back for a bounded number of reconstructions, and check literal values when the result is empty. | `nl_database_service.py` `query()`, `_safe_execute_query` | Single shot. An execution error is returned to the user as-is (lines 380-382) with no retry, and no parser is used. | Recovers the commonest text-to-SQL errors cheaply. "Cannot answer" becomes a real result. | More LLM calls and latency per question, and a new SQL-parser dependency (it must go into `constraints/shared.txt`). The prechecks run extra queries against the user's database. | Adopt with conditions: after #13415, attempt cap from config. | Moderate–significant |
| G3 (#20812) | **Question-level coverage score for knowledge-base answers.** Report the share of the question's entities that the retrieved chunks or graph entities cover, and list the uncovered ones. | `services/rag_service.py`, `constants/rag_graph_constants.py` | RAG filters chunks by `RAG_SCORE_THRESHOLD` (`rag_graph_constants.py:50`), and the agent loop abstains on low *think* confidence (`agent_loop/loop.py:1875-1888`). Neither measures whether each named entity was found. | Clarifying questions instead of partial answers. | Entity extraction on every chat turn adds latency, overlaps the existing abstention, and is unmeasurable until the retrieval benchmarks in #13251 exist. | Adopt with conditions: lowest priority, gated on #13251. | Moderate |

### What We Already Do Better

- **Authentication on every route.** `nl_query` requires `Depends(get_current_user)` (`api/nl_database.py:138`).
  The reference work's internal API and ingest services trust a forwarded header or have no
  authentication at all.
- **A read-only check exists at all.** `_validate_readonly_sql` (`nl_database_service.py:71-95`, #723) runs
  before execution. No equivalent was found in the reference files read. It is weak, though (see D1, #20809).
- **Per-role model mapping** already exists, with a 6-tier per-role default (`autobot_shared/ssot_config.py:95`,
  #2553).
- **Human verification of knowledge:** facts carry `verification_status`, `verified_by` and `verified_at`
  (`knowledge/facts.py:312-335`). This is the knowledge-base analogue of term certification.
- **Abstention is a first-class outcome:** `ABSTAINED` is distinct from `FAILED` (`agent_loop/types.py:77`).
- **Local-first:** there is no hosted predictor that uploads user tables.

### Rejected by hidden metrics

- **A full ontology service with business-term certification.** It means five more services, an LLM
  compile pass per database and a standing human curation workload. AutoBot is not a warehouse-analytics
  platform, and the NL→SQL surface is one feature, so curation cost would dominate any accuracy gain.
- **Hosted prediction service:** it sends connected tables off the host.

### Discovered problems in AutoBot (found during the audit, independent of the reference work)

- **D1 (#20809): the NL→SQL read-only guard is a keyword filter only.**
  - `SELECT … INTO OUTFILE` passes the check, because `INTO` and `OUTFILE` are not in `_DANGEROUS_KEYWORDS`.
  - Side-effecting functions inside a `SELECT` pass.
  - The legitimate `REPLACE()` string function is rejected.
  - The connections are opened writable: SQLite uses plain `sqlite3.connect`, Postgres and MySQL
    open no read-only transaction (lines 151-230).
  - There is no statement timeout, and the Postgres path has no row cap.
- **D2: the route resolves any non-chat-scoped secret id for any authenticated user.** `_resolve_db_url`
  calls `get_secret(db_secret_id, chat_id=None)` (`api/nl_database.py:74`), and `get_secret`
  (`api/secrets.py:313-331`) checks only chat scope. This is another sighting of the open ownership defect
  #16982, not a new defect.

### Specific Code/Files Affected

- `autobot-backend/services/nl_database_service.py`:
  - G1: entity extraction, schema-slice retrieval and a coverage result in `query()`.
  - G2: a repair loop around `_generate_sql` and `_safe_execute_query`.
  - D1: an AST statement check, read-only connections, a timeout and a row cap.
- `autobot-backend/api/nl_database.py` / `api/schemas_agent.py`: add `coverage`, `uncovered_entities` and an
  `unconstructable` status to `NLQueryResponse` (G1, G2).
- `autobot-backend/services/rag_service.py`: a coverage field on the RAG result (G3).
- `constraints/shared.txt`: the SQL-parser pin (G2, D1).
