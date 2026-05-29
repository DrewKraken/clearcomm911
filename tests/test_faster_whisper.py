"""Tests for the faster-whisper adapter.

A fake model stands in for ``WhisperModel`` so these exercise the adapter's logic — audio assembly,
segment conversion, confidence mapping — without downloading weights or running inference.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass

import numpy as np
import pytest

from clearcomm.transcribers.faster_whisper import (
    FasterWhisperTranscriber,
    _segment_confidence,
)
from clearcomm.types import AudioFrame, TranscriptSegment


@dataclass
class _FakeSegment:
    text: str
    start: float
    end: float
    avg_logprob: float
    no_speech_prob: float


@dataclass
class _FakeInfo:
    language: str


class _FakeModel:
    def __init__(self, segments: list[_FakeSegment], language: str = "es") -> None:
        self._segments = segments
        self._language = language
        self.received: np.ndarray | None = None

    def transcribe(
        self, audio: np.ndarray, **kwargs: object
    ) -> tuple[list[_FakeSegment], _FakeInfo]:
        self.received = audio
        return self._segments, _FakeInfo(language=self._language)


def _pcm_frame(sample_rate: int = 16000, n: int = 160) -> AudioFrame:
    pcm = np.zeros(n, dtype=np.int16).tobytes()
    return AudioFrame(pcm=pcm, sample_rate=sample_rate, timestamp=0.0)


async def _frames(*frames: AudioFrame) -> AsyncIterator[AudioFrame]:
    for frame in frames:
        yield frame


def _run(transcriber: FasterWhisperTranscriber, *frames: AudioFrame) -> list[TranscriptSegment]:
    async def collect() -> list[TranscriptSegment]:
        return [seg async for seg in transcriber.transcribe(_frames(*frames))]

    return asyncio.run(collect())


def test_converts_model_segments_to_transcript_segments() -> None:
    model = _FakeModel(
        [
            _FakeSegment("  no puedo respirar  ", 0.0, 1.4, avg_logprob=-0.1, no_speech_prob=0.01),
            _FakeSegment("hay un incendio", 1.4, 2.8, avg_logprob=-0.3, no_speech_prob=0.02),
        ]
    )
    segments = _run(FasterWhisperTranscriber(model=model), _pcm_frame())

    assert [s.text for s in segments] == ["no puedo respirar", "hay un incendio"]
    assert all(s.is_final for s in segments)
    assert all(s.language == "es" for s in segments)
    assert all(0.0 <= s.confidence <= 1.0 for s in segments)


def test_empty_stream_yields_nothing() -> None:
    model = _FakeModel([])
    assert _run(FasterWhisperTranscriber(model=model)) == []


def test_language_falls_back_when_model_reports_none() -> None:
    model = _FakeModel([_FakeSegment("hola", 0.0, 0.5, -0.2, 0.0)], language="")
    segments = _run(FasterWhisperTranscriber(model=model, language="es"), _pcm_frame())
    assert segments[0].language == "es"


def test_resamples_non_native_rate() -> None:
    model = _FakeModel([_FakeSegment("hola", 0.0, 0.5, -0.2, 0.0)])
    _run(FasterWhisperTranscriber(model=model), _pcm_frame(sample_rate=8000, n=800))
    assert model.received is not None


@pytest.mark.parametrize(
    ("avg_logprob", "no_speech_prob", "expected"),
    [
        (0.0, 0.0, 1.0),
        (-0.1, 0.0, pytest.approx(0.9048, abs=1e-3)),
        (-1.0, 0.0, pytest.approx(0.3679, abs=1e-3)),
        (-0.1, 1.0, 0.0),
    ],
)
def test_confidence_mapping(avg_logprob: float, no_speech_prob: float, expected: float) -> None:
    assert _segment_confidence(avg_logprob, no_speech_prob) == expected


def test_confidence_is_clamped() -> None:
    assert 0.0 <= _segment_confidence(0.5, 0.0) <= 1.0
