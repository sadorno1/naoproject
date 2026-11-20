"""Bounded constant-gain adjustment of 16-bit PCM WAV speech (standard library only)."""
from array import array
import io
import math
import sys
import wave


def boost_wav(data, target_rms_dbfs=-18.0, peak_dbfs=-1.0, max_gain_db=12.0):
    if not all(math.isfinite(v) for v in (target_rms_dbfs, peak_dbfs, max_gain_db)):
        raise ValueError("Audio levels must be finite")
    if not target_rms_dbfs <= peak_dbfs <= 0 or max_gain_db < 0:
        raise ValueError("Require target RMS <= peak <= 0 dBFS and gain >= 0")
    with wave.open(io.BytesIO(data), "rb") as source:
        params = source.getparams()
        if source.getsampwidth() != 2 or source.getcomptype() != "NONE":
            raise ValueError("Speech loudness adjustment requires uncompressed 16-bit PCM WAV")
        samples = array("h", source.readframes(source.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    if not samples:
        return data
    peak = max(abs(v) for v in samples)
    rms = math.sqrt(sum(v * v for v in samples) / len(samples))
    #Do not amplify silence or near-silent noise below -60 dBFS.
    if rms < 32768 * 10 ** (-60 / 20):
        return data
    gain = min(32767 * 10 ** (peak_dbfs / 20) / peak,
               max(1.0, min(10 ** (max_gain_db / 20),
                            32768 * 10 ** (target_rms_dbfs / 20) / rms)))
    adjusted = array("h", (max(-32768, min(32767, round(v * gain))) for v in samples))
    if sys.byteorder != "little":
        adjusted.byteswap()
    output = io.BytesIO()
    with wave.open(output, "wb") as dest:
        dest.setparams(params)
        dest.writeframes(adjusted.tobytes())
    return output.getvalue()
