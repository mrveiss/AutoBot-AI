# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Provider choice and fallback order (#17778).

Assertions are about WHICH provider is chosen, never about transcript text.
"""

from unittest.mock import create_autospec, patch

import pytest

from voice_processing.providers import (
    SpeechProvider,
    SpeechProviderRegistry,
    TranscriptionUnavailableError,
    TranscriptSegment,
)
from voice_processing.providers.generic_provider import GENERIC_LANGUAGES
from voice_processing.providers.whisper_provider import WhisperProvider


def _seg(text: str = "x") -> TranscriptSegment:
    return TranscriptSegment(text=text, start_time=0.0, end_time=0.0, confidence=0.9)


def _fake(name: str, segments=None, *, available=True, error=None):
    provider = create_autospec(SpeechProvider, instance=True, spec_set=True)
    type(provider).provider_name = name
    provider.is_available.return_value = available
    provider.is_external = False
    provider.external_when_local_unavailable = False
    provider.is_default_local = False
    if error is not None:
        provider.transcribe.side_effect = error
    else:
        provider.transcribe.return_value = segments if segments is not None else [_seg()]
    return provider


def _registry_with_defaults(monkeypatch, *, cloud_key: bool):
    """The registry exactly as ``initialize_providers`` builds it."""
    import voice_processing.providers as providers_pkg
    import voice_processing.providers.registry_init as registry_init
    from voice_processing.providers import selection

    fresh = SpeechProviderRegistry()
    monkeypatch.setattr(providers_pkg, "_registry", fresh)
    if not cloud_key:
        monkeypatch.setattr(selection, "_PROVIDER_MAP", {})
    registry_init.initialize_providers()
    return fresh


def test_english_without_cloud_key_chooses_whisper(monkeypatch):
    registry = _registry_with_defaults(monkeypatch, cloud_key=False)
    assert isinstance(registry.get_provider("en"), WhisperProvider)


@pytest.mark.parametrize("lang", GENERIC_LANGUAGES)
def test_whisper_sits_between_cloud_and_generic_for_every_generic_language(monkeypatch, lang):
    registry = _registry_with_defaults(monkeypatch, cloud_key=False)
    names = [type(p).__name__ for p in registry.get_all_providers(lang)]
    assert names == ["WhisperProvider", "GenericProvider"]


def test_latvian_keeps_late_then_tilde_first(monkeypatch):
    registry = _registry_with_defaults(monkeypatch, cloud_key=False)
    for lang in ("lv", "lat"):
        names = [type(p).__name__ for p in registry.get_all_providers(lang)]
        assert names[:2] == ["LateProvider", "TildeProvider"]
        assert "WhisperProvider" not in names


def test_cloud_provider_beats_whisper_for_english(monkeypatch):
    registry = _registry_with_defaults(monkeypatch, cloud_key=False)
    cloud = _fake("cloud")
    registry.register("en", cloud, priority=15)
    assert registry.get_provider("en") is cloud


@pytest.mark.asyncio
async def test_failing_top_provider_falls_through_to_the_next():
    registry = SpeechProviderRegistry()
    top = _fake("top", error=RuntimeError("boom"))
    second = _fake("second")
    registry.register("en", top, priority=10)
    registry.register("en", second, priority=0)
    outcome = await registry.transcribe_with_fallback("a.wav", "en")
    assert outcome.provider is second
    top.transcribe.assert_awaited_once()


@pytest.mark.asyncio
async def test_unavailable_provider_is_skipped_to_the_next_local_one():
    registry = SpeechProviderRegistry()
    unavailable = _fake("down", available=False)
    last = _fake("last")
    registry.register("en", unavailable, priority=10)
    registry.register("en", last, priority=0)
    outcome = await registry.transcribe_with_fallback("a.wav", "en")
    assert outcome.provider is last
    unavailable.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_empty_result_ends_the_chain_and_never_reaches_a_second_provider():
    registry = SpeechProviderRegistry()
    empty = _fake("empty", segments=[])
    later = _fake("later")
    registry.register("en", empty, priority=10)
    registry.register("en", later, priority=0)
    outcome = await registry.transcribe_with_fallback("a.wav", "en")
    assert outcome.provider is empty and outcome.segments == []
    later.transcribe.assert_not_called()


def _external(name, **kwargs):
    provider = _fake(name, **kwargs)
    provider.is_external = True
    return provider


def _local(name, **kwargs):
    provider = _fake(name, **kwargs)
    provider.is_external = False
    provider.is_default_local = True
    return provider


@pytest.mark.asyncio
async def test_cloud_failure_never_reaches_another_cloud_and_goes_local():
    registry = SpeechProviderRegistry()
    selected = _external("selected", error=RuntimeError("down"))
    other = _external("other")
    whisper = _local("whisper")
    registry.register("en", selected, priority=20)
    registry.register("en", other, priority=15)
    registry.register("en", whisper, priority=5)
    outcome = await registry.transcribe_with_fallback("a.wav", "en")
    assert outcome.provider is whisper
    other.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_cloud_failure_without_local_does_not_reach_another_cloud():
    registry = SpeechProviderRegistry()
    other = _external("other")
    registry.register("en", _external("selected", error=RuntimeError("down")), priority=20)
    registry.register("en", other, priority=15)
    with pytest.raises(TranscriptionUnavailableError) as caught:
        await registry.transcribe_with_fallback("a.wav", "en")
    assert "other: external fallthrough refused" in caught.value.reasons
    other.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_opt_in_enables_external_fallthrough(monkeypatch):
    monkeypatch.setenv("AUTOBOT_SPEECH_EXTERNAL_FALLTHROUGH", "true")
    registry = SpeechProviderRegistry()
    other = _external("other")
    registry.register("en", _external("selected", error=RuntimeError("down")), priority=20)
    registry.register("en", other, priority=15)
    outcome = await registry.transcribe_with_fallback("a.wav", "en")
    assert outcome.provider is other


@pytest.mark.asyncio
async def test_whisper_raising_does_not_unlock_generic(monkeypatch):
    registry = _registry_with_defaults(monkeypatch, cloud_key=False)
    whisper, generic = registry.get_all_providers("en")
    boom = _local("whisper", error=RuntimeError("boom"))
    registry._providers["en"] = [(boom, 5), (generic, 0)]
    with patch.object(type(generic), "transcribe") as generic_run:
        with pytest.raises(TranscriptionUnavailableError):
            await registry.transcribe_with_fallback("a.wav", "en")
    generic_run.assert_not_called()


@pytest.mark.asyncio
async def test_whisper_unavailable_means_generic_is_used(monkeypatch):
    registry = _registry_with_defaults(monkeypatch, cloud_key=False)
    whisper, generic = registry.get_all_providers("en")
    with patch("voice_processing.providers.whisper_provider.whisper_loadable", return_value=False):
        assert whisper.is_available() is False
        generic_double = _fake("generic")
        generic_double.is_external = True
        generic_double.external_when_local_unavailable = True
        registry._providers["en"] = [(whisper, 5), (generic_double, 0)]
        outcome = await registry.transcribe_with_fallback("a.wav", "en")
    assert outcome.provider is generic_double


@pytest.mark.asyncio
async def test_no_provider_raises_and_all_raising_is_a_failure_with_reasons():
    registry = SpeechProviderRegistry()
    with pytest.raises(ValueError, match="No speech provider"):
        await registry.transcribe_with_fallback("a.wav", "xx")
    registry.register("en", _fake("a", error=RuntimeError("first")), priority=1)
    registry.register("en", _fake("b", error=RuntimeError("last")), priority=0)
    with pytest.raises(TranscriptionUnavailableError) as caught:
        await registry.transcribe_with_fallback("a.wav", "en")
    assert caught.value.reasons == ["a: RuntimeError", "b: RuntimeError"]


@pytest.mark.asyncio
async def test_a_provider_that_ran_with_no_speech_is_a_genuine_empty_not_an_error():
    registry = SpeechProviderRegistry()
    registry.register("en", _fake("a", segments=[]), priority=0)
    outcome = await registry.transcribe_with_fallback("a.wav", "en")
    assert outcome.provider is not None and outcome.segments == []


def _lv_registry(late, tilde, other_cloud=None):
    registry = SpeechProviderRegistry()
    registry.register("lv", late, priority=10)
    registry.register("lv", tilde, priority=5)
    registry.declare_primary_external("lv", tilde)
    if other_cloud is not None:
        registry.register("lv", other_cloud, priority=1)
    return registry


@pytest.mark.asyncio
@pytest.mark.parametrize("late_kwargs", [{"available": False}, {"error": RuntimeError("down")}])
async def test_latvian_with_late_failing_runs_tilde(late_kwargs):
    tilde = _external("tilde")
    outcome = await _lv_registry(_fake("late", **late_kwargs), tilde).transcribe_with_fallback("a.wav", "lv")
    assert outcome.provider is tilde


@pytest.mark.asyncio
async def test_latvian_with_late_missing_and_tilde_failing_reaches_no_other_cloud():
    other = _external("other")
    registry = _lv_registry(_fake("late", available=False), _external("tilde", error=RuntimeError("x")), other)
    with pytest.raises(TranscriptionUnavailableError):
        await registry.transcribe_with_fallback("a.wav", "lv")
    other.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_english_with_whisper_raising_does_not_reach_tilde(monkeypatch):
    registry = _registry_with_defaults(monkeypatch, cloud_key=False)
    _, generic = registry.get_all_providers("en")
    tilde = _external("tilde")
    registry._providers["en"] = [(_local("whisper", error=RuntimeError("boom")), 5), (tilde, 3), (generic, 0)]
    with pytest.raises(TranscriptionUnavailableError):
        await registry.transcribe_with_fallback("a.wav", "en")
    tilde.transcribe.assert_not_called()


@pytest.mark.asyncio
async def test_opt_in_still_enables_general_fallthrough_for_latvian(monkeypatch):
    monkeypatch.setenv("AUTOBOT_SPEECH_EXTERNAL_FALLTHROUGH", "true")
    other = _external("other")
    registry = _lv_registry(_fake("late", available=False), _external("tilde", error=RuntimeError("x")), other)
    assert (await registry.transcribe_with_fallback("a.wav", "lv")).provider is other


def test_registry_init_declares_tilde_primary_for_latvian(monkeypatch):
    registry = _registry_with_defaults(monkeypatch, cloud_key=False)
    for lang in ("lv", "lat"):
        assert type(registry._primary_external[lang]).__name__ == "TildeProvider"
    assert "en" not in registry._primary_external
