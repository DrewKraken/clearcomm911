"""Tests for the benchmark's audio-packing and transcription helpers.

The full benchmark needs real weights and audio; these cover the pure glue that CI can verify.
"""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pytest

from clearcomm.benchmark import BenchmarkResult, signal_to_frame, transcribe_text
from clearcomm.transcribers.faster_whisper import FasterWhisperTranscriber


def test_signal_to_frame_packs_int16_pcm() -> None:
    signal = np.array([0.0, 1.0, -1.0, 0.5], dtype=np.float32)
    frame = signal_to_frame(signal, 16000)
    assert frame.sample_rate == 16000
    recovered = np.frombuffer(frame.pcm, dtype=np.int16)
    assert recovered[0] == 0
    assert recovered[1] == 32767
    assert recovered[2] == -32767


def test_signal_to_frame_clips_out_of_range() -> None:
    frame = signal_to_frame(np.array([2.0, -2.0], dtype=np.float32), 16000)
    recovered = np.frombuffer(frame.pcm, dtype=np.int16)
    assert recovered[0] == 32767
    assert recovered[1] == -32767


@dataclass
class _Seg:
    text: str
    start: float
    end: float
    avg_logprob: float
    no_speech_prob: float


@dataclass
class _Info:
    language: str


class _FakeModel:
    def transcribe(self, audio: np.ndarray, **kwargs: object) -> tuple[list[_Seg], _Info]:
        return [_Seg("hola", 0.0, 0.5, -0.1, 0.0), _Seg("mundo", 0.5, 1.0, -0.1, 0.0)], _Info("es")


def test_transcribe_text_joins_segments() -> None:
    transcriber = FasterWhisperTranscriber(model=_FakeModel())
    text = transcribe_text(transcriber, np.zeros(16000, dtype=np.float32), 16000)
    assert text == "hola mundo"


def test_benchmark_result_degradation() -> None:
    result = BenchmarkResult(clean_wer=0.10, telephony_wer=0.25)
    assert result.degradation == pytest.approx(0.15)
