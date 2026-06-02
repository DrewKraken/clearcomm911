"""Tests for the benchmark's audio-packing, transcription, and corpus helpers.

The full benchmark needs real weights and audio; these cover the pure glue that CI can verify — a
fake model stands in for inference, and short signals are written to temporary fixtures.
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import numpy as np
import pytest
import soundfile as sf

from clearcomm.benchmark import (
    BenchmarkResult,
    ModelBenchmark,
    benchmark_model,
    load_corpus,
    signal_to_frame,
    transcribe_text,
)
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


def test_model_benchmark_degradation() -> None:
    result = ModelBenchmark(
        model_size="large-v3", clips=3, clean_wer=0.08, telephony_wer=0.20, real_time_factor=1.4
    )
    assert result.degradation == pytest.approx(0.12)


def _write_fixture(directory: Path, name: str, reference: str, *, rate: int = 16000) -> None:
    sf.write(directory / f"{name}.wav", np.zeros(rate // 5, dtype=np.float32), rate)  # 0.2 s
    (directory / f"{name}.txt").write_text(reference, encoding="utf-8")


def test_load_corpus_pairs_audio_with_references(tmp_path: Path) -> None:
    _write_fixture(tmp_path, "b", "hay un incendio")
    _write_fixture(tmp_path, "a", "no puedo respirar")
    sf.write(tmp_path / "orphan.wav", np.zeros(100, dtype=np.float32), 16000)  # no reference

    corpus = load_corpus(tmp_path)

    assert [path.stem for path, _ in corpus] == ["a", "b"]  # sorted, orphan dropped
    assert [reference for _, reference in corpus] == ["no puedo respirar", "hay un incendio"]


def test_load_corpus_raises_when_empty(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match=r"no audio/\.txt fixture pairs"):
        load_corpus(tmp_path)


def test_benchmark_model_scores_each_pass(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    _write_fixture(tmp_path, "a", "hola mundo")
    _write_fixture(tmp_path, "b", "hola mundo")

    scores = iter([0.1, 0.2])  # the clean pass is scored first, then the telephony pass
    calls: list[tuple[list[str], list[str]]] = []

    def fake_wer(references: list[str], hypotheses: list[str]) -> float:
        calls.append((references, hypotheses))
        return next(scores)

    monkeypatch.setattr("clearcomm.benchmark._word_error_rate", fake_wer)
    transcriber = FasterWhisperTranscriber(model=_FakeModel())

    result = benchmark_model(load_corpus(tmp_path), model_size="fake", transcriber=transcriber)

    assert result.clips == 2
    assert result.clean_wer == pytest.approx(0.1)
    assert result.telephony_wer == pytest.approx(0.2)
    assert result.degradation == pytest.approx(0.1)
    assert result.real_time_factor >= 0.0
    assert len(calls) == 2  # one scoring pass clean, one telephony
    assert all(len(refs) == 2 and len(hyps) == 2 for refs, hyps in calls)  # both clips scored
