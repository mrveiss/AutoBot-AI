# Copyright 2025-2026 mrveiss
# SPDX-License-Identifier: Apache-2.0
# AutoBot - AI-Powered Automation Platform
# Author: mrveiss
"""Characterization of the ffmpeg normalisation format (#17778).

``FFmpegService.extract_audio`` is where uploaded audio is converted to the
format the STT stack consumes. The argv it builds IS that format, so the codec,
sample rate and channel count are pinned here at the subprocess boundary.
"""

import asyncio
from unittest.mock import AsyncMock, create_autospec, patch

import pytest

from media.audio.ffmpeg_service import FFmpegService


def _argv_pairs(argv: list[str]) -> dict[str, str]:
    """Flag -> following value, for the flags that take one."""
    return {flag: argv[i + 1] for i, flag in enumerate(argv[:-1]) if flag in {"-acodec", "-ar", "-ac", "-f"}}


@pytest.fixture
def tmp_path(tmp_path):
    """A temp dir already holding the input clip (written here, outside any event loop)."""
    (tmp_path / "clip.wav").write_bytes(b"RIFF")
    return tmp_path


async def _run_extract(tmp_path, **kwargs) -> list[str]:
    source = tmp_path / "clip.wav"
    process = create_autospec(asyncio.subprocess.Process, instance=True)
    process.communicate = AsyncMock(return_value=(b"", b""))
    process.returncode = 0
    with patch("media.audio.ffmpeg_service.asyncio.create_subprocess_exec", autospec=True) as runner:
        runner.return_value = process
        await FFmpegService().extract_audio(str(source), output_path=str(tmp_path / "out.wav"), **kwargs)
    return list(runner.call_args.args)


@pytest.mark.asyncio
async def test_the_default_call_normalises_to_pcm_s16le_16khz_mono(tmp_path) -> None:
    argv = await _run_extract(tmp_path)
    flags = _argv_pairs(argv)
    assert (flags["-acodec"], flags["-ar"], flags["-ac"]) == ("pcm_s16le", "16000", "1")


@pytest.mark.asyncio
async def test_the_output_is_the_last_argument_and_video_is_dropped(tmp_path) -> None:
    argv = await _run_extract(tmp_path)
    assert argv[-1] == str(tmp_path / "out.wav")
    assert "-vn" in argv
    assert argv[argv.index("-y") + 1] == argv[-1]


@pytest.mark.asyncio
async def test_rate_and_channels_are_parameters_not_constants(tmp_path) -> None:
    flags = _argv_pairs(await _run_extract(tmp_path, sample_rate=8000, channels=2))
    assert (flags["-ar"], flags["-ac"]) == ("8000", "2")


def test_the_defaults_in_the_signature_are_16khz_mono() -> None:
    import inspect

    params = inspect.signature(FFmpegService.extract_audio).parameters
    assert (params["sample_rate"].default, params["channels"].default) == (16000, 1)
