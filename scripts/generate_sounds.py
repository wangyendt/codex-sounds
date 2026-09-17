#!/usr/bin/env python3
"""Rebuild the original, quiet PCM WAV cues using only Python's standard library."""
import math
from pathlib import Path
import struct
import wave

RATE = 44100
PATTERNS = {
    "complete": [(880, .16), (1174.66, .24)],
    "input": [(659.25, .16), (0, .10), (659.25, .20)],
    "approval": [(440, .14), (0, .07), (554.37, .14), (0, .07), (659.25, .20)],
}


def render(pattern):
    result = bytearray()
    for frequency, seconds in pattern:
        length = round(RATE * seconds)
        for i in range(length):
            # Fade both edges to avoid clicks. Peak amplitude is 20% of full scale.
            envelope = min(1.0, i / (RATE * .015), (length - 1 - i) / (RATE * .05))
            value = .2 * envelope * math.sin(2 * math.pi * frequency * i / RATE)
            result.extend(struct.pack("<h", round(32767 * value)))
    return bytes(result)


def main():
    output = Path(__file__).resolve().parents[1] / "assets"
    output.mkdir(exist_ok=True)
    for name, pattern in PATTERNS.items():
        with wave.open(str(output / (name + ".wav")), "wb") as wav:
            wav.setnchannels(1)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(render(pattern))


if __name__ == "__main__":
    main()
