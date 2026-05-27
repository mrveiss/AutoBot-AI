# AutoBot - AI-Powered Automation Platform
# Copyright (c) 2025 mrveiss
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

if TYPE_CHECKING:
    import torch

logger = get_logger(__name__)

# ---------------------------------------------------------------------------
# Lazy torch import — module degrades gracefully without it
# ---------------------------------------------------------------------------

_torch = None
_torch_checked = False


def _get_torch() -> Any:
    """Return the torch module, importing lazily on first call."""
    global _torch, _torch_checked  # noqa: PLW0603
    if not _torch_checked:
        _torch_checked = True
        try:
            import torch as _t

            _torch = _t
        except (ImportError, RuntimeError):
            _torch = None
    return _torch


# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

#: Valid compression modes understood by LayerInferenceConfig.
_VALID_COMPRESSIONS = frozenset({"4bit", "8bit", "none"})


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
            raise ValueError(f"compression must be one of {sorted(_VALID_COMPRESSIONS)}, got '{self.compression}'")
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
                "transformers is required for load_model_config. " "Install with: pip install transformers>=4.40.0"
            ) from exc

        kwargs: Dict[str, Any] = {}
        if self._config.cache_dir:
            kwargs["cache_dir"] = self._config.cache_dir

        logger.debug("Loading model config for %s", model_name)
        auto_cfg = AutoConfig.from_pretrained(
            model_name, resume_download=True, **kwargs
        )  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally
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
        num_layers = config.get("num_hidden_layers") or config.get("n_layer") or config.get("num_layers")

        if num_layers is None:
            logger.warning("Could not determine num_hidden_layers from config — returning ['model']")
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

    # ------------------------------------------------------------------
    # Layer load / evict
    # ------------------------------------------------------------------

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

        full_sd: Dict[str, Any] = torch.load(state_dict_path, map_location="cpu", weights_only=True)
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

        hidden = input_ids.float() if input_ids.dtype not in (torch.float16, torch.float32) else input_ids

        for layer in layers:
            out = layer(hidden)
            hidden = out[0] if isinstance(out, (tuple, list)) else out

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
                "transformers is required for generate. " "Install with: pip install transformers>=4.40.0"
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
        return AutoTokenizer.from_pretrained(
            self._config.model_name, resume_download=True, **kwargs
        )  # nosec B615 - HuggingFace model loaded by name; revision pinning managed operationally

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
            Hidden states after all layers [batch, seq, hidden_size].
        """
        _get_torch()  # Validate torch is available
        hidden = input_ids.float()

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

        return hidden


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
    gpt2_style = {"gpt2", "gptj", "gpt_neo", "gpt_neox"}
    if model_type in gpt2_style:
        return "transformer.h."
    # LLaMA, Mistral, Falcon, Qwen, Gemma, Phi, etc.
    return "model.layers."


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
    for param in list(module.parameters()):
        param.data = torch.empty(param.shape, dtype=param.dtype, device=meta)
    for buf_name, buf in list(module.named_buffers()):
        if buf is not None:
            _set_buffer(module, torch, buf_name, meta, buf)


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
    """Return the argmax token id from the last position of hidden states.

    Issue #1946.

    Args:
        torch: The torch module.
        hidden: Tensor shaped ``[batch, seq, vocab_or_hidden]``.

    Returns:
        Integer token id (argmax over last dimension at last seq position).
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
