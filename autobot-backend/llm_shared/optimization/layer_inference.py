# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""
Layer-by-layer inference engine for batch and offline processing.

During batch/offline inference the entire model need not reside in VRAM
simultaneously.  This module loads transformer layers one at a time, runs each
layer's forward pass, then evicts the weights to the meta device before
loading the next.  Memory requirements are therefore bounded by the largest
single layer rather than the full model.

Key integration points:
- KVCacheManager / LayerKVCache from kv_cache.py  — per-layer KV cache
- HfQuantizerWrapper from hf_quantizer.py         — GPTQ/AWQ/BnB weight loading

Issue #1946: Layer-by-layer inference mode for batch/offline processing.
"""

import time
from dataclasses import dataclass, field
from typing import TYPE_CHECKING, Any, Dict, List

from autobot_shared.logging_manager import get_logger

from ..torch_loader import lazy_torch

if TYPE_CHECKING:
    import torch

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lazy torch import — module degrades gracefully without it.
# Issue #12714: unified onto the shared thread-safe llm_shared.torch_loader.
# ---------------------------------------------------------------------------


def _get_torch() -> Any:
    """Return the torch module, importing lazily on first call. None if unavailable."""
    return lazy_torch(required=False)


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Valid compression modes understood by LayerInferenceConfig.
_VALID_COMPRESSIONS = frozenset({"4bit", "8bit", "none"})

#: Architectures that nest transformer blocks under ``transformer.`` and name
#: their token embedding ``wte``, rather than the LLaMA-style ``model.`` layout.
#: Shared by the prefix, embedding and head resolvers so they cannot disagree
#: about which family a model belongs to (#13032).
_GPT2_STYLE = frozenset({"gpt2", "gptj", "gpt_neo", "gpt_neox"})


@dataclass
class LayerInferenceConfig:
    """Configuration for the layer-by-layer inference engine.

    Issue #1946.

    Attributes:
        model_name: HuggingFace model identifier or local path.
        compression: Weight compression mode — ``"4bit"``, ``"8bit"``, or ``"none"``.
        max_seq_len: Maximum sequence length the engine must support.
        batch_size: Number of sequences processed in parallel.
        device: Torch device string, e.g. ``"cuda"`` or ``"cpu"``.
        cache_dir: Optional directory for cached model weights.
    """

    model_name: str
    compression: str = "none"
    max_seq_len: int = 2048
    batch_size: int = 1
    device: str = "cpu"
    cache_dir: str | None = None

    def __post_init__(self) -> None:
        """Validate all configuration fields."""
        if not self.model_name:
            raise ValueError("model_name must not be empty")
        if self.compression not in _VALID_COMPRESSIONS:
            raise ValueError(
                f"compression must be one of {sorted(_VALID_COMPRESSIONS)}, got '{self.compression}'"
            )
        if self.max_seq_len < 1:
            raise ValueError(f"max_seq_len must be >= 1, got {self.max_seq_len}")
        if self.batch_size < 1:
            raise ValueError(f"batch_size must be >= 1, got {self.batch_size}")


# ---------------------------------------------------------------------------
# Stats
# ---------------------------------------------------------------------------


@dataclass
class LayerInferenceStats:
    """Timing and memory statistics for a single generate() call.

    Issue #1946.

    Attributes:
        total_time: Wall-clock seconds for the entire generate() call.
        per_layer_times: Mapping of layer name to seconds spent in that layer.
        peak_memory: Peak host or device memory during generation (bytes).
            Set to 0 when torch.cuda is unavailable or device is CPU.
        tokens_generated: Number of tokens produced.
    """

    total_time: float = 0.0
    per_layer_times: Dict[str, float] = field(default_factory=dict)
    peak_memory: int = 0
    tokens_generated: int = 0


# ---------------------------------------------------------------------------
# LayerInferenceEngine
# ---------------------------------------------------------------------------


class LayerInferenceEngine:
    """Layer-by-layer inference engine for batch and offline processing.

    Loads each transformer layer's weights individually, runs the layer's
    contribution to the forward pass, then evicts the weights to the meta
    device.  This keeps peak VRAM proportional to the heaviest single layer
    rather than the whole model.

    Integration:
        - Use KVCacheManager from kv_cache.py to create the KV cache that is
          passed into forward_pass().
        - Use HfQuantizerWrapper from hf_quantizer.py to obtain ``from_pretrained``
          kwargs before calling load_layer() for quantized checkpoints.

    Issue #1946.

    Args:
        config: Engine configuration controlling model, compression, and device.
    """

    def __init__(self, config: LayerInferenceConfig) -> None:
        self._config = config
        # #13031: one memory-mapped handle per checkpoint, reused across every
        # load_layer call. Without it the generate() loop re-deserialised the
        # whole file once per layer per token — 2,048 times for a 32-layer model
        # producing 64 tokens.
        self._mapped_checkpoints: Dict[str, Any] = {}
        logger.info(
            "LayerInferenceEngine initialised: model=%s compression=%s device=%s max_seq=%d",
            config.model_name,
            config.compression,
            config.device,
            config.max_seq_len,
        )

    @property
    def config(self) -> LayerInferenceConfig:
        """Engine configuration."""
        return self._config

    # ------------------------------------------------------------------
    # Model introspection
    # ------------------------------------------------------------------

    def load_model_config(self, model_name: str) -> Dict[str, Any]:
        """Load and return the model's configuration dictionary.

        Calls ``AutoConfig.from_pretrained`` from the transformers library and
        returns its ``to_dict()`` representation.  Does NOT load any weights.

        Issue #1946.

        Args:
            model_name: HuggingFace model identifier or local path.

        Returns:
            Model configuration as a plain dictionary.

        Raises:
            ImportError: If transformers is not installed.
            OSError: If the model config cannot be fetched.
        """
        try:
            from transformers import AutoConfig  # noqa: PLC0415
        except ImportError as exc:
            raise ImportError(
                "transformers is required for load_model_config. "
                "Install with: pip install transformers>=4.40.0"
            ) from exc

        kwargs: Dict[str, Any] = {}
        if self._config.cache_dir:
            kwargs["cache_dir"] = self._config.cache_dir

        logger.debug("Loading model config for %s", model_name)
        # HuggingFace model loaded by name; revision pinning managed operationally.
        auto_cfg = AutoConfig.from_pretrained(
            model_name, resume_download=True, **kwargs
        )  # nosec B615
        cfg_dict: Dict[str, Any] = auto_cfg.to_dict()
        logger.info(
            "Loaded model config for %s: arch=%s",
            model_name,
            cfg_dict.get("model_type"),
        )
        return cfg_dict

    def get_layer_names(self, config: Dict[str, Any]) -> List[str]:
        """Return an ordered list of transformer layer names from a model config.

        Generates names of the form ``"model.layers.<i>"`` for architectures
        that expose ``num_hidden_layers`` (LLaMA, Mistral, Falcon, GPT-NeoX,
        etc.).  Falls back to ``"transformer.h.<i>"`` for GPT-2/GPT-J style
        configs.  Returns a single-element list with ``"model"`` for unknown
        architectures so callers always receive a non-empty list.

        Issue #1946.

        Args:
            config: Model configuration dictionary (from load_model_config or
                AutoConfig.to_dict()).

        Returns:
            Ordered list of transformer layer name strings.
        """
        num_layers = (
            config.get("num_hidden_layers") or config.get("n_layer") or config.get("num_layers")
        )

        if num_layers is None:
            logger.warning(
                "Could not determine num_hidden_layers from config — returning ['model']"
            )
            return ["model"]

        model_type: str = str(config.get("model_type", "")).lower()
        prefix = _layer_prefix_for_arch(model_type)
        names = [f"{prefix}{i}" for i in range(int(num_layers))]
        logger.debug(
            "get_layer_names: model_type=%s num_layers=%d prefix=%s",
            model_type,
            num_layers,
            prefix,
        )
        return names

    def get_embedding_name(self, config: Dict[str, Any]) -> str:
        """Return the token-embedding module name for this model config (#13032).

        Deliberately separate from :meth:`get_layer_names` rather than prepended
        to it. That method's contract is "the ordered transformer blocks", and
        callers index into it and evict per entry; folding non-block modules in
        would silently change what those callers iterate over.
        """
        return _embedding_name_for_arch(str(config.get("model_type", "")).lower())

    def get_head_name(self, config: Dict[str, Any]) -> str:
        """Return the LM-head module name for this model config (#13032).

        The head projects hidden states to vocabulary logits. Without it the
        engine had nothing to argmax over except hidden units.
        """
        return _head_name_for_arch(str(config.get("model_type", "")).lower())

    # ------------------------------------------------------------------
    # Layer load / evict
    # ------------------------------------------------------------------

    def _checkpoint(self, torch: Any, state_dict_path: str) -> Dict[str, Any]:
        """Return the checkpoint's tensors, memory-mapped and cached per path.

        ``mmap=True`` makes ``torch.load`` map the file rather than deserialise
        it: the returned dict holds tensor views backed by the file on disk, and
        only the bytes a caller actually reads are paged in. Selecting one
        layer's keys therefore touches one layer's weights, which is what makes
        peak memory bounded by the largest single layer as this module's
        docstring promises — the previous full ``torch.load`` materialised every
        parameter and then discarded all but one layer's.

        Caching the handle is what removes the per-token cost. It is cheap to
        hold precisely because it is a mapping and not a copy: the pages are
        clean and the kernel can reclaim them under pressure.

        The fallback path is deliberately **not** cached. Legacy (non-zipfile)
        checkpoints cannot be mapped, and there the dict is a real in-RAM copy —
        keeping it would trade this issue's problem for the one the module was
        written to avoid.
        """
        cached = self._mapped_checkpoints.get(state_dict_path)
        if cached is not None:
            return cached
        try:
            mapped = torch.load(state_dict_path, map_location="cpu", weights_only=True, mmap=True)
        except (RuntimeError, ValueError, TypeError) as exc:
            logger.warning(
                "Checkpoint %s cannot be memory-mapped (%s) — falling back to a full load. "
                "Peak memory is the whole model and the load repeats per layer (#13031).",
                state_dict_path,
                exc,
            )
            return torch.load(state_dict_path, map_location="cpu", weights_only=True)
        self._mapped_checkpoints[state_dict_path] = mapped
        return mapped

    def release_checkpoints(self) -> None:
        """Drop cached memory-mapped checkpoints so their mappings can close.

        Call when a model is swapped out.

        Note that on a **CPU** device this does not necessarily unmap anything
        immediately: ``_build_layer_module`` ends in ``module.to(device)``, which
        is a no-op when the tensors are already on CPU, so those parameters
        still alias the mapped file. Refcounting keeps the mapping alive for as
        long as any live layer references it, so dropping the cache here is safe
        either way — it releases the mapping once the last layer holding it is
        evicted. On CUDA the ``.to()`` genuinely copies and the mapping is
        released as soon as this returns.
        """
        count = len(self._mapped_checkpoints)
        self._mapped_checkpoints.clear()
        if count:
            logger.debug("Released %d memory-mapped checkpoint(s)", count)

    def load_layer(self, layer_name: str, state_dict_path: str) -> Any:
        """Load a single transformer layer's weights onto the configured device.

        Reads only the keys that belong to ``layer_name`` from the state dict
        file at ``state_dict_path``, constructs a minimal ``nn.Module``-like
        container, and moves it to ``self._config.device``.

        Issue #1946.

        Args:
            layer_name: Fully-qualified layer name (e.g. ``"model.layers.3"``).
            state_dict_path: Path to a ``.pt`` or ``.safetensors`` checkpoint.

        Returns:
            An ``nn.Module`` with the layer's parameters loaded on device.

        Raises:
            ImportError: If torch is not installed.
            FileNotFoundError: If state_dict_path does not exist.
            KeyError: If no keys matching layer_name exist in the checkpoint.
        """
        torch = _get_torch()
        if torch is None:
            raise ImportError("PyTorch is required for load_layer.")

        logger.debug("Loading layer '%s' from %s", layer_name, state_dict_path)
        t0 = time.monotonic()

        full_sd = self._checkpoint(torch, state_dict_path)
        prefix = layer_name + "."
        layer_sd = {k[len(prefix) :]: v for k, v in full_sd.items() if k.startswith(prefix)}

        if not layer_sd:
            raise KeyError(
                f"No keys matching prefix '{prefix}' found in {state_dict_path}. "
                f"Available top-level keys: {sorted(set(k.split('.')[0] for k in full_sd))}"
            )

        module = _build_layer_module(torch, layer_sd, self._config.device)
        elapsed = time.monotonic() - t0
        logger.info(
            "Loaded layer '%s' on %s: %d params, %.3fs",
            layer_name,
            self._config.device,
            len(layer_sd),
            elapsed,
        )
        return module

    def evict_layer(self, layer: Any) -> None:
        """Move a loaded layer's parameters to the meta device, freeing memory.

        After eviction the layer object is no longer usable for computation.
        Call this after the layer's contribution to the forward pass is complete.

        Issue #1946.

        Args:
            layer: An ``nn.Module`` previously returned by load_layer().

        Raises:
            ImportError: If torch is not installed.
        """
        torch = _get_torch()
        if torch is None:
            raise ImportError("PyTorch is required for evict_layer.")

        _move_to_meta(torch, layer)
        logger.debug("Evicted layer to meta device")

    # ------------------------------------------------------------------
    # Forward pass
    # ------------------------------------------------------------------

    def forward_pass(
        self,
        input_ids: "torch.Tensor",
        layers: List[Any],
        kv_cache: Any | None = None,
        embedding: Any | None = None,
        head: Any | None = None,
    ) -> "torch.Tensor":
        """Run a sequential forward pass through an ordered list of layers.

        Each element of ``layers`` must be callable as ``layer(hidden_states)``
        and return a tensor or tuple whose first element is the updated hidden
        states.  Layers are called in list order.

        The ``kv_cache`` argument is accepted for API consistency and future
        integration with LayerKVCache but is not inspected in this
        implementation — callers that need KV cache semantics should embed
        cache reads/writes inside their layer callables.

        Issue #1946.

        Args:
            input_ids: Token IDs tensor shaped ``[batch, seq_len]``.
            layers: Ordered list of callable layer modules.
            kv_cache: Optional KV cache (LayerKVCache or compatible object).

        Returns:
            Output logits tensor shaped ``[batch, seq_len, vocab_size]`` if the
            last layer is an lm_head, or hidden states shaped
            ``[batch, seq_len, hidden_size]`` otherwise.

        Raises:
            ImportError: If torch is not installed.
            ValueError: If layers list is empty.
        """
        torch = _get_torch()
        if torch is None:
            raise ImportError("PyTorch is required for forward_pass.")
        if not layers:
            raise ValueError("layers must not be empty")

        # #13032: embed when an embedding module is supplied. Without one, an
        # integer tensor is still cast to float as before — that path cannot
        # produce meaningful activations (token ids are vocabulary indices, not
        # a hidden-state vector), so it warns rather than failing silently.
        # Callers passing float hidden states directly are unaffected.
        if embedding is not None:
            hidden = _apply_embedding(embedding, input_ids)
        elif input_ids.dtype not in (torch.float16, torch.float32):
            logger.warning(
                "forward_pass received integer token ids with no embedding module — "
                "casting to float. Layer 0 will see vocabulary indices as activations "
                "and the result cannot be meaningful (#13032)."
            )
            hidden = input_ids.float()
        else:
            hidden = input_ids

        for layer in layers:
            out = layer(hidden)
            hidden = out[0] if isinstance(out, (tuple, list)) else out

        if head is not None:
            hidden = _apply_head(head, hidden)
        return hidden

    # ------------------------------------------------------------------
    # Generation
    # ------------------------------------------------------------------

    def generate(
        self,
        prompt: str,
        max_new_tokens: int = 64,
    ) -> str:
        """Generate text from a prompt using layer-by-layer inference.

        Tokenises the prompt, then for each new token:
        1. Loads each layer sequentially from the checkpoint.
        2. Runs the forward pass through that layer.
        3. Evicts the layer immediately after use.
        4. Samples the next token from the final logits.

        This method requires a HuggingFace-compatible tokeniser and a model
        whose config was loaded via load_model_config().  The checkpoint path
        is derived from ``config.model_name`` (local) or the HF cache.

        Issue #1946.

        Args:
            prompt: Input text to continue.
            max_new_tokens: Maximum number of tokens to generate.

        Returns:
            Generated text string (not including the prompt).

        Raises:
            ImportError: If transformers or torch are not installed.
            ValueError: If max_new_tokens < 1.
        """
        if max_new_tokens < 1:
            raise ValueError(f"max_new_tokens must be >= 1, got {max_new_tokens}")

        torch = _get_torch()
        if torch is None:
            raise ImportError("PyTorch is required for generate.")

        try:
            from transformers import AutoTokenizer  # noqa: PLC0415
        except (ImportError, RuntimeError) as exc:
            raise ImportError(
                "transformers is required for generate. "
                "Install with: pip install transformers>=4.40.0"
            ) from exc

        t_start = time.monotonic()
        stats = LayerInferenceStats()

        logger.info("generate: loading tokeniser for %s", self._config.model_name)
        tokeniser = self._load_tokeniser(AutoTokenizer)
        model_cfg = self.load_model_config(self._config.model_name)
        layer_names = self.get_layer_names(model_cfg)
        state_dict_path = self._resolve_checkpoint_path()

        input_ids = tokeniser(prompt, return_tensors="pt").input_ids.to(self._config.device)
        generated_ids: List[int] = []

        logger.info(
            "generate: starting loop max_new_tokens=%d num_layers=%d",
            max_new_tokens,
            len(layer_names),
        )
        _reset_peak_memory(torch, self._config.device)

        for _step in range(max_new_tokens):
            hidden = self._run_layer_loop(input_ids, layer_names, state_dict_path, stats)
            next_token_id = _greedy_sample(torch, hidden)
            generated_ids.append(next_token_id)
            input_ids = torch.cat(
                [
                    input_ids,
                    torch.tensor([[next_token_id]], device=self._config.device),
                ],
                dim=1,
            )
            if _is_eos(tokeniser, next_token_id):
                logger.debug("generate: EOS token reached at step %d", _step)
                break

        stats.total_time = time.monotonic() - t_start
        stats.tokens_generated = len(generated_ids)
        stats.peak_memory = _get_peak_memory(torch, self._config.device)
        logger.info(
            "generate: done tokens=%d total_time=%.3fs peak_memory_mb=%.1f",
            stats.tokens_generated,
            stats.total_time,
            stats.peak_memory / (1024 * 1024),
        )
        return tokeniser.decode(generated_ids, skip_special_tokens=True)

    # ------------------------------------------------------------------
    # Private helpers
    # ------------------------------------------------------------------

    def _load_tokeniser(self, AutoTokenizer: Any) -> Any:
        """Instantiate the tokeniser for the configured model.

        Issue #1946: Extracted to keep generate() within the line budget.
        """
        kwargs: Dict[str, Any] = {"use_fast": True}
        if self._config.cache_dir:
            kwargs["cache_dir"] = self._config.cache_dir
        # HuggingFace model loaded by name; revision pinning managed operationally.
        return AutoTokenizer.from_pretrained(
            self._config.model_name, resume_download=True, **kwargs
        )  # nosec B615

    def _resolve_checkpoint_path(self) -> str:
        """Return the checkpoint path for the configured model.

        For local paths the model_name is returned directly.  For HuggingFace
        Hub models the caller is expected to have downloaded the weights first;
        this method returns model_name and lets torch.load handle resolution.

        Issue #1946.
        """
        return self._config.model_name

    def _run_layer_loop(
        self,
        input_ids: "torch.Tensor",
        layer_names: List[str],
        state_dict_path: str,
        stats: LayerInferenceStats,
    ) -> "torch.Tensor":
        """Load each layer, run the forward pass, and evict.

        Issue #1946: Extracted from generate() to respect the 65-line limit.

        Args:
            input_ids: Current input token IDs [batch, seq].
            layer_names: Ordered transformer layer names.
            state_dict_path: Path to checkpoint weights.
            stats: Stats object to update with per-layer timing.

        Returns:
            Vocabulary logits [batch, seq, vocab_size] when the checkpoint
            carries an embedding, so the caller can argmax over a real vocab
            axis. #13032: this used to return raw post-block hidden states, and
            before that it started from ``input_ids.float()`` — token ids fed in
            as activations.
        """
        _get_torch()  # Validate torch is available
        arch = self._arch_from_layer_names(layer_names)
        hidden, embed_weight = self._embed_inputs(input_ids, state_dict_path, arch)

        for name in layer_names:
            t0 = time.monotonic()
            try:
                layer = self.load_layer(name, state_dict_path)
                out = layer(hidden)
                hidden = out[0] if isinstance(out, (tuple, list)) else out
                self.evict_layer(layer)
            except (KeyError, FileNotFoundError) as exc:
                logger.warning("Skipping layer '%s': %s", name, exc)
                continue
            elapsed = time.monotonic() - t0
            stats.per_layer_times[name] = stats.per_layer_times.get(name, 0.0) + elapsed
            logger.debug("Layer '%s' forward: %.4fs", name, elapsed)

        return self._project_logits(hidden, state_dict_path, embed_weight, arch)

    @staticmethod
    def _arch_from_layer_names(layer_names: List[str]) -> str:
        """Infer the architecture family from the block names already resolved.

        Derived rather than stored: :meth:`get_layer_names` is the only place the
        model config is seen, and caching its answer on the instance would make
        a getter side-effecting and would go stale if a second model were used.
        The block prefix already encodes the family — that is what
        :func:`_layer_prefix_for_arch` produced — so reading it back is exact.
        """
        return "gpt2" if any(n.startswith("transformer.h.") for n in layer_names) else ""

    def _embed_inputs(
        self, input_ids: "torch.Tensor", state_dict_path: str, arch: str
    ) -> "tuple[torch.Tensor, Any]":
        """Embed token ids, returning hidden states and the embedding weight.

        The weight comes back so :meth:`_project_logits` can tie against it when
        the checkpoint has no separate ``lm_head`` (#13032).

        If the checkpoint carries no embedding at all the previous behaviour is
        kept — ids cast to float — rather than raising, because a partial or
        block-only checkpoint is a legitimate thing to feed this engine for a
        timing run. It is logged at warning level, since the output cannot be
        meaningful.
        """
        name = _embedding_name_for_arch(arch)
        try:
            module = self.load_layer(name, state_dict_path)
        except (KeyError, FileNotFoundError) as exc:
            logger.warning(
                "No embedding '%s' in %s (%s) — falling back to raw ids as activations. "
                "Output cannot be meaningful (#13032).",
                name,
                state_dict_path,
                exc,
            )
            return input_ids.float(), None
        weight = getattr(module, "weight", None)
        return _apply_embedding(module, input_ids), weight

    def _project_logits(
        self, hidden: "torch.Tensor", state_dict_path: str, embed_weight: Any, arch: str
    ) -> "torch.Tensor":
        """Project post-block hidden states to vocabulary logits (#13032).

        Falls back to the tied embedding weight when the checkpoint ships no
        ``lm_head`` — the common case for GPT-2 and many LLaMA-family models.
        With neither, the hidden states are returned unchanged so existing
        block-only callers keep working; sampling from that is meaningless, so
        it is logged.
        """
        name = _head_name_for_arch(arch)
        module = None
        try:
            module = self.load_layer(name, state_dict_path)
        except (KeyError, FileNotFoundError):
            if embed_weight is None:
                logger.warning(
                    "No '%s' and no embedding to tie against — returning hidden states, "
                    "not logits. Sampling from these is meaningless (#13032).",
                    name,
                )
                return hidden
            logger.debug("No '%s' in checkpoint — tying head to the embedding weight", name)
        return _apply_head(module, hidden, fallback_weight=embed_weight)


# ---------------------------------------------------------------------------
# Module-level helpers
# ---------------------------------------------------------------------------


def _layer_prefix_for_arch(model_type: str) -> str:
    """Return the layer name prefix for a given model architecture string.

    Issue #1946.

    Args:
        model_type: Lower-cased model_type from the model config.

    Returns:
        Dot-separated prefix including trailing dot, e.g. ``"model.layers."``.
    """
    if model_type in _GPT2_STYLE:
        return "transformer.h."
    # LLaMA, Mistral, Falcon, Qwen, Gemma, Phi, etc.
    return "model.layers."


def _embedding_name_for_arch(model_type: str) -> str:
    """Return the token-embedding module name for an architecture (#13032).

    The embedding is what turns token ids into hidden states. Without it the
    engine fed raw vocabulary indices into layer 0 as floats, so every
    downstream activation was meaningless.
    """
    if model_type in _GPT2_STYLE:
        return "transformer.wte"
    return "model.embed_tokens"


def _head_name_for_arch(model_type: str) -> str:
    """Return the LM-head module name for an architecture (#13032).

    ``lm_head`` is the same name in both families. It is kept as a function so
    the caller reads symmetrically with the embedding and prefix helpers, and so
    an architecture needing something else has one place to change.
    """
    return "lm_head"


def _apply_embedding(module: Any, input_ids: "torch.Tensor") -> "torch.Tensor":
    """Turn token ids into hidden states using a loaded embedding module (#13032).

    ``_build_layer_module`` returns a bare ``nn.Module`` carrying the checkpoint's
    parameters — not an ``nn.Embedding`` — so it is not callable as one. The
    lookup is therefore done directly against the weight matrix, which is what
    ``nn.Embedding.forward`` does anyway.

    Args:
        module: Loaded embedding module exposing ``weight`` [vocab, hidden].
        input_ids: Token ids [batch, seq].

    Returns:
        Hidden states [batch, seq, hidden].
    """
    weight = getattr(module, "weight", None)
    if weight is None:
        raise KeyError("embedding module has no 'weight' parameter to index")
    return weight[input_ids]


def _apply_head(module: Any, hidden: "torch.Tensor", fallback_weight: Any = None) -> "torch.Tensor":
    """Project hidden states to vocabulary logits (#13032).

    ``fallback_weight`` supports **tied embeddings**, which are the norm rather
    than the exception — GPT-2 and many LLaMA-family checkpoints ship no
    ``lm_head.weight`` at all because the head reuses the embedding matrix. When
    the head is absent the caller passes the embedding weight and the same
    matrix is applied transposed, which is exactly what a tied head computes.

    Args:
        module: Loaded head module with ``weight`` [vocab, hidden], or None.
        hidden: Hidden states [batch, seq, hidden].
        fallback_weight: Embedding weight to use when no head module exists.

    Returns:
        Logits [batch, seq, vocab].
    """
    weight = getattr(module, "weight", None) if module is not None else None
    if weight is None:
        weight = fallback_weight
    if weight is None:
        raise KeyError("no lm_head weight and no embedding weight to tie against")
    logits = hidden @ weight.t()
    bias = getattr(module, "bias", None) if module is not None else None
    return logits + bias if bias is not None else logits


def _build_layer_module(torch: Any, layer_sd: Dict[str, Any], device: str) -> Any:
    """Wrap a flat state dict in an nn.Module and move it to device.

    Issue #1946.

    Args:
        torch: The torch module.
        layer_sd: State dict with keys relative to the layer root.
        device: Target device string.

    Returns:
        An nn.Module whose parameters match layer_sd, located on device.
    """
    module = torch.nn.Module()
    for k, v in layer_sd.items():
        _set_nested_param(module, torch, k, v)
    return module.to(device)


def _set_nested_param(module: Any, torch: Any, key: str, tensor: Any) -> None:
    """Register a (possibly nested) parameter inside module under key.

    Issue #1946: Handles keys like ``"self_attn.q_proj.weight"`` by creating
    nested submodules as needed.
    """
    parts = key.split(".")
    container = module
    for part in parts[:-1]:
        if not hasattr(container, part):
            setattr(container, part, torch.nn.Module())
        container = getattr(container, part)
    leaf = parts[-1]
    if isinstance(tensor, torch.Tensor):
        container.register_parameter(leaf, torch.nn.Parameter(tensor, requires_grad=False))
    else:
        container.register_buffer(leaf, tensor)


def _move_to_meta(torch: Any, module: Any) -> None:
    """Recursively move all parameters and buffers of module to meta device.

    Issue #1946.
    """
    meta = torch.device("meta")
    # remove_duplicate=False so a parameter shared by two submodules is released at
    # every name it is registered under. The old in-place ``.data`` assignment
    # reached all aliases through the single deduplicated entry; re-registering
    # does not, and a missed alias would keep the real tensor — and its memory —
    # alive, defeating the eviction. The layer is documented as unusable after
    # eviction, so untying the shared storage here is safe.
    for param_name, param in list(module.named_parameters(remove_duplicate=False)):
        if param is not None:
            _set_parameter(module, torch, param_name, meta, param)
    for buf_name, buf in list(module.named_buffers()):
        if buf is not None:
            _set_buffer(module, torch, buf_name, meta, buf)


def _set_parameter(module: Any, torch: Any, name: str, device: Any, param: Any) -> None:
    """Replace a named parameter with a meta-device empty tensor of the same shape.

    Issue #13162: eviction previously did ``param.data = torch.empty(..., device=meta)``.
    PyTorch rejects that with ``RuntimeError: Attempted to call variable.set_data(tensor),
    but variable and tensor have incompatible tensor type`` because a meta tensor carries a
    different ``TensorImpl`` than a dense one, so ``evict_layer`` raised instead of freeing
    the layer. Re-registering the parameter — the same shape ``_set_buffer`` already uses
    for buffers — is the supported way to move one across device types.
    """
    parts = name.split(".")
    container = module
    for part in parts[:-1]:
        container = getattr(container, part)
    container.register_parameter(
        parts[-1],
        torch.nn.Parameter(
            torch.empty(param.shape, dtype=param.dtype, device=device),
            requires_grad=param.requires_grad,
        ),
    )


def _set_buffer(module: Any, torch: Any, name: str, device: Any, buf: Any) -> None:
    """Replace a named buffer with a meta-device empty tensor of the same shape.

    Issue #1946: Handles dotted names (e.g. ``"self_attn.q_proj.bias"``).
    """
    parts = name.split(".")
    container = module
    for part in parts[:-1]:
        container = getattr(container, part)
    leaf = parts[-1]
    container.register_buffer(leaf, torch.empty(buf.shape, dtype=buf.dtype, device=device))


def _greedy_sample(torch: Any, hidden: "torch.Tensor") -> int:
    """Return the argmax token id from the last position of the logits.

    Issue #1946.

    #13032 named this as a third defect — "sampling reads the wrong axis". It is
    really the *symptom* of the other two: ``argmax(dim=-1)`` over the last axis
    is correct whenever that axis is the vocabulary, and it was not, because
    nothing projected hidden states through an LM head. With the head applied in
    ``_run_layer_loop`` this function is right as written and is unchanged.

    It remains the caller's job to pass logits. When a checkpoint has neither a
    head nor a tied embedding to fall back on, ``_project_logits`` logs that it
    is returning hidden states, and an index from this function is a hidden-unit
    index rather than a token id.

    Args:
        torch: The torch module.
        hidden: Logits shaped ``[batch, seq, vocab]``.

    Returns:
        Integer token id (argmax over the vocabulary axis at the last position).
    """
    last_logits = hidden[:, -1, :]  # [batch, vocab]
    return int(last_logits.argmax(dim=-1)[0].item())


def _is_eos(tokeniser: Any, token_id: int) -> bool:
    """Return True when token_id matches the tokeniser's EOS token.

    Issue #1946.
    """
    eos_id = getattr(tokeniser, "eos_token_id", None)
    return eos_id is not None and token_id == eos_id


def _reset_peak_memory(torch: Any, device: str) -> None:
    """Reset CUDA peak memory stats if device is CUDA.

    Issue #1946.
    """
    try:
        if device.startswith("cuda") and hasattr(torch.cuda, "reset_peak_memory_stats"):
            torch.cuda.reset_peak_memory_stats()
    except Exception:  # noqa: BLE001
        pass


def _get_peak_memory(torch: Any, device: str) -> int:
    """Return peak CUDA memory in bytes, or 0 for CPU / unavailable.

    Issue #1946.
    """
    try:
        if device.startswith("cuda") and hasattr(torch.cuda, "max_memory_allocated"):
            return int(torch.cuda.max_memory_allocated())
    except Exception:  # noqa: BLE001
        pass
    return 0


__all__ = [
    "LayerInferenceConfig",
    "LayerInferenceEngine",
    "LayerInferenceStats",
]
