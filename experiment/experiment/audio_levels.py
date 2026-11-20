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
        payload = source.readframes(source.getnframes())
        if len(payload) % (params.nchannels * params.sampwidth):
            raise ValueError("Speech WAV ends with an incomplete PCM frame")
        samples = array("h", payload)
        #Streamed WAV headers may advertise UINT32_MAX instead of the actual data size.
        #Only the downloaded PCM frames determine the length of our finalized output.
        params = params._replace(nframes=len(samples) // params.nchannels)
    if sys.byteorder != "little":
        samples.byteswap()
    peak = max((abs(v) for v in samples), default=0)
    rms = math.sqrt(sum(v * v for v in samples) / len(samples)) if samples else 0
    #Do not amplify silence or near-silent noise below -60 dBFS.
    gain = 1.0
    if rms >= 32768 * 10 ** (-60 / 20):
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
