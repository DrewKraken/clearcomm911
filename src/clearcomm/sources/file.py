"""Recorded-file audio source.

Streams any libsndfile-readable file as the pipeline's frame input: the audio is mixed to mono and
emitted as fixed-duration 16-bit PCM frames at the file's native sample rate, leaving resampling to
the stages downstream. With ``realtime`` set, frames are paced to wall-clock so a recording plays
through the console the way a live call would; left off, the file is drained as fast as possible —
the path the benchmark and the tests use.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator
from pathlib import Path

import numpy as np
import numpy.typing as npt

from ..interfaces import AudioSource
from ..types import AudioFrame

_INT16_MAX = 32767
DEFAULT_FRAME_DURATION = 0.02
"""Seconds of audio per frame (20 ms, a common telephony framing)."""


def _to_int16_pcm(samples: npt.NDArray[np.float32]) -> bytes:
    """Pack a float32 signal in [-1.0, 1.0] into 16-bit PCM bytes."""
    return (np.clip(samples, -1.0, 1.0) * _INT16_MAX).astype(np.int16).tobytes()


class FileAudioSource(AudioSource):
    """Streams a recorded audio file as :class:`~clearcomm.types.AudioFrame` input."""

    def __init__(
        self,
        path: Path | str,
        *,
        frame_duration: float = DEFAULT_FRAME_DURATION,
        realtime: bool = False,
    ) -> None:
        if frame_duration <= 0:
            raise ValueError(f"frame_duration must be positive, got {frame_duration}")
        self._path = Path(path)
        self._frame_duration = frame_duration
        self._realtime = realtime

    async def frames(self) -> AsyncIterator[AudioFrame]:
        signal, rate = self._read_mono()
        per_frame = max(1, round(rate * self._frame_duration))
        for start in range(0, len(signal), per_frame):
            chunk = signal[start : start + per_frame]
            yield AudioFrame(pcm=_to_int16_pcm(chunk), sample_rate=rate, timestamp=start / rate)
            if self._realtime:
                await asyncio.sleep(len(chunk) / rate)

    def _read_mono(self) -> tuple[npt.NDArray[np.float32], int]:
        import soundfile as sf

        signal, rate = sf.read(self._path, dtype="float32", always_2d=False)
        if signal.ndim > 1:
            signal = signal.mean(axis=1)
        return np.ascontiguousarray(signal, dtype=np.float32), int(rate)
