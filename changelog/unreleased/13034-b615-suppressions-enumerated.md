---
type: security
scope: ai-ml
issue: 13034
pr: 0000
---
The three remaining `# nosec B615` suppressions — the caller-supplied model loads in `llm_shared/optimization/layer_inference.py` and `model_inspector.py` — now consult the pinned-model registry through `pinned_revision_kwargs()`, so a model that *is* registered gets its exact revision even on a dynamic path, and the false "revision pinning managed operationally" comment each carried is replaced by a statement of what actually holds. A new guard enumerates every live suppression in the tree with its reason and asserts that a registry-backed one really calls the resolver; its population is built from `tokenize` COMMENT tokens, so prose naming the marker — this entry, the docs, the registry docstring — is not mistaken for a suppression and cannot silence it either. Unregistered, caller-supplied repo ids still resolve against a mutable default branch; that remainder is stated in `docs/developer/MODEL_REVISION_PINNING.md` rather than hidden by dropping the suppression.
