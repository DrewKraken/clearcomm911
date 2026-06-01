"""Tests for the inbound pipeline.

Scripted fakes stand in for the transcriber and translator so these exercise the orchestration —
which segments are translated, how a failure is handled, event ordering — without any model.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

from clearcomm.interfaces import Transcriber, Translator
from clearcomm.pipeline import (
    CommittedTranslation,
    InboundPipeline,
    InterimTranscript,
    PipelineEvent,
    TranslationUnavailable,
)
from clearcomm.types import AudioFrame, AuthoritativeTranslation, TranscriptSegment


def _seg(text: str, *, final: bool, language: str = "es") -> TranscriptSegment:
    return TranscriptSegment(
        text=text, is_final=final, start=0.0, end=1.0, language=language, confidence=0.9
    )


class _ScriptedTranscriber(Transcriber):
    """Yields a fixed list of segments, ignoring the audio it is handed."""

    def __init__(self, segments: list[TranscriptSegment]) -> None:
        self._segments = segments

    async def transcribe(
        self, frames: AsyncIterator[AudioFrame]
    ) -> AsyncIterator[TranscriptSegment]:
        for segment in self._segments:
            yield segment


class _PrefixTranslator(Translator):
    """Records the calls it receives and echoes the source with a target-language prefix."""

    def __init__(self) -> None:
        self.calls: list[tuple[str, str]] = []

    async def translate(
        self, segment: TranscriptSegment, *, target_language: str
    ) -> AuthoritativeTranslation:
        self.calls.append((segment.text, target_language))
        return AuthoritativeTranslation(
            text=f"[{target_language}] {segment.text}",
            source=segment,
            source_language=segment.language,
            target_language=target_language,
            engine="prefix",
            confidence=None,
        )


class _FailingTranslator(Translator):
    async def translate(
        self, segment: TranscriptSegment, *, target_language: str
    ) -> AuthoritativeTranslation:
        raise RuntimeError("engine down")


async def _frames(*frames: AudioFrame) -> AsyncIterator[AudioFrame]:
    for frame in frames:
        yield frame


def _run(
    transcriber: Transcriber, translator: Translator, target: str = "en"
) -> list[PipelineEvent]:
    pipeline = InboundPipeline(transcriber, translator, target_language=target)

    async def collect() -> list[PipelineEvent]:
        return [event async for event in pipeline.run(_frames())]

    return asyncio.run(collect())


def test_interim_segments_are_forwarded_but_not_translated() -> None:
    translator = _PrefixTranslator()
    events = _run(
        _ScriptedTranscriber([_seg("no pue", final=False), _seg("no puedo respirar", final=True)]),
        translator,
    )

    first, second = events
    assert isinstance(first, InterimTranscript)
    assert first.segment.text == "no pue"
    assert isinstance(second, CommittedTranslation)
    assert second.translation.text == "[en] no puedo respirar"
    assert translator.calls == [("no puedo respirar", "en")]


def test_translator_failure_degrades_the_turn_without_dropping_the_stream() -> None:
    events = _run(
        _ScriptedTranscriber([_seg("hay fuego", final=True), _seg("en la cocina", final=True)]),
        _FailingTranslator(),
    )

    assert len(events) == 2
    first = events[0]
    assert isinstance(first, TranslationUnavailable)
    assert first.segment.text == "hay fuego"
    assert first.reason == "engine down"
    assert isinstance(events[1], TranslationUnavailable)


def test_target_language_is_threaded_to_the_translator() -> None:
    translator = _PrefixTranslator()
    _run(_ScriptedTranscriber([_seg("hola", final=True)]), translator, target="en")
    assert translator.calls == [("hola", "en")]


def test_event_order_is_preserved() -> None:
    events = _run(
        _ScriptedTranscriber(
            [_seg("a", final=False), _seg("b", final=True), _seg("c", final=False)]
        ),
        _PrefixTranslator(),
    )
    assert [type(e).__name__ for e in events] == [
        "InterimTranscript",
        "CommittedTranslation",
        "InterimTranscript",
    ]


def test_empty_transcript_yields_no_events() -> None:
    assert _run(_ScriptedTranscriber([]), _PrefixTranslator()) == []
