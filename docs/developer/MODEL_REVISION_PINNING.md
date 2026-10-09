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

The one stated exception is the dynamic `model_name` sites (`layer_inference`,
`model_inspector`), whose name arrives from a routing request. They call
`pinned_revision_kwargs(model_name)` instead, which returns
`{"revision": <pin>}` for a registered id and `{}` for any other name rather
than raising, so an unregistered name still loads from the mutable default
branch. That is the documented interim state, not a second rule; see
[Scope: this does not yet cover every `from_pretrained` call
site](#scope-this-does-not-yet-cover-every-from_pretrained-call-site).

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

Measured on `main` at `0a4cffce`: **4 bandit findings suppressed across 3
files** — 5 `# nosec B615` comment occurrences, one of which is the explanation
above the NPU worker's call rather than a suppression of its own. Not the 18
this document opened with, and not the 16 the issue text still cites either.
Every other occurrence of the string in the tree is prose: this file, the
changelog, the research notes, two module docstrings and the guard's own
fixtures. Counting those is the mistake `grep -rn "nosec B615"` makes, which is
why the guard that holds the line
(`repo_tests/nosec_b615_suppressions_are_registry_backed_13034_test.py`) builds
its population from `tokenize` COMMENT tokens instead of from file text.

| File | Live suppressions | Why no static pin fits |
|---|---|---|
| `llm_shared/optimization/layer_inference.py` | 2 (2 comments) | `model_name` arrives from a routing request; it may be a local path or a non-HuggingFace tag such as `llama3:8b`. |
| `llm_shared/optimization/model_inspector.py` | 1 (1 comment) | `inspect_model(model_name)` is called by the complexity router and hardware sizing with whatever model the caller routed to. |
| `autobot-npu-worker/.../app/model_manager.py` | 1 (2 comments) | `str(model_path)` is a **local directory** `ensure_model_downloaded()` already populated and verified against its pin (#17087). No Hub resolution happens, so `revision=` would be a no-op rather than a guarantee. The second comment is the explanation above the call, not a second suppression. |

### What the dynamic sites do instead

`pinned_revision_kwargs(model_ref)` returns `{"revision": <pin>}` when
`model_ref` is registered and `{}` when it is not. The two optimization modules
call it, so a registered model id is pinned **even on a dynamic path**, while an
unregistered one resolves exactly as before.

It is the deliberate soft counterpart to `get_pinned_revision`, which raises
for an unregistered id precisely so a *fixed* call site cannot omit a pin by
accident. The two must not be swapped: a fixed call site using
`pinned_revision_kwargs` would lose that protection, and
`model_revision_pinning_enforced_17804_test.py` is what keeps fixed sites on
the raising path.

**`{}` is not a pin, and the suppression stays because of it.** The three
dynamic sites keep `# nosec B615` for the unregistered remainder rather than
dropping it: bandit gives a non-literal `revision=` the benefit of the doubt
(`bandit/plugins/huggingface_unsafe_download.py` returns early for any
non-`ast.Constant` revision keyword), so passing one would silence the finding
whether or not anything was actually resolved. A quiet scan over a load that
still resolves against a mutable default branch is worse than a recorded
suppression — it reads as safe. Each suppression's reason is recorded in the
guard's `_SUPPRESSED` table and checked against the code.

### The remainder, unsolved

Pinning an arbitrary caller-supplied name needs its own design — for example
trust-on-first-use pinning (resolve once, persist, and verify the *same*
resolved revision on every later load of the same name) or requiring the caller
to supply a revision alongside the model name. Both add a persistence and bump
story this registry does not have. Tracked on #13034 as remaining scope rather
than solved here.

**#13034's AC1 as written — `grep -rn "nosec B615"` returning zero — is not
reachable and should not be the criterion.** Satisfying it literally would mean
deleting the sentences that explain the rule, including this one, while a
single comment discussing the marker would break it again. The enforceable
property is the one the guard asserts: the suppression set is enumerated,
reasoned, cannot grow unnoticed, and every entry claiming to be registry-backed
really calls the resolver.
