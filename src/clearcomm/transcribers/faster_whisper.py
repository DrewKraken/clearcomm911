"""Self-hosted speech-to-text using faster-whisper (CTranslate2 Whisper).

This is the on-premises transcriber: audio never leaves the agency network. v0.1 buffers the audio
stream and transcribes it in one pass, emitting the model's segments as final results. Low-latency
incremental decoding (interim results, voice-activity-gated windows) is layered in the pipeline
later; the contract here is the same either way.

The model is injectable so the adapter's logic — audio assembly, segment conversion, confidence
mapping — is unit-tested without downloading weights or running inference. The default path lazily
imports faster-whisper so the core package does not depend on it.
"""

from __future__ import annotations

import asyncio
import math
from collections.abc import AsyncIterator
from typing import Any, Protocol

import numpy as np
import numpy.typing as npt

from ..interfaces import Transcriber
from ..types import AudioFrame, TranscriptSegment

_INT16_FULL_SCALE = 32768.0
MODEL_SAMPLE_RATE = 16000
"""Whisper's native input rate; incoming audio is resampled to this."""


class _WhisperModel(Protocol):
    """The subset of the faster-whisper ``WhisperModel`` API this adapter relies on."""

    def transcribe(self, audio: npt.NDArray[np.float32], **kwargs: Any) -> tuple[Any, Any]: ...


def _segment_confidence(avg_logprob: float, no_speech_prob: float) -> float:
    """Map faster-whisper's log-probabilities to a normalized 0.0 to 1.0 confidence.

    ``avg_logprob`` is the mean token log-probability (≤ 0); ``exp`` recovers an approximate
    probability. A high ``no_speech_prob`` discounts it, so a segment the model suspects is not
    speech is surfaced as low-confidence rather than presented as certain.
    """
    base = math.exp(min(avg_logprob, 0.0))
    confidence = base * (1.0 - no_speech_prob)
    return max(0.0, min(1.0, confidence))


class FasterWhisperTranscriber(Transcriber):
    def __init__(
        self,
        model_size: str = "large-v3",
        *,
        language: str = "es",
        model: _WhisperModel | None = None,
        device: str = "cpu",
        compute_type: str = "int8",
    ) -> None:
        self._language = language
        self._model = (
            model if model is not None else self._load_model(model_size, device, compute_type)
        )

    @staticmethod
    def _load_model(model_size: str, device: str, compute_type: str) -> _WhisperModel:
        from faster_whisper import WhisperModel

        model: _WhisperModel = WhisperModel(model_size, device=device, compute_type=compute_type)
        return model

    @staticmethod
    def _to_float_pcm(frames: list[AudioFrame]) -> tuple[npt.NDArray[np.float32], int]:
        """Concatenate 16-bit PCM frames into a normalized float32 signal."""
        rate = frames[0].sample_rate
        chunks = [np.frombuffer(frame.pcm, dtype=np.int16) for frame in frames]
        signal = np.concatenate(chunks).astype(np.float32) / _INT16_FULL_SCALE
        return signal, rate

    async def transcribe(
        self, frames: AsyncIterator[AudioFrame]
    ) -> AsyncIterator[TranscriptSegment]:
        buffered = [frame async for frame in frames]
        if not buffered:
            return

        signal, rate = self._to_float_pcm(buffered)
        if rate != MODEL_SAMPLE_RATE:
            from ..audio import resample

            signal = resample(signal, rate, MODEL_SAMPLE_RATE)

        segments, info = await asyncio.to_thread(self._run, signal)
        language = getattr(info, "language", None) or self._language

        for segment in segments:
            yield TranscriptSegment(
                text=segment.text.strip(),
                is_final=True,
                start=segment.start,
                end=segment.end,
                language=language,
                confidence=_segment_confidence(segment.avg_logprob, segment.no_speech_prob),
            )

    def _run(self, signal: npt.NDArray[np.float32]) -> tuple[list[Any], Any]:
        segments, info = self._model.transcribe(signal, language=self._language)
        return list(segments), info
