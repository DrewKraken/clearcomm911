"""Self-hosted deterministic translation using Argos Translate (CTranslate2 + OpenNMT).

This is the on-premises authoritative translator: text never leaves the agency network, and the
output is deterministic, so the same source yields the same translation for review. Argos runs on
CTranslate2 — the same inference runtime as the faster-whisper transcriber — and its models carry
permissive licenses suitable for use by public agencies, which the stack constraint in the
architecture requires.

The translation backend is injectable so the adapter's logic — segment-to-translation mapping,
empty-input handling, language wiring — is unit-tested without installing a model or running
inference. The default backend lazily imports Argos so the core package does not depend on it. The
model package for a language pair (e.g. es->en) is a one-time deployment step, installed with
``argospm`` or the ``argostranslate.package`` API; inference is fully offline once it is present.

``confidence`` is deliberately left unset. Argos exposes a per-hypothesis score, but it is a
cumulative, length-dependent log-probability rather than a calibrated, comparable confidence;
surfacing it as one would risk presenting a translation as more certain than it is, which the
translation-safety model forbids. The source segment's own transcription confidence travels on the
result as the available uncertainty signal.
"""

from __future__ import annotations

import asyncio
from typing import Protocol

from ..interfaces import Translator
from ..types import AuthoritativeTranslation, TranscriptSegment

ENGINE = "argostranslate"
"""Recorded on every translation so an audit log identifies the engine that produced it."""


class _TranslateBackend(Protocol):
    """The single translation call this adapter needs, isolated for dependency injection."""

    def translate(self, text: str, from_code: str, to_code: str) -> str: ...


class _ArgosBackend:
    """Default backend: a thin wrapper over Argos's offline translation call."""

    def translate(self, text: str, from_code: str, to_code: str) -> str:
        from argostranslate import translate as argos

        result: str = argos.translate(text, from_code, to_code)
        return result


class ArgosTranslator(Translator):
    """Deterministic ``Translator`` backed by a self-hosted Argos model.

    The source language is taken from each segment; the target is supplied per call. Inference runs
    in a worker thread so a translation never blocks the event loop carrying the live call.
    """

    def __init__(self, *, backend: _TranslateBackend | None = None) -> None:
        self._backend = backend if backend is not None else _ArgosBackend()

    async def translate(
        self, segment: TranscriptSegment, *, target_language: str
    ) -> AuthoritativeTranslation:
        source = segment.text.strip()
        if not source:
            text = ""
        else:
            translated = await asyncio.to_thread(
                self._backend.translate, source, segment.language, target_language
            )
            text = translated.strip()

        return AuthoritativeTranslation(
            text=text,
            source=segment,
            source_language=segment.language,
            target_language=target_language,
            engine=ENGINE,
            confidence=None,
        )
