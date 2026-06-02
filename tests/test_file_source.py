"""Tests for the recorded-file audio source.

A short signal is written to a temporary file and streamed back, exercising the real read path —
mono mixing, framing, timestamps — without committing any audio fixture.
"""

from __future__ import annotations

import asyncio
from itertools import pairwise
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from clearcomm.sources import FileAudioSource
from clearcomm.types import AudioFrame


def _write_wav(path: Path, signal: np.ndarray, rate: int) -> Path:
    sf.write(path, signal, rate)
    return path


def _drain(source: FileAudioSource) -> list[AudioFrame]:
    async def collect() -> list[AudioFrame]:
        return [frame async for frame in source.frames()]

    return asyncio.run(collect())


def _decode(frames: list[AudioFrame]) -> np.ndarray:
    pcm = b"".join(frame.pcm for frame in frames)
    return np.frombuffer(pcm, dtype=np.int16).astype(np.float32) / 32767.0


def test_streams_file_as_frames(tmp_path: Path) -> None:
    rate = 16000
    signal = (0.5 * np.sin(np.linspace(0.0, 20.0, rate))).astype(np.float32)  # 1 s tone
    source = FileAudioSource(_write_wav(tmp_path / "tone.wav", signal, rate), frame_duration=0.02)

    frames = _drain(source)

    assert len(frames) == 50  # 1 s / 20 ms
    assert all(frame.sample_rate == rate for frame in frames)
    reconstructed = _decode(frames)
    assert len(reconstructed) == len(signal)
    np.testing.assert_allclose(reconstructed, signal, atol=1e-3)


def test_timestamps_advance_by_frame_duration(tmp_path: Path) -> None:
    rate = 8000
    signal = np.zeros(rate, dtype=np.float32)
    wav = _write_wav(tmp_path / "silence.wav", signal, rate)
    source = FileAudioSource(wav, frame_duration=0.05)

    timestamps = [frame.timestamp for frame in _drain(source)]

    assert timestamps[0] == 0.0
    assert all(b - a == pytest.approx(0.05) for a, b in pairwise(timestamps))


def test_mixes_stereo_to_mono(tmp_path: Path) -> None:
    rate = 16000
    left = np.full(rate, 0.4, dtype=np.float32)
    right = np.full(rate, -0.2, dtype=np.float32)
    stereo = np.stack([left, right], axis=1)
    source = FileAudioSource(_write_wav(tmp_path / "stereo.wav", stereo, rate))

    mono = _decode(_drain(source))

    np.testing.assert_allclose(mono, np.full(rate, 0.1, dtype=np.float32), atol=1e-3)


def test_shorter_than_one_frame_yields_single_frame(tmp_path: Path) -> None:
    rate = 16000
    signal = np.zeros(100, dtype=np.float32)  # < 20 ms
    source = FileAudioSource(_write_wav(tmp_path / "blip.wav", signal, rate))

    frames = _drain(source)

    assert len(frames) == 1
    assert len(frames[0].pcm) == 100 * 2  # 100 int16 samples


def test_rejects_nonpositive_frame_duration(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="frame_duration must be positive"):
        FileAudioSource(tmp_path / "x.wav", frame_duration=0.0)


def test_realtime_paces_emission(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    rate = 16000
    signal = np.zeros(rate // 10, dtype=np.float32)  # 0.1 s
    source = FileAudioSource(
        _write_wav(tmp_path / "paced.wav", signal, rate), frame_duration=0.02, realtime=True
    )

    slept: list[float] = []

    async def fake_sleep(seconds: float) -> None:
        slept.append(seconds)

    monkeypatch.setattr("clearcomm.sources.file.asyncio.sleep", fake_sleep)
    frames = _drain(source)

    assert slept  # emission was paced
    assert sum(slept) == pytest.approx(len(frames) * 0.02, abs=1e-6)
