<!-- Copyright (c) 2025-2026 mrveiss -->
# Model revision pinning and integrity verification (#13034)

## The problem this closes

Every `from_pretrained(repo_id)` call without a `revision=` resolves against
the model's mutable default branch on HuggingFace — the same call can return
different weights on a different day. 18 `# nosec B615` suppressions across
the repo used to assert "revision pinning managed operationally" with no
registry, lockfile, or bump procedure actually implementing that — the
comment described an intention nothing enforced.

## The mechanism

`autobot_shared/pinned_model_registry.py` is the single source of truth: a
`repo_id → (exact commit SHA, expected weight-file sha256)` map. Every
weight-loading call site:

1. Looks up its pin: `revision = get_pinned_revision(repo_id)`.
2. Passes it to `from_pretrained(repo_id, revision=revision)`.
3. After loading, calls `verify_cached_model(repo_id)`, which locates the
   downloaded file in the local HuggingFace cache and fails closed
   (`ModelIntegrityError`) if its sha256 doesn't match the registry — or if
   none of the registered files were found in the cache at all. "Nothing to
   verify" is treated as a failure, not a silent pass.

A `repo_id` not in the registry raises `KeyError` from `get_pinned_revision`
— a new call site cannot silently load an unpinned model by omission.

## Bump procedure — who owns it, and how

**Owner:** whoever adds or bumps an entry records their name and date in the
entry's comment in `pinned_model_registry.py` (see the existing entries for
the format). A pin with no recorded owner rots and gets re-suppressed instead
of maintained — recording this is part of the fix, not optional.

**How to obtain a real pin (never guess a SHA or a digest):**

```bash
# 1. Exact commit SHA for the revision to pin:
curl -s "https://huggingface.co/api/models/<repo_id>" | python3 -c \
    'import json,sys; print(json.load(sys.stdin)["sha"])'

# 2. sha256 of each weight file at that revision, via the raw git-lfs
#    pointer (a few hundred bytes -- this does NOT download the real,
#    often multi-GB, file):
curl -s "https://huggingface.co/<repo_id>/raw/<sha>/<filename>" | \
    grep "^oid sha256:"
```

Repeat step 2 for every weight file the model ships in a format
`from_pretrained` might actually load (commonly both `pytorch_model.bin` and
`model.safetensors`, or sharded `model-0000N-of-0000M.safetensors` files) —
`verify_cached_model` checks whichever of the registered filenames the local
cache actually has, so more than one recorded digest per model is normal and
expected, not redundant.

Use the exact output of these commands as the new/updated
`PinnedModel(revision=..., weight_digests={...})` entry. Do not reconstruct,
approximate, or paraphrase a hash from memory or from a tool that summarizes
page content (a model-mediated paraphrase of a long hex string is a real
transcription-error risk for something this precision-critical) — always the
raw command output, verbatim.

## Scope: this does not yet cover every `from_pretrained` call site

Two of the original 18 suppressions remain, on purpose:
`llm_shared/optimization/layer_inference.py` and
`llm_shared/optimization/model_inspector.py` accept an arbitrary,
caller-supplied `model_name` at runtime (traced to `request.model_name` in
`llm_shared/optimization/integration.py`) — a fixed, static registry entry
doesn't fit an open-ended model set the same way it fits the five
call sites this issue's fix does cover (`ai_hardware_accelerator.py`,
`code_embedding_generator.py`, `multimodal_processor/processors/vision.py`,
`multimodal_processor/processors/voice.py`). Pinning that dynamic path needs
its own design — for example, trust-on-first-use pinning (resolve once,
persist, and verify the *same* resolved revision on every later load of the
same name) or requiring the caller to supply a revision alongside the model
name — tracked on #13034 as remaining scope rather than solved here.
