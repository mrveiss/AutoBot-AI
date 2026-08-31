# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""#15054 -- ``resume_download`` was removed from ``from_pretrained`` in the pinned
``transformers==5.15.1`` (``requirements-ci/ai-ml.txt:10``). Every call site in the
tree passed it anyway.

What actually happens at 5.15.1, read from the installed package's own source
rather than assumed from memory: ``resume_download`` is popped nowhere before
``cls(*args, **kwargs)`` runs, so the split is entirely about what that
particular ``__init__`` does with the leftover kwarg.

**8 of this fix's 18 sites raise.** ``PreTrainedModel.from_pretrained``
(``modeling_utils.py``) forwards unrecognized kwargs through
``config_class.from_pretrained(..., return_unused_kwargs=True, **kwargs)``; the
still-unused remainder becomes ``model_kwargs``, reaching
``cls(config, *model_args, **model_kwargs)``. ``CLIPModel`` x2,
``Wav2Vec2Model``, ``AutoModel``, ``Blip2ForConditionalGeneration`` x2,
``WhisperForConditionalGeneration`` and ``Wav2Vec2ForCTC`` have no ``**kwargs``
catch-all on ``__init__`` -- each takes only ``config`` (plus ``target_lang`` for
``Wav2Vec2ForCTC``) -- so this is a live ``TypeError``, exactly the CI
reproduction the issue cites: ``CLIPModel.__init__() got an unexpected keyword
argument 'resume_download'`` (run 32839088246).

**The other 10 swallow it silently -- including every Processor class, not
just Auto*.** ``CLIPProcessor`` x2, ``Wav2Vec2Processor`` x2, ``Blip2Processor``,
``WhisperProcessor``, ``AutoTokenizer`` x2 and ``AutoConfig`` x2 never reach a
strict ``__init__`` with this kwarg still attached.
``ProcessorMixin.from_args_and_dict`` (``processing_utils.py``) computes
``accepted_args_and_kwargs`` from ``cls.__init__.__code__.co_varnames`` and calls
``validate_init_kwargs`` to split the incoming dict into
``valid_kwargs``/``unused_kwargs`` *before* instantiating -- ``resume_download``
lands in ``unused_kwargs`` and is dropped, never passed to ``__init__`` at all
(an earlier pass at this docstring got this wrong, assuming Processor classes
raised like Model classes do; a review of this PR caught it by reading
``from_args_and_dict``/``validate_init_kwargs`` directly). Config classes take a
different silent path: ``PretrainedConfig.__post_init__`` stores any leftover
kwarg as a bare instance attribute, and ``PreTrainedTokenizerBase.__init__``
just leaves it sitting, unused, in ``init_kwargs``.

Either way the conclusion is unchanged: **live breakage**, not latent debt,
because every one of this fix's six loaders calls its Model class before its
Processor class (e.g. ``vision.py``'s ``_load_models``: ``CLIPModel.from_pretrained``
before ``CLIPProcessor.from_pretrained``) -- the Model call's ``TypeError`` aborts
the whole ``_load_models`` sequence before the Processor call, whichever way it
would have gone, is ever reached. And regardless of which half a given call falls
into, resumption is automatic in v5, so the argument is dead everywhere and
belongs nowhere; no replacement kwarg exists to substitute.

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

Known limitation -- the splat blind spot
-----------------------------------------
This is a text scanner, not an interpreter: it can only see a kwarg spelled
literally inside a ``from_pretrained(...)`` span. A ``**splat`` of a variable
built elsewhere (``_dl_kwargs = {"resume_download": True}`` two lines above,
then ``CLIPModel.from_pretrained("x", **_dl_kwargs)``) hides the kwarg from a
plain-text ban, and resolving the splat's actual contents would mean executing
code -- something this guard, and this whole fix, deliberately never does.
:data:`SPLAT_ALLOWLIST` closes that gap the same way the (unrelated)
``ALLOWLIST`` in ``credential_vault_resolution_guard_test.py`` closes its own:
*any* ``**splat`` inside a ``from_pretrained`` span is review-required, not
trusted, by default. An unlisted one fails
``test_no_unreviewed_splat_kwargs_reach_from_pretrained`` outright, forcing a
human to read the splatted dict's construction and either add a justified entry
(as ``layer_inference.py``'s two ``**kwargs`` sites below did -- both build
``kwargs`` from ``cache_dir``/``use_fast`` only, read by hand) or fix a real
offender. The allowlist is keyed by ``(file, line)``, not by the splat's
content, so it inherits the same residual tradeoff the credential guard's
allowlist already accepts in this repo: it re-verifies on every line-number
drift (``test_splat_allowlist_entries_still_correspond_to_a_real_splat`` catches
a stale entry), but not on an in-place edit to the same line's dict that keeps
the line number fixed.

The mutation this guard exists to catch
----------------------------------------
``test_a_reintroduced_resume_download_is_caught`` proves the direct-kwarg
detector against a reproduction of the exact pre-fix
``multimodal_processor/processors/vision.py`` ``CLIPModel.from_pretrained`` call
site (fixed in this same PR) -- a ``resume_download=True`` kwarg on a line other
than the call's own opening line, the shape every real offender in this repo
used. ``test_a_splat_kwargs_call_is_flagged_for_review`` proves the splat
detector against the indirect shape above, confirming the guard degrades to
"flag for review" rather than "silently pass" on the one shape it cannot resolve
by reading alone.
"""

from __future__ import annotations

import re
import subprocess  # nosec B404  # fixed argv (git ls-files), no shell, no caller input
from pathlib import Path

from repo_tests.credential_vault_prose_strip import UnparseableSourceError, strip_prose

REPO_ROOT = Path(__file__).resolve().parents[1]

_FROM_PRETRAINED_RE = re.compile(r"\bfrom_pretrained\s*\(")
_RESUME_DOWNLOAD_RE = re.compile(r"\bresume_download\b")
_SPLAT_RE = re.compile(r"\*\*\w+")
_SKIP_PATH_SUBSTRINGS = ("/tests/", "repo_tests/")

#: Below this, the sweep itself is broken (moved root, renamed helper), not a
#: genuinely thinned-out tree. See module docstring's "Reach floor" section.
FROM_PRETRAINED_REACH_FLOOR = 15

#: ``(repo-relative file, line_no) -> reason`` for every ``**splat`` this guard's
#: text scan cannot resolve on its own (see module docstring's "Known
#: limitation" section). Each entry was read by hand at the time it was added
#: and confirmed to never carry ``resume_download``.
SPLAT_ALLOWLIST: dict[tuple[str, int], str] = {
    (
        "autobot-backend/llm_shared/optimization/layer_inference.py",
        198,
    ): "kwargs built two lines above from cache_dir only (#15054)",
    (
        "autobot-backend/llm_shared/optimization/layer_inference.py",
        565,
    ): "kwargs built two lines above from use_fast/cache_dir only (#15054)",
}


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


def test_no_unreviewed_splat_kwargs_reach_from_pretrained() -> None:
    """The splat half of the guard: an unlisted ``**splat`` fails, forcing review.

    Text alone cannot tell whether a splatted dict carries ``resume_download``
    (see module docstring's "Known limitation" section), so every ``**splat``
    inside a ``from_pretrained`` span must be on :data:`SPLAT_ALLOWLIST`, with a
    reason confirming it was actually read.
    """
    unreviewed = [
        (rel, lineno)
        for rel, calls in production_from_pretrained_calls().items()
        for lineno, span in calls
        if _SPLAT_RE.search(span) and (rel, lineno) not in SPLAT_ALLOWLIST
    ]
    assert not unreviewed, "unreviewed **splat inside a from_pretrained call -- read it and allowlist or fix it:\n" + "\n".join(
        f"  {rel}:{lineno}" for rel, lineno in sorted(unreviewed)
    )


def test_splat_allowlist_entries_still_correspond_to_a_real_splat() -> None:
    """A stale entry (the splat it excused is gone) should shrink, not linger."""
    found = production_from_pretrained_calls()
    live_splats = {
        (rel, lineno) for rel, calls in found.items() for lineno, span in calls if _SPLAT_RE.search(span)
    }
    stale = sorted(key for key in SPLAT_ALLOWLIST if key not in live_splats)
    assert not stale, f"SPLAT_ALLOWLIST entries with no matching splat left -- delete them: {stale}"


def test_a_splat_kwargs_call_is_flagged_for_review() -> None:
    """The blind spot's contrast mutation: an indirect splat is still caught.

    Reproduces the exact reproduction this guard cannot resolve by reading
    alone -- a ``resume_download`` hidden inside a splatted dict -- and proves
    it is flagged as unreviewed (not allowlisted, not silently passed) rather
    than invisible to the guard entirely.
    """
    splat_shape = (
        '        _dl_kwargs = {"resume_download": True}\n'
        '        CLIPModel.from_pretrained("x", **_dl_kwargs)\n'
    )
    calls = find_from_pretrained_calls(splat_shape)
    assert len(calls) == 1
    lineno, span = calls[0]
    assert _SPLAT_RE.search(span) is not None, "the splat detector missed a **_dl_kwargs splat entirely"

    fake_file = "repro/not_a_real_file.py"
    unreviewed = [
        (fake_file, ln)
        for ln, sp in calls
        if _SPLAT_RE.search(sp) and (fake_file, ln) not in SPLAT_ALLOWLIST
    ]
    assert unreviewed == [(fake_file, lineno)], (
        "the reproduction of the indirect-splat resume_download shape was not "
        "flagged for review -- this guard would not have caught it"
    )
