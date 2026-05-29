"""Tests for the pipeline-stage contracts.

These verify that the abstract contracts hold and that a minimal in-memory implementation can
satisfy them — a smoke test of the seam every real provider will plug into.
"""

from __future__ import annotations

import asyncio
from collections.abc import AsyncIterator

import pytest

from clearcomm.interfaces import Transcriber, Translator
from clearcomm.types import AudioFrame, AuthoritativeTranslation, TranscriptSegment


def test_transcriber_is_abstract() -> None:
    with pytest.raises(TypeError):
        Transcriber()  # type: ignore[abstract]


def test_translator_is_abstract() -> None:
    with pytest.raises(TypeError):
        Translator()  # type: ignore[abstract]


class _EchoTranscriber(Transcriber):
    """Emits one interim then one final segment per frame, echoing a fixed phrase."""

    async def transcribe(
        self, frames: AsyncIterator[AudioFrame]
    ) -> AsyncIterator[TranscriptSegment]:
        async for frame in frames:
            yield TranscriptSegment(
                text="hola",
                is_final=False,
                start=frame.timestamp,
                end=frame.timestamp,
                language="es",
                confidence=0.5,
            )
            yield TranscriptSegment(
                text="hola mundo",
                is_final=True,
                start=frame.timestamp,
                end=frame.timestamp + 1.0,
                language="es",
                confidence=0.9,
            )


class _PrefixTranslator(Translator):
    """Deterministic stand-in that marks where a real engine would translate."""

    async def translate(
        self, segment: TranscriptSegment, *, target_language: str
    ) -> AuthoritativeTranslation:
        return AuthoritativeTranslation(
            text=f"[{target_language}] {segment.text}",
            source=segment,
            source_language=segment.language,
            target_language=target_language,
            engine="prefix",
            confidence=segment.confidence,
        )


async def _one_frame() -> AsyncIterator[AudioFrame]:
    yield AudioFrame(pcm=b"\x00", sample_rate=8000, timestamp=0.0)


def test_minimal_implementations_satisfy_the_contract() -> None:
    async def run() -> list[AuthoritativeTranslation]:
        transcriber = _EchoTranscriber()
        translator = _PrefixTranslator()
        results: list[AuthoritativeTranslation] = []
        async for segment in transcriber.transcribe(_one_frame()):
            if segment.is_final:
                results.append(await translator.translate(segment, target_language="en"))
        return results

    translations = asyncio.run(run())

    assert len(translations) == 1
    assert translations[0].text == "[en] hola mundo"
    assert translations[0].source_language == "es"
    assert translations[0].source.is_final is True


def test_only_final_segments_are_translated() -> None:
    async def run() -> tuple[int, int]:
        transcriber = _EchoTranscriber()
        interim = 0
        final = 0
        async for segment in transcriber.transcribe(_one_frame()):
            if segment.is_final:
                final += 1
            else:
                interim += 1
        return interim, final

    interim, final = asyncio.run(run())
    assert interim == 1
    assert final == 1
