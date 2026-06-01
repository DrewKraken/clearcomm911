"""Tests for the translation benchmark's pure glue.

The full benchmark needs an installed model and sacrebleu; these cover the line-translation helper
and the result type that CI can verify with a fake translator.
"""

from __future__ import annotations

from pathlib import Path

from clearcomm.interfaces import Translator
from clearcomm.translation_benchmark import (
    TranslationBenchmarkResult,
    _read_lines,
    translate_lines,
)
from clearcomm.types import AuthoritativeTranslation, TranscriptSegment


class _UppercaseTranslator(Translator):
    """Stand-in that records the language pair it is asked for and echoes the source upper-cased."""

    def __init__(self) -> None:
        self.pairs: list[tuple[str, str]] = []

    async def translate(
        self, segment: TranscriptSegment, *, target_language: str
    ) -> AuthoritativeTranslation:
        self.pairs.append((segment.language, target_language))
        return AuthoritativeTranslation(
            text=segment.text.upper(),
            source=segment,
            source_language=segment.language,
            target_language=target_language,
            engine="fake",
            confidence=None,
        )


def test_translate_lines_preserves_order_and_count() -> None:
    out = translate_lines(
        _UppercaseTranslator(),
        ["hola", "mundo", "ayuda"],
        source_language="es",
        target_language="en",
    )
    assert out == ["HOLA", "MUNDO", "AYUDA"]


def test_translate_lines_threads_the_language_pair_through() -> None:
    translator = _UppercaseTranslator()
    translate_lines(translator, ["hola"], source_language="es", target_language="en")
    assert translator.pairs == [("es", "en")]


def test_translate_lines_handles_empty_input() -> None:
    out = translate_lines(_UppercaseTranslator(), [], source_language="es", target_language="en")
    assert out == []


def test_result_holds_scores() -> None:
    result = TranslationBenchmarkResult(chrf=62.5, bleu=41.0)
    assert result.chrf == 62.5
    assert result.bleu == 41.0


def test_read_lines_keeps_blank_lines_so_parallel_files_stay_aligned(tmp_path: Path) -> None:
    path = tmp_path / "lines.txt"
    path.write_text("first\n\nthird\n", encoding="utf-8")
    assert _read_lines(path) == ["first", "", "third"]
