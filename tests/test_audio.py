"""Tests for telephony-band audio simulation."""

from __future__ import annotations

import numpy as np

from clearcomm.audio import (
    NARROWBAND_RATE,
    mu_law_decode,
    mu_law_encode,
    to_telephony_band,
)


def _tone(freq_hz: float, rate: int, seconds: float = 0.25) -> np.ndarray:
    t = np.linspace(0.0, seconds, int(rate * seconds), endpoint=False)
    return (0.5 * np.sin(2 * np.pi * freq_hz * t)).astype(np.float32)


def test_mu_law_codes_are_bytes() -> None:
    codes = mu_law_encode(_tone(300, 16000))
    assert codes.dtype == np.uint8
    assert codes.min() >= 0 and codes.max() <= 255


def test_mu_law_roundtrip_preserves_signal_shape_and_range() -> None:
    signal = _tone(300, 16000)
    recovered = mu_law_decode(mu_law_encode(signal))
    assert recovered.shape == signal.shape
    assert np.all(np.abs(recovered) <= 1.0)
    # Companding is lossy but should track the original closely.
    assert np.corrcoef(signal, recovered)[0, 1] > 0.99


def test_mu_law_preserves_silence() -> None:
    silence = np.zeros(160, dtype=np.float32)
    recovered = mu_law_decode(mu_law_encode(silence))
    assert np.allclose(recovered, 0.0, atol=1e-2)


def test_telephony_band_keeps_voiceband_tone() -> None:
    rate = 16000
    voiceband = _tone(300, rate)
    degraded = to_telephony_band(voiceband, rate)
    assert degraded.dtype == np.float32
    retained = float(np.sqrt(np.mean(degraded**2)) / np.sqrt(np.mean(voiceband**2)))
    assert retained > 0.5


def test_telephony_band_removes_energy_above_nyquist() -> None:
    rate = 16000
    above_band = _tone(6000, rate)  # above the 4 kHz narrowband Nyquist limit
    degraded = to_telephony_band(above_band, rate)
    retained = float(np.sqrt(np.mean(degraded**2)) / np.sqrt(np.mean(above_band**2)))
    assert retained < 0.1


def test_narrowband_rate_is_g711() -> None:
    assert NARROWBAND_RATE == 8000
