"""Translation-quality benchmark for the authoritative translator.

Runs a :class:`~clearcomm.interfaces.Translator` over source-language lines and scores the output
against reference translations with chrF (primary) and BLEU. chrF leads because it is more reliable
than BLEU on the short, often fragmentary utterances typical of emergency speech.

This is a local tool, not a CI test: it needs an installed translation model and a parallel
reference set. Real-call text is validated privately during a pilot and is never committed to this
repository.

Usage::

    python -m clearcomm.translation_benchmark --source es.txt --reference en.txt \\
        --source-language es --target-language en
"""

from __future__ import annotations

import argparse
import asyncio
from dataclasses import dataclass
from pathlib import Path

from .interfaces import Translator
from .translators.argos import ArgosTranslator
from .types import TranscriptSegment


def _segment(text: str, language: str) -> TranscriptSegment:
    return TranscriptSegment(
        text=text, is_final=True, start=0.0, end=0.0, language=language, confidence=1.0
    )


def translate_lines(
    translator: Translator, lines: list[str], *, source_language: str, target_language: str
) -> list[str]:
    """Translate each source line and return the translated text in the same order."""

    async def collect() -> list[str]:
        out: list[str] = []
        for line in lines:
            translation = await translator.translate(
                _segment(line, source_language), target_language=target_language
            )
            out.append(translation.text)
        return out

    return asyncio.run(collect())


@dataclass(frozen=True)
class TranslationBenchmarkResult:
    chrf: float
    bleu: float


def _read_lines(path: Path) -> list[str]:
    """Read a file into stripped lines, keeping blanks so source and reference stay aligned.

    Dropping blank lines independently from each file would shift every later line out of
    correspondence with its translation, silently scoring hypotheses against the wrong references.
    The count check in :func:`run_benchmark` then catches a genuine length mismatch loudly.
    """
    return [line.strip() for line in path.read_text(encoding="utf-8").splitlines()]


def run_benchmark(
    source_path: Path, reference_path: Path, *, source_language: str, target_language: str
) -> TranslationBenchmarkResult:
    import sacrebleu

    sources = _read_lines(source_path)
    references = _read_lines(reference_path)
    if len(sources) != len(references):
        raise ValueError(f"source has {len(sources)} lines but reference has {len(references)}")

    hypotheses = translate_lines(
        ArgosTranslator(), sources, source_language=source_language, target_language=target_language
    )

    chrf = sacrebleu.corpus_chrf(hypotheses, [references]).score
    bleu = sacrebleu.corpus_bleu(hypotheses, [references]).score
    return TranslationBenchmarkResult(chrf=float(chrf), bleu=float(bleu))


def main() -> None:
    parser = argparse.ArgumentParser(description="Translation-quality benchmark (chrF and BLEU).")
    parser.add_argument("--source", type=Path, required=True, help="Source-language lines.")
    parser.add_argument("--reference", type=Path, required=True, help="Reference translations.")
    parser.add_argument("--source-language", default="es", help="Source language code.")
    parser.add_argument("--target-language", default="en", help="Target language code.")
    args = parser.parse_args()

    result = run_benchmark(
        args.source,
        args.reference,
        source_language=args.source_language,
        target_language=args.target_language,
    )

    print(f"chrF:  {result.chrf:.2f}")
    print(f"BLEU:  {result.bleu:.2f}")


if __name__ == "__main__":
    main()
