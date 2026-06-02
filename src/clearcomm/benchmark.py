"""Speech-to-text accuracy and speed benchmark for telephony-band audio.

Runs a transcriber over a corpus of Spanish speech, once clean and once degraded to telephony band
(:func:`clearcomm.audio.to_telephony_band`), and reports word error rate for each. The gap between
the two — the channel cost — is the number that matters: it estimates how much accuracy the phone
channel takes, which is the open question for the on-premises deployment profile.

Alongside accuracy the benchmark reports a real-time factor per model, because accuracy a model
cannot deliver in time is no use on a live call: a factor above 1.0 means transcription runs slower
than the speech itself. Sweeping across model sizes makes that accuracy-versus-speed trade-off
explicit rather than hiding it behind whichever model happens to feel fast.

This is a local tool, not a CI test — it needs real model weights and real audio. Read-speech is an
honest proxy for the channel effect; real-call accuracy is validated privately during a pilot and is
never committed to this repository.

A corpus is a directory of paired files: each ``<name>.<ext>`` audio clip sits beside a
``<name>.txt`` holding its reference transcript.

Usage::

    python -m clearcomm.benchmark --corpus fixtures/spanish --model-sizes small large-v3
"""

from __future__ import annotations

import argparse
import asyncio
from collections.abc import AsyncIterator
from dataclasses import dataclass
from pathlib import Path
from time import perf_counter

import numpy as np
import numpy.typing as npt

from .audio import resample, to_telephony_band
from .transcribers.faster_whisper import MODEL_SAMPLE_RATE, FasterWhisperTranscriber
from .types import AudioFrame

_INT16_MAX = 32767
_AUDIO_SUFFIXES = (".wav", ".flac", ".ogg", ".mp3")


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


def _read_signal(path: Path) -> tuple[npt.NDArray[np.float32], int]:
    """Read an audio file as a mono float32 signal at the model's sample rate."""
    import soundfile as sf

    signal, rate = sf.read(path, dtype="float32", always_2d=False)
    if signal.ndim > 1:
        signal = signal.mean(axis=1).astype(np.float32)
    if rate != MODEL_SAMPLE_RATE:
        signal = resample(signal, rate, MODEL_SAMPLE_RATE)
        rate = MODEL_SAMPLE_RATE
    return np.ascontiguousarray(signal, dtype=np.float32), rate


def _word_error_rate(references: list[str], hypotheses: list[str]) -> float:
    """Aggregate word error rate over the corpus, isolating the optional scoring dependency."""
    from jiwer import wer

    return float(wer(references, hypotheses))


@dataclass(frozen=True)
class BenchmarkResult:
    clean_wer: float
    telephony_wer: float

    @property
    def degradation(self) -> float:
        """The accuracy cost of the phone channel, in absolute WER."""
        return self.telephony_wer - self.clean_wer


def run_benchmark(audio_path: Path, reference: str, *, model_size: str) -> BenchmarkResult:
    """Benchmark a single clip — the degenerate one-fixture case, kept for quick checks."""
    signal, rate = _read_signal(audio_path)
    transcriber = FasterWhisperTranscriber(model_size=model_size)
    clean = transcribe_text(transcriber, signal, rate)
    telephony = transcribe_text(transcriber, to_telephony_band(signal, rate), rate)
    return BenchmarkResult(
        clean_wer=_word_error_rate([reference], [clean]),
        telephony_wer=_word_error_rate([reference], [telephony]),
    )


@dataclass(frozen=True)
class ModelBenchmark:
    """One model's accuracy and speed over the whole corpus."""

    model_size: str
    clips: int
    clean_wer: float
    telephony_wer: float
    real_time_factor: float
    """Telephony transcription time over audio duration; above 1.0 is slower than live."""

    @property
    def degradation(self) -> float:
        """The accuracy cost of the phone channel, in absolute WER."""
        return self.telephony_wer - self.clean_wer


def load_corpus(directory: Path) -> list[tuple[Path, str]]:
    """Pair each audio clip in ``directory`` with its sibling ``.txt`` reference transcript."""
    fixtures: list[tuple[Path, str]] = []
    for audio_path in sorted(directory.iterdir()):
        if audio_path.suffix.lower() not in _AUDIO_SUFFIXES:
            continue
        reference_path = audio_path.with_suffix(".txt")
        if reference_path.exists():
            fixtures.append((audio_path, reference_path.read_text(encoding="utf-8").strip()))
    if not fixtures:
        raise ValueError(f"no audio/.txt fixture pairs found in {directory}")
    return fixtures


def benchmark_model(
    corpus: list[tuple[Path, str]],
    *,
    model_size: str,
    transcriber: FasterWhisperTranscriber | None = None,
) -> ModelBenchmark:
    """Score one model across the corpus, clean and telephony-band, and time the telephony pass."""
    transcriber = transcriber or FasterWhisperTranscriber(model_size=model_size)
    references: list[str] = []
    clean_hyps: list[str] = []
    telephony_hyps: list[str] = []
    audio_seconds = 0.0
    telephony_seconds = 0.0

    for audio_path, reference in corpus:
        signal, rate = _read_signal(audio_path)
        references.append(reference)
        clean_hyps.append(transcribe_text(transcriber, signal, rate))

        telephony_signal = to_telephony_band(signal, rate)
        started = perf_counter()
        telephony_hyps.append(transcribe_text(transcriber, telephony_signal, rate))
        telephony_seconds += perf_counter() - started
        audio_seconds += len(signal) / rate

    return ModelBenchmark(
        model_size=model_size,
        clips=len(corpus),
        clean_wer=_word_error_rate(references, clean_hyps),
        telephony_wer=_word_error_rate(references, telephony_hyps),
        real_time_factor=telephony_seconds / audio_seconds if audio_seconds else 0.0,
    )


def run_sweep(corpus_directory: Path, *, model_sizes: list[str]) -> list[ModelBenchmark]:
    """Benchmark every model size over the same corpus."""
    corpus = load_corpus(corpus_directory)
    return [benchmark_model(corpus, model_size=size) for size in model_sizes]


def _print_report(results: list[ModelBenchmark]) -> None:
    header = f"{'model':<16}{'clips':>6}{'clean':>9}{'telephony':>11}{'channel':>9}{'RTF':>8}"
    print(header)
    print("-" * len(header))
    for r in results:
        print(
            f"{r.model_size:<16}{r.clips:>6}{r.clean_wer:>9.3f}{r.telephony_wer:>11.3f}"
            f"{r.degradation:>+9.3f}{r.real_time_factor:>8.2f}"
        )


def main() -> None:
    parser = argparse.ArgumentParser(description="Telephony-band STT accuracy and speed benchmark.")
    parser.add_argument(
        "--corpus",
        type=Path,
        required=True,
        help="Directory of paired <name>.<ext> and <name>.txt fixtures.",
    )
    parser.add_argument(
        "--model-sizes",
        nargs="+",
        default=["large-v3"],
        help="faster-whisper model sizes to sweep.",
    )
    args = parser.parse_args()

    _print_report(run_sweep(args.corpus, model_sizes=args.model_sizes))


if __name__ == "__main__":
    main()
