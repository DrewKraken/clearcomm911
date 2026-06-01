"""Tests for the Argos translator adapter.

A fake backend stands in for Argos so these exercise the adapter's logic — segment mapping,
empty-input handling, language wiring — without installing a model or running inference.
"""

from __future__ import annotations

import asyncio

from clearcomm.translators.argos import ENGINE, ArgosTranslator
from clearcomm.types import AuthoritativeTranslation, TranscriptSegment


class _FakeBackend:
    def __init__(self, output: str = "I can't breathe") -> None:
        self._output = output
        self.calls: list[tuple[str, str, str]] = []

    def translate(self, text: str, from_code: str, to_code: str) -> str:
        self.calls.append((text, from_code, to_code))
        return self._output


def _segment(text: str = "no puedo respirar", language: str = "es") -> TranscriptSegment:
    return TranscriptSegment(
        text=text, is_final=True, start=0.0, end=1.4, language=language, confidence=0.9
    )


def _translate(
    translator: ArgosTranslator, segment: TranscriptSegment, target: str = "en"
) -> AuthoritativeTranslation:
    return asyncio.run(translator.translate(segment, target_language=target))


def test_translates_segment_into_authoritative_translation() -> None:
    result = _translate(ArgosTranslator(backend=_FakeBackend("I can't breathe")), _segment())

    assert result.text == "I can't breathe"
    assert result.source_language == "es"
    assert result.target_language == "en"
    assert result.engine == ENGINE


def test_passes_source_text_and_language_pair_to_backend() -> None:
    backend = _FakeBackend()
    _translate(ArgosTranslator(backend=backend), _segment(language="es"), target="en")
    assert backend.calls == [("no puedo respirar", "es", "en")]


def test_strips_whitespace_from_translation() -> None:
    result = _translate(ArgosTranslator(backend=_FakeBackend("  help is on the way  ")), _segment())
    assert result.text == "help is on the way"


def test_empty_segment_is_not_sent_to_backend() -> None:
    backend = _FakeBackend()
    result = _translate(ArgosTranslator(backend=backend), _segment(text="   "))
    assert result.text == ""
    assert backend.calls == []


def test_confidence_is_unset() -> None:
    result = _translate(ArgosTranslator(backend=_FakeBackend()), _segment())
    assert result.confidence is None


def test_source_segment_is_retained_as_ground_truth() -> None:
    segment = _segment()
    result = _translate(ArgosTranslator(backend=_FakeBackend()), segment)
    assert result.source is segment
