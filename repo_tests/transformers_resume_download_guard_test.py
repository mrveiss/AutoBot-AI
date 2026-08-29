# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15054 -- ``resume_download`` was removed from ``from_pretrained`` in the pinned
``transformers==5.15.1`` (``requirements-ci/ai-ml.txt:10``). Every call site in the
tree passed it anyway.

What actually happens at 5.15.1, read from the installed package's own source
rather than assumed from memory: ``resume_download`` is popped nowhere --
``modeling_utils.py``'s ``from_pretrained`` forwards unrecognized kwargs through
``config_class.from_pretrained(..., return_unused_kwargs=True, **kwargs)`` and the
unused remainder lands in ``model_kwargs``, which then reaches
``cls(config, *model_args, **model_kwargs)``. A direct model/processor class
(``CLIPModel``, ``Wav2Vec2Model``, ``WhisperForConditionalGeneration``, ...) has no
``**kwargs`` catch-all on ``__init__``, so this is a live ``TypeError`` -- exactly
the CI reproduction the issue cites: ``CLIPModel.__init__() got an unexpected
keyword argument 'resume_download'`` (run 32839088246). An ``AutoConfig``/
``AutoTokenizer`` call instead survives it: ``PretrainedConfig.__post_init__``
stores any leftover kwarg as a bare instance attribute and
``PreTrainedTokenizerBase.__init__`` just leaves it sitting, unused, in
``init_kwargs`` -- silently swallowed, latent debt rather than a crash on that
path. Either way resumption is automatic in v5, so the argument is dead
everywhere and belongs nowhere; no replacement kwarg exists to substitute.

Mechanism
---------
:func:`find_from_pretrained_calls` tracks paren depth from each ``from_pretrained(``
match so a call wrapped across several lines -- every real call site in this repo
is -- is captured whole rather than just its opening line. Same technique as
``credential_vault_resolution_guard_test.py``'s ``_vault_routed_line_numbers``,
applied to ``from_pretrained(`` instead of ``resolve_provider_key(``. Source is
prose-stripped first (:func:`repo_tests.credential_vault_prose_strip.strip_prose`)
so a docstring merely *mentioning* the API
(``llm_shared/optimization/hf_quantizer.py:97``, ``AutoConfig.from_pretrained(...)
.to_dict()`` in an ``Args:`` block) is never counted as a call site.

Reach floor
-----------
The tree carries 22 real ``from_pretrained`` call sites as of this fix (18 of
which passed ``resume_download``, now all fixed; #15054's own table listed only
10, missing ``multimodal_processor/processors/voice.py`` entirely and 4 of
``vision.py``'s 5 sites). :data:`FROM_PRETRAINED_REACH_FLOOR` is set to 15 --
comfortably below 22 so an unrelated trim doesn't false-fail this guard, but far
above zero, so a walk that stops finding call sites (moved root, renamed helper)
fails loudly instead of reporting a false "no offenders" having checked nothing.

The mutation this guard exists to catch
----------------------------------------
``test_a_reintroduced_resume_download_is_caught`` proves the detector directly
against a reproduction of the exact pre-fix
``multimodal_processor/processors/vision.py`` ``CLIPModel.from_pretrained`` call
site (fixed in this same PR) -- a ``resume_download=True`` kwarg on a line other
than the call's own opening line, the shape every real offender in this repo used.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv (git ls-files), no shell, no caller input
from pathlib import Path

from repo_tests.credential_vault_prose_strip import UnparseableSourceError, strip_prose

REPO_ROOT = Path(__file__).resolve().parents[1]

_FROM_PRETRAINED_RE = re.compile(r"\bfrom_pretrained\s*\(")
_RESUME_DOWNLOAD_RE = re.compile(r"\bresume_download\b")
_SKIP_PATH_SUBSTRINGS = ("/tests/", "repo_tests/")

#: Below this, the sweep itself is broken (moved root, renamed helper), not a
#: genuinely thinned-out tree. See module docstring's "Reach floor" section.
FROM_PRETRAINED_REACH_FLOOR = 15


def _tracked_python_files() -> list[str]:
    out = subprocess.run(
        ["git", "-C", str(REPO_ROOT), "ls-files", "*.py"],
        capture_output=True,
        text=True,
        check=True,
    ).stdout
    return [line for line in out.splitlines() if line]


def _is_production_file(rel_path: str) -> bool:
    if rel_path.endswith("_test.py") or Path(rel_path).name.startswith("test_"):
        return False
    return not any(needle in rel_path for needle in _SKIP_PATH_SUBSTRINGS)


def _capture_call_span(lines: list[str], lineno: int, start_col: int) -> tuple[list[str], int]:
    """From ``lines[lineno]`` starting at ``start_col``, return the call's span
    lines and the index of its last line.

    Tracks paren depth from the call's opening ``(`` so a call wrapped across
    several lines is captured whole, not just its first line -- the same
    technique ``credential_vault_resolution_guard_test._vault_routed_line_numbers``
    uses for ``resolve_provider_key(...)``.
    """
    depth = 0
    cursor = lineno
    offset = start_col
    span_lines: list[str] = []
    while cursor < len(lines):
        segment = lines[cursor][offset:]
        depth += segment.count("(") - segment.count(")")
        span_lines.append(lines[cursor])
        offset = 0
        if depth <= 0:
            break
        cursor += 1
    return span_lines, cursor


def find_from_pretrained_calls(text: str) -> list[tuple[int, str]]:
    """Every ``(line_no, call_span)`` for a ``.from_pretrained(...)`` call in *text*.

    See :func:`_capture_call_span` for how a multi-line call is captured whole.
    """
    lines = text.splitlines()
    calls: list[tuple[int, str]] = []
    lineno = 0
    while lineno < len(lines):
        match = _FROM_PRETRAINED_RE.search(lines[lineno])
        if match is None:
            lineno += 1
            continue
        span_lines, cursor = _capture_call_span(lines, lineno, match.start())
        calls.append((lineno + 1, "\n".join(span_lines)))
        lineno = cursor + 1
    return calls


def production_from_pretrained_calls() -> dict[str, list[tuple[int, str]]]:
    """Every production file's ``from_pretrained`` call spans, prose stripped.

    A file that fails to tokenize fails this call outright, with the offending
    path attached, rather than being silently skipped -- the same discipline
    ``credential_vault_resolution_guard_test.py`` applies for the same reason.
    """
    found: dict[str, list[tuple[int, str]]] = {}
    for rel in _tracked_python_files():
        if not _is_production_file(rel):
            continue
        path = REPO_ROOT / rel
        try:
            text = path.read_text(encoding="utf-8", errors="ignore")
        except OSError:
            continue
        try:
            calls = find_from_pretrained_calls(strip_prose(text))
        except UnparseableSourceError as exc:
            raise UnparseableSourceError(f"{rel}: {exc}") from exc
        if calls:
            found[rel] = calls
    return found


def test_the_from_pretrained_sweep_reaches_the_repo() -> None:
    """Guard the guard: a broken walk finding nothing agrees with a clean tree."""
    total = sum(len(calls) for calls in production_from_pretrained_calls().values())
    assert total >= FROM_PRETRAINED_REACH_FLOOR, (
        f"#15054: only {total} from_pretrained call sites found (floor "
        f"{FROM_PRETRAINED_REACH_FLOOR}) -- the sweep is broken (moved root, "
        f"renamed helper), not a genuinely thinned-out tree."
    )


def test_no_from_pretrained_call_passes_resume_download() -> None:
    """#15054: resume_download was removed from from_pretrained in transformers v5.

    See module docstring for what removal actually does at the pinned 5.15.1
    (live TypeError on model/processor classes, silent no-op on Auto config/
    tokenizer classes) -- both call shapes must stay clear, since neither
    behaviour is one this repo wants back.
    """
    offenders = [
        (rel, lineno)
        for rel, calls in production_from_pretrained_calls().items()
        for lineno, span in calls
        if _RESUME_DOWNLOAD_RE.search(span)
    ]
    assert not offenders, "resume_download passed to from_pretrained (removed in transformers v5):\n" + "\n".join(
        f"  {rel}:{lineno}" for rel, lineno in sorted(offenders)
    )


def test_a_reintroduced_resume_download_is_caught() -> None:
    """The contrast mutation: prove the detector actually fires, not pass vacuously.

    Reproduces the exact pre-fix shape of
    ``multimodal_processor/processors/vision.py``'s ``CLIPModel.from_pretrained``
    call (fixed in this same PR).
    """
    pre_fix_shape = (
        "        self.clip_model = CLIPModel.from_pretrained(\n"
        '            "openai/clip-vit-base-patch32", resume_download=True\n'
        "        ).to(self.device)\n"
    )
    calls = find_from_pretrained_calls(pre_fix_shape)
    assert len(calls) == 1
    assert _RESUME_DOWNLOAD_RE.search(calls[0][1]) is not None, (
        "the detector failed to flag a reproduction of the exact pre-fix "
        "vision.py CLIPModel.from_pretrained call -- it would not have caught #15054"
    )


def test_a_docstring_mention_is_not_counted_as_a_call_site() -> None:
    """The other half of the same guard: no false positive on prose.

    Reproduces ``llm_shared/optimization/hf_quantizer.py:97`` verbatim: a
    docstring naming ``AutoConfig.from_pretrained(...)`` in an ``Args:`` block,
    never executed as code.
    """
    docstring_only = (
        '    """Detects a config quantization type.\n'
        "\n"
        "    Args:\n"
        "        model_config: Typically loaded from ``config.json`` via\n"
        "            ``AutoConfig.from_pretrained(...).to_dict()``.\n"
        '    """\n'
    )
    assert find_from_pretrained_calls(strip_prose(docstring_only)) == []
