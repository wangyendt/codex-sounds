#!/usr/bin/env python3
"""Rebuild the selected C / minimal-electronic cues using only the standard library."""
import math
from pathlib import Path
import struct
import wave

RATE = 44100
DURATION = 1.18
PATTERNS = {
    'complete': [(0, 72, .70), (.10, 76, .60), (.21, 79, .73)],
    'input': [(0, 74, .74), (.23, 81, .58)],
    'approval': [(0, 69, .76), (.14, 76, .62), (.28, 81, .66)],
}


def render(kind):
    """Stereo PCM16: rounded FM plucks, gentle pitch settling, short reflections."""
    mono = [0.0] * round(RATE * DURATION)
    voice_duration = .66
    for start, midi, level in PATTERNS[kind]:
        freq = 440 * 2 ** ((midi + 2 - 69) / 12)
        offset = round(start * RATE)
        for i in range(round(RATE * voice_duration)):
            t = i / RATE
            phase = 2 * math.pi * freq * (t + .008 * .014 * (1 - math.exp(-t / .014)))
            value = math.sin(phase + .65 * math.exp(-t / .050) * math.sin(2 * math.pi * freq * 2 * t)) * math.exp(-t / .20)
            value += .14 * math.sin(2 * math.pi * freq * .5 * t) * math.exp(-t / .24)
            value += .055 * math.sin(2 * math.pi * freq * 1.003 * t) * math.exp(-t / .20)
            attack = 1 - math.exp(-t / .009)
            end_fade = min(1, max(0, (voice_duration - t) / .085)) ** 2
            mono[offset + i] += value * attack * end_fade * level
    channels = []
    wet = .085
    for side in range(2):
        channel = mono.copy()
        for delay, gain in [(.043 + side * .010, wet), (.091 - side * .008, wet * .50), (.157 + side * .012, wet * .23)]:
            d = round(delay * RATE)
            for i in range(d, len(channel)):
                channel[i] += mono[i - d] * gain
        average = sum(channel) / len(channel)
        channels.append([value - average for value in channel])
    active = round(.85 * RATE)
    rms = math.sqrt(sum(x * x for channel in channels for x in channel[:active]) / (2 * active))
    peak = max(abs(x) for channel in channels for x in channel)
    gain = min(.063 / max(rms, 1e-9), .27 / max(peak, 1e-9))
    fade = round(.025 * RATE)
    result = bytearray()
    for i in range(len(mono)):
        edge = min(1, i / (fade - 1), (len(mono) - 1 - i) / (fade - 1))
        for channel in channels:
            result.extend(struct.pack('<h', round(channel[i] * gain * edge * 32767)))
    return bytes(result)


def main():
    output = Path(__file__).resolve().parents[1] / 'assets'
    output.mkdir(exist_ok=True)
    for kind in PATTERNS:
        with wave.open(str(output / (kind + '.wav')), 'wb') as wav:
            wav.setnchannels(2)
            wav.setsampwidth(2)
            wav.setframerate(RATE)
            wav.writeframes(render(kind))


if __name__ == '__main__':
    main()
