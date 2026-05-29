"""Provider-agnostic contracts for the pipeline stages.

Each stage is defined as an abstract base class so that a concrete provider — cloud or
self-hosted — can be selected by configuration without changing the pipeline. v0.1 implements the
inbound path (transcription and translation); the synthesis contract for the return path arrives
with v0.2.
"""

from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import AsyncIterator

from .types import AudioFrame, AuthoritativeTranslation, TranscriptSegment


class Transcriber(ABC):
    """Streaming speech-to-text.

    Consumes audio frames and yields transcript segments as they are recognized, emitting interim
    hypotheses followed by stable (``is_final``) segments.
    """

    @abstractmethod
    def transcribe(self, frames: AsyncIterator[AudioFrame]) -> AsyncIterator[TranscriptSegment]:
        """Yield transcript segments for the given audio stream."""
        raise NotImplementedError


class Translator(ABC):
    """Deterministic text translation.

    Produces an :class:`~clearcomm.types.AuthoritativeTranslation`; the source language is taken
    from the segment, and the target is supplied by the caller.
    """

    @abstractmethod
    async def translate(
        self, segment: TranscriptSegment, *, target_language: str
    ) -> AuthoritativeTranslation:
        """Translate a single transcript segment into the target language."""
        raise NotImplementedError
