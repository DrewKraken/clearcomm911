"""Telephony-band audio simulation.

Real 911 audio arrives narrowband: 8 kHz, G.711 μ-law companded, and lossy. Speech-to-text models
are trained largely on wideband audio, so accuracy must be measured on telephony-band audio rather
than clean recordings. This module degrades clean audio to approximate phone-band conditions so the
benchmark reflects the real operating environment.

The μ-law transform here is the ideal companding curve (μ=255) with 8-bit quantization — a faithful
model of the G.711 companding and its quantization noise. The dominant accuracy effect, the 8 kHz
band limit, is applied by resampling through the narrowband rate.
"""

from __future__ import annotations

import numpy as np
import numpy.typing as npt
from scipy.signal import resample_poly

MU = 255.0
"""μ-law companding parameter for G.711 (North American telephony)."""

NARROWBAND_RATE = 8000
"""The sample rate of G.711 telephony audio, in Hz."""


def mu_law_encode(samples: npt.NDArray[np.float32]) -> npt.NDArray[np.uint8]:
    """Companding-encode float PCM in [-1.0, 1.0] to 8-bit μ-law codes."""
    clipped = np.clip(samples, -1.0, 1.0)
    magnitude = np.log1p(MU * np.abs(clipped)) / np.log1p(MU)
    companded = np.sign(clipped) * magnitude
    codes: npt.NDArray[np.uint8] = np.round((companded + 1.0) * 127.5).astype(np.uint8)
    return codes


def mu_law_decode(codes: npt.NDArray[np.uint8]) -> npt.NDArray[np.float32]:
    """Expand 8-bit μ-law codes back to float PCM in [-1.0, 1.0]."""
    companded = codes.astype(np.float32) / 127.5 - 1.0
    magnitude = np.expm1(np.abs(companded) * np.log1p(MU)) / MU
    samples: npt.NDArray[np.float32] = (np.sign(companded) * magnitude).astype(np.float32)
    return samples


def resample(
    samples: npt.NDArray[np.float32], orig_rate: int, target_rate: int
) -> npt.NDArray[np.float32]:
    """Resample a mono signal between sample rates."""
    if orig_rate == target_rate:
        return samples
    resampled = resample_poly(samples, target_rate, orig_rate)
    return np.asarray(resampled, dtype=np.float32)


def to_telephony_band(samples: npt.NDArray[np.float32], rate: int) -> npt.NDArray[np.float32]:
    """Degrade wideband audio to approximate an 8 kHz G.711 μ-law phone call.

    Returns audio at the original ``rate`` (band-limited and μ-law-distorted) so it can feed a model
    that expects its native input rate.
    """
    narrowband = resample(samples, rate, NARROWBAND_RATE)
    companded = mu_law_decode(mu_law_encode(narrowband))
    return resample(companded, NARROWBAND_RATE, rate)
