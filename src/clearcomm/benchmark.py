"""Speech-to-text accuracy benchmark for telephony-band audio.

Runs a transcriber over a clean recording and over the same recording degraded to telephony band
(:func:`clearcomm.audio.to_telephony_band`), and reports word error rate against a reference
transcript. The gap between the two is the number that matters: it estimates how much accuracy the
phone channel costs, which is the open question for the on-premises deployment profile.

This is a local tool, not a CI test — it needs real model weights and real audio. Read-speech is an
honest proxy for the channel effect; real-call accuracy is validated privately during a pilot and is
never committed to this repository.

Usage::

    python -m clearcomm.benchmark --audio clip.wav --reference clip.txt --model-size large-v3
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path

import numpy as np
import numpy.typing as npt

from .audio import resample, to_telephony_band
from .transcribers.faster_whisper import MODEL_SAMPLE_RATE, FasterWhisperTranscriber
from .types import AudioFrame

_INT16_MAX = 32767


def signal_to_frame(signal: npt.NDArray[np.float32], rate: int) -> AudioFrame:
    """Pack a float32 signal in [-1.0, 1.0] into a 16-bit PCM :class:`AudioFrame`."""
    pcm = (np.clip(signal, -1.0, 1.0) * _INT16_MAX).astype(np.int16).tobytes()
    return AudioFrame(pcm=pcm, sample_rate=rate, timestamp=0.0)


async def _single_frame_stream(frame: AudioFrame) -> AsyncIterator[AudioFrame]:
    yield frame


def transcribe_text(
    transcriber: FasterWhisperTranscriber, signal: npt.NDArray[np.float32], rate: int
) -> str:
    """Transcribe a whole signal and return the joined transcript text."""

    async def collect() -> str:
        stream = _single_frame_stream(signal_to_frame(signal, rate))
        parts = [segment.text async for segment in transcriber.transcribe(stream)]
        return " ".join(parts).strip()

    return asyncio.run(collect())


@dataclass(frozen=True)
class BenchmarkResult:
    clean_wer: float
    telephony_wer: float

    @property
    def degradation(self) -> float:
        """The accuracy cost of the phone channel, in absolute WER."""
        return self.telephony_wer - self.clean_wer


def run_benchmark(audio_path: Path, reference: str, *, model_size: str) -> BenchmarkResult:
    import soundfile as sf
    from jiwer import wer

    signal, rate = sf.read(audio_path, dtype="float32", always_2d=False)
    if signal.ndim > 1:
        signal = signal.mean(axis=1).astype(np.float32)
    if rate != MODEL_SAMPLE_RATE:
        signal = resample(signal, rate, MODEL_SAMPLE_RATE)
        rate = MODEL_SAMPLE_RATE

    transcriber = FasterWhisperTranscriber(model_size=model_size)
    clean = transcribe_text(transcriber, signal, rate)
    telephony = transcribe_text(transcriber, to_telephony_band(signal, rate), rate)

    return BenchmarkResult(
        clean_wer=float(wer(reference, clean)),
        telephony_wer=float(wer(reference, telephony)),
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Telephony-band STT accuracy benchmark.")
    parser.add_argument("--audio", type=Path, required=True, help="Path to a speech audio file.")
    parser.add_argument(
        "--reference", type=Path, required=True, help="Path to the reference transcript text file."
    )
    parser.add_argument("--model-size", default="large-v3", help="faster-whisper model size.")
    args = parser.parse_args()

    reference = args.reference.read_text(encoding="utf-8").strip()
    result = run_benchmark(args.audio, reference, model_size=args.model_size)

    print(f"clean WER:      {result.clean_wer:.3f}")
    print(f"telephony WER:  {result.telephony_wer:.3f}")
    print(f"channel cost:   {result.degradation:+.3f}")


if __name__ == "__main__":
    main()
