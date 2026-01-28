from __future__ import annotations

import threading
from collections import deque
from typing import Optional

import numpy as np

try:
    import sounddevice as sd  # type: ignore
except Exception:  # pragma: no cover
    sd = None  # type: ignore


class RingBuffer:
    def __init__(self, capacity: int):
        self.capacity = int(capacity)
        self.buf = np.zeros(self.capacity, dtype=np.float32)
        self.write_idx = 0
        self.size = 0
        self.lock = threading.Lock()

    def write(self, data: np.ndarray) -> None:
        with self.lock:
            n = len(data)
            if n >= self.capacity:
                data = data[-self.capacity :]
                n = len(data)
            end = (self.write_idx + n) % self.capacity
            if self.write_idx + n <= self.capacity:
                self.buf[self.write_idx : self.write_idx + n] = data
            else:
                first = self.capacity - self.write_idx
                self.buf[self.write_idx :] = data[:first]
                self.buf[: end] = data[first:]
            self.write_idx = end
            self.size = min(self.capacity, self.size + n)

    def read_latest(self, n: int) -> np.ndarray:
        with self.lock:
            n = min(n, self.size)
            start = (self.write_idx - n) % self.capacity
            if start + n <= self.capacity:
                return self.buf[start : start + n].copy()
            first = self.capacity - start
            return np.concatenate((self.buf[start:], self.buf[: n - first])).copy()


class AudioInput:
    def __init__(self, samplerate: int = 48000, blocksize: int = 1024, channels: int = 1):
        self.samplerate = samplerate
        self.blocksize = blocksize
        self.channels = channels
        self.stream: Optional[object] = None
        self.buffer = RingBuffer(self.samplerate * 2)  # ~2s

    def start(self) -> None:
        if sd is None or self.stream is not None:
            return

        def callback(indata, frames, time_info, status):  # type: ignore
            if frames <= 0:
                return
            try:
                mono = indata[:, 0].astype(np.float32, copy=False)
                self.buffer.write(mono)
            except Exception:
                pass

        try:
            self.stream = sd.InputStream(
                samplerate=self.samplerate,
                channels=self.channels,
                blocksize=self.blocksize,
                callback=callback,
            )
            self.stream.start()
        except Exception:
            self.stream = None

    def stop(self) -> None:
        if self.stream is not None:
            try:
                self.stream.stop()
                self.stream.close()
            except Exception:
                pass
            self.stream = None

    def get_latest(self, n_samples: int) -> np.ndarray:
        return self.buffer.read_latest(n_samples)


