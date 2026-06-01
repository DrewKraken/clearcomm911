"""Inbound-path orchestration: caller audio to dispatcher-facing transcript and translation.

This wires the two inbound stages — :class:`~clearcomm.interfaces.Transcriber` and
:class:`~clearcomm.interfaces.Translator` — into one streaming flow over those same interfaces, so
the concrete providers (cloud or self-hosted) are selected by configuration, not chosen here.

The pipeline encodes two architecture rules in its structure rather than by convention:

- *Interim transcript is shown, never translated.* Only stable (``is_final``) segments reach the
  translator; interim hypotheses are forwarded for immediate display and nothing more. This is what
  keeps committed translations from flickering and rewriting themselves while speech is still
  forming.
- *A translator failure degrades the turn; it does not drop the stream.* If translation raises, the
  pipeline emits the committed source transcript with an explicit "unavailable" marker instead of
  ending the stream or — worse — presenting nothing. This is the floor of the reliability model;
  provider failover sits above it and arrives later.

The output is a discriminated stream of events the dispatcher console renders directly: interim
transcript as it streams, committed translations once stable, and a clear marker when a turn could
not be translated.
"""

from __future__ import annotations

from collections.abc import AsyncIterator
from dataclasses import dataclass

from .interfaces import Transcriber, Translator
from .types import AudioFrame, AuthoritativeTranslation, TranscriptSegment


@dataclass(frozen=True, slots=True)
class InterimTranscript:
    """An unstable hypothesis, shown to the dispatcher as it forms and never translated."""

    segment: TranscriptSegment


@dataclass(frozen=True, slots=True)
class CommittedTranslation:
    """A stable segment and its authoritative translation, ready for the dispatcher to act on."""

    segment: TranscriptSegment
    translation: AuthoritativeTranslation


@dataclass(frozen=True, slots=True)
class TranslationUnavailable:
    """A stable segment whose translation failed; its source stands in as ground truth."""

    segment: TranscriptSegment
    reason: str


PipelineEvent = InterimTranscript | CommittedTranslation | TranslationUnavailable


class InboundPipeline:
    """Streams caller audio through transcription and translation into console-ready events."""

    def __init__(
        self, transcriber: Transcriber, translator: Translator, *, target_language: str
    ) -> None:
        self._transcriber = transcriber
        self._translator = translator
        self._target_language = target_language

    async def run(self, frames: AsyncIterator[AudioFrame]) -> AsyncIterator[PipelineEvent]:
        async for segment in self._transcriber.transcribe(frames):
            if not segment.is_final:
                yield InterimTranscript(segment)
                continue
            yield await self._translate(segment)

    async def _translate(self, segment: TranscriptSegment) -> PipelineEvent:
        try:
            translation = await self._translator.translate(
                segment, target_language=self._target_language
            )
        except Exception as error:
            return TranslationUnavailable(segment, reason=str(error))
        return CommittedTranslation(segment, translation)
