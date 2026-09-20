---
type: security
scope: ai-ml
issue: 13034
pr: 0000
---
Every `from_pretrained` call that resolved a bare model name against HuggingFace's mutable default branch is now pinned to an exact, integrity-verified revision, closing 15 of 18 `# nosec B615` suppressions that asserted "revision pinning managed operationally" with nothing actually implementing it. New `autobot_shared.pinned_model_registry` (`get_pinned_revision`/`verify_cached_model`) covers CLIP, Wav2Vec2, BLIP-2, Whisper and CodeBERT across `ai_hardware_accelerator.py`, `code_embedding_generator.py`, and the vision/voice multimodal processors — verified against the live HuggingFace API, not guessed. Fails closed on a digest mismatch or an unverifiable download. The remaining 3 suppressions (`llm_shared/optimization/layer_inference.py`, `model_inspector.py`) load arbitrary, caller-supplied model names at runtime and need a different mechanism (documented as remaining scope in `docs/developer/MODEL_REVISION_PINNING.md`).
