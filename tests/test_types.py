"""Tests for the core data types and their invariants."""

from __future__ import annotations

import dataclasses

import pytest

from clearcomm.types import AudioFrame, AuthoritativeTranslation, TranscriptSegment


def _segment(confidence: float = 0.9, start: float = 0.0, end: float = 1.0) -> TranscriptSegment:
    return TranscriptSegment(
        text="no puedo respirar",
        is_final=True,
        start=start,
        end=end,
        language="es",
        confidence=confidence,
    )


def test_audio_frame_is_immutable() -> None:
    frame = AudioFrame(pcm=b"\x00\x01", sample_rate=8000, timestamp=0.0)
    with pytest.raises(dataclasses.FrozenInstanceError):
        frame.sample_rate = 16000  # type: ignore[misc]


def test_segment_accepts_valid_confidence() -> None:
    assert _segment(confidence=0.0).confidence == 0.0
    assert _segment(confidence=1.0).confidence == 1.0


@pytest.mark.parametrize("confidence", [-0.1, 1.1])
def test_segment_rejects_out_of_range_confidence(confidence: float) -> None:
    with pytest.raises(ValueError, match="confidence"):
        _segment(confidence=confidence)


def test_segment_rejects_end_before_start() -> None:
    with pytest.raises(ValueError, match="precedes start"):
        _segment(start=2.0, end=1.0)


def test_translation_retains_source_segment() -> None:
    segment = _segment()
    translation = AuthoritativeTranslation(
        text="I can't breathe",
        source=segment,
        source_language="es",
        target_language="en",
        engine="test",
        confidence=0.95,
    )
    assert translation.source is segment
    assert translation.source.text == "no puedo respirar"


def test_translation_allows_unknown_confidence() -> None:
    translation = AuthoritativeTranslation(
        text="I can't breathe",
        source=_segment(),
        source_language="es",
        target_language="en",
        engine="test",
    )
    assert translation.confidence is None


def test_translation_rejects_out_of_range_confidence() -> None:
    with pytest.raises(ValueError, match="confidence"):
        AuthoritativeTranslation(
            text="I can't breathe",
            source=_segment(),
            source_language="es",
            target_language="en",
            engine="test",
            confidence=1.5,
        )
