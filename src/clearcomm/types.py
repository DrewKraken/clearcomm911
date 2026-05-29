"""Core data types passed between pipeline stages.

The naming of ``AuthoritativeTranslation`` is deliberate. Only deterministic machine translation
produces this type, and only this type is permitted to drive the dispatcher display and (in later
versions) spoken output. When an optional context model is added, its output will be a distinct
type that those paths cannot accept — making "a non-authoritative translation reaches the caller"
a type error rather than a runtime risk.
"""

from __future__ import annotations

from dataclasses import dataclass


@dataclass(frozen=True, slots=True)
class AudioFrame:
    """A chunk of raw PCM audio with the metadata needed to place it in the stream."""

    pcm: bytes
    sample_rate: int
    timestamp: float
    """Seconds since the start of the stream."""


@dataclass(frozen=True, slots=True)
class TranscriptSegment:
    """A unit of recognized speech.

    ``is_final`` distinguishes interim hypotheses (shown to the dispatcher as they form, never
    translated) from stable segments (which trigger translation). ``confidence`` is normalized to
    the range ``0.0`` to ``1.0`` so the console can flag low-confidence speech regardless of engine.
    """

    text: str
    is_final: bool
    start: float
    end: float
    language: str
    confidence: float

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
        if self.end < self.start:
            raise ValueError(f"end ({self.end}) precedes start ({self.start})")


@dataclass(frozen=True, slots=True)
class AuthoritativeTranslation:
    """A translation that may be presented to the dispatcher as authoritative.

    Produced only by a deterministic translator. ``source`` retains the originating segment so the
    caller's own words remain available as ground truth.
    """

    text: str
    source: TranscriptSegment
    source_language: str
    target_language: str
    engine: str
    confidence: float | None = None

    def __post_init__(self) -> None:
        if self.confidence is not None and not 0.0 <= self.confidence <= 1.0:
            raise ValueError(f"confidence must be in [0.0, 1.0], got {self.confidence}")
