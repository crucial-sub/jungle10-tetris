"""Seeded PRNG implementation (Mulberry32 algorithm) for deterministic game logic."""

import ctypes


class SeededRandom:
    """Mulberry32 PRNG - matches the JavaScript implementation exactly."""

    def __init__(self, seed: int):
        self.state = seed & 0xFFFFFFFF  # Ensure 32-bit unsigned

    def next(self) -> float:
        """Generate next random float between 0 and 1."""
        self.state = (self.state + 0x6D2B79F5) & 0xFFFFFFFF

        t = self.state
        t = (t ^ (t >> 15)) & 0xFFFFFFFF
        t = self._imul(t, t | 1)
        t = (t ^ (t + self._imul(t ^ (t >> 7), t | 61))) & 0xFFFFFFFF
        result = ((t ^ (t >> 14)) & 0xFFFFFFFF) / 4294967296

        return result

    def next_int(self, max_val: int) -> int:
        """Generate next random integer from 0 to max_val-1."""
        return int(self.next() * max_val)

    @staticmethod
    def _imul(a: int, b: int) -> int:
        """Emulate JavaScript's Math.imul for 32-bit integer multiplication."""
        a = a & 0xFFFFFFFF
        b = b & 0xFFFFFFFF

        # Perform multiplication with proper overflow handling
        result = ctypes.c_int32(a * b).value
        return result & 0xFFFFFFFF
