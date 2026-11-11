# Eval harness: live runs and before/after measurement

The trajectory eval (`autobot-backend/eval/`) has three candidates:

| Candidate | What it answers with | Can it go red? |
|---|---|---|
| baseline | each golden's own expectation | no (a file against itself) |
| recorded replay | recorded runs in `eval/recorded/` | yes |
| live (`--live`) | the real chat graph, headless, against a local model | yes, per model |

CI runs the first two with fake models only. The live run needs the stack and a model, so it is run on the host
by a person, and its report is attached to the issue or PR it supports. It is not committed.

## What a live run does

Each golden prompt goes through `ChatWorkflowManager.process_message` on a unique session
(`eval-<golden>-<uuid>`), and the final graph state is read back. The model is pinned through chat's own
per-session selector (`context["model"]` becomes `session.metadata["model_override"]`), so the run measures the
path users hit and builds no URL of its own. Checkpoints for the session are deleted afterwards.

Safety, for every run:

- a throwaway workspace per run, removed afterwards (`AUTOBOT_EVAL_WORKSPACE_ROOT` sets its parent);
- the bounded `research_agent` profile, whose `forbidden_work` hard-blocks shell and infrastructure tools;
- every approval category gated, so any other mutating tool halts at an approval nobody grants (status
  `awaiting_approval`, which fails the golden);
- a read-only first corpus, enforced: a tool outside a golden's `expected_tools` plus `allowed_tools` (empty by
  default) fails the run with a `forbidden_tool` detail. `eval/tests/test_live_safety.py` pins what the profile
  still allows;
- no residue: the graph checkpoints and the chat-history session of the run's own `eval-*` id are deleted, and a
  paused approval is resumed as denied (`denied: eval run`), so nothing stays in the operator queue;
- a turn whose graph never ran (chat fell back to its legacy flow) is `not_run`, not a clean pass.

Chat has no per-session working directory yet, so file tools cannot be sandboxed (#21249).

## Local-only guard

The run is refused (exit 2) before any prompt is sent unless the provider chat itself resolves (not the typed
`--provider`, which must match) is local, every model's endpoint is loopback or private, and no
`AUTOBOT_FALLBACK_CHAIN_*` can fail over to a hosted provider. `AUTOBOT_EVAL_ALLOW_REMOTE_PROVIDER=true` overrides that; the report then says
`local_only: false`. The report records an endpoint class (`loopback`, `private`, `public`), never a host.

## Failure categories

Each is decided by a detector the chat workflow already owns (`eval/live_classify.py`):

| Category | Signal |
|---|---|
| `malformed_tool_call` | tool-call markers present, the handler's own extractor parses fewer calls than announced |
| `unknown_tool` | `metadata.message_type == "unknown_tool"` from `tool_dispatch_guards.unknown_tool_error` |
| `loop_stall` | `tool_loop_count >= _LOOP_ABORT_THRESHOLD`, continuation cap reached while continuing, or a timeout |
| `false_done` | a final answer while the golden's `success_criteria` fail; with no criteria, a labelled heuristic |
| `unsupported_claim` | a substantive answer on a `knowledge_qa`/`troubleshooting` golden with no knowledge used and no citation, or the optional judge |

A golden passes only when status is as expected, the tool sequence matches (`tool_match`), every success
criterion holds and no category fired. A turn the harness could not run is `not_run` and is never a pass. A grounded golden on an empty or unreachable
knowledge base is `not_run` too (an environment cause; the pins record `kb_status`).

## Fixture v2

`fixture_version: "2"` adds `tool_match` (`exact` or `subsequence`) and `success_criteria` (the
`orchestration.success_criteria` shape; `custom` is not allowed in a fixture). v1 fixtures still load.

## Run it

```
cd autobot-backend
python -m eval.run --live --model <model> --repeat 3 --label before --json before.json
python -m eval.run --live --model <model> --repeat 3 --label after  --json after.json
python -m eval.compare before.json after.json
```

`--model` repeats for several models; `--provider` and `--judge-model` are optional. Exit codes: `0` examined,
`1` a golden failed (with `--fail-on-regression`), `2` not examined (refused, or nothing could run).

## Before/after procedure for a harness change

1. On the base commit, run the command above with `--label before`.
2. On the change, run it again with the same model(s), `--repeat`, and environment.
3. `python -m eval.compare` refuses (exit 2) unless the model set, step budget, loop threshold, timeout, corpus size,
   repeats, judge model, KB status and each model's provider, endpoint class and local-only flag match.
4. Attach the comparison to the PR. A difference smaller than the spread across repeats is not a result.

Tokens are reported only when the provider reports them; otherwise `null`, never an estimate.
