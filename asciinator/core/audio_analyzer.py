from __future__ import annotations

import numpy as np


class SixBandAnalyzer:
    def __init__(self, samplerate: int = 48000, window_ms: float = 23.0):
        self.sr = samplerate
        self.win = int(self.sr * window_ms / 1000.0)
        if self.win % 2 == 1:
            self.win += 1
        self.hop = self.win // 2
        self.window = np.hanning(self.win).astype(np.float32)
        self.band_edges = np.array([0, 60, 150, 400, 1000, 2400, 15000], dtype=np.float32)
        self.eps = 1e-9
        self.baseline = np.zeros(6, dtype=np.float32)
        self.smoothed = np.zeros(6, dtype=np.float32)
        self.alpha_base = 0.99
        self.alpha_attack = 0.35
        self.alpha_release = 0.1
        self.noise_gate = 0.02

    def _bands_from_fft(self, mag: np.ndarray) -> np.ndarray:
        freqs = np.linspace(0, self.sr / 2, len(mag), dtype=np.float32)
        energies = np.zeros(6, dtype=np.float32)
        for i in range(6):
            lo, hi = self.band_edges[i], self.band_edges[i + 1]
            mask = (freqs >= lo) & (freqs < hi)
            if np.any(mask):
                energies[i] = float(np.mean(mag[mask]))
        return energies

    def process(self, mono: np.ndarray) -> np.ndarray:
        if mono.size < self.win:
            buf = np.zeros(self.win, dtype=np.float32)
            buf[-mono.size :] = mono.astype(np.float32, copy=False)
        else:
            buf = mono[-self.win :].astype(np.float32, copy=False)
        xw = buf * self.window
        fft = np.fft.rfft(xw)
        mag = np.abs(fft).astype(np.float32)
        bands = self._bands_from_fft(mag)
        self.baseline = self.alpha_base * self.baseline + (1 - self.alpha_base) * bands
        norm = np.maximum(0.0, bands - self.baseline)
        knee = 0.1
        norm = norm / (norm + knee + self.eps)
        norm[norm < self.noise_gate] = 0.0
        out = np.empty_like(norm)
        for i in range(6):
            a = self.alpha_attack if norm[i] > self.smoothed[i] else self.alpha_release
            self.smoothed[i] = a * self.smoothed[i] + (1 - a) * norm[i]
            out[i] = self.smoothed[i]
        return out


