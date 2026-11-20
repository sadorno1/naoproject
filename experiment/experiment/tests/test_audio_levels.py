"""Offline audio tests; no API or robot required."""
from array import array
import io
from pathlib import Path
import sys
import unittest
from unittest.mock import Mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_levels import boost_wav
from speech import TTS


def wav_bytes(values):
    samples = array("h", values)
    if sys.byteorder != "little":
        samples.byteswap()
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(1)
        f.setsampwidth(2)
        f.setframerate(24000)
        f.writeframes(samples.tobytes())
    return out.getvalue()


def read_wav(data):
    with wave.open(io.BytesIO(data), "rb") as f:
        params = f.getparams()
        samples = array("h", f.readframes(f.getnframes()))
    if sys.byteorder != "little":
        samples.byteswap()
    return params, samples


class AudioTests(unittest.TestCase):
    def test_quiet_speech_boost_is_capped_and_preserves_timing(self):
        original = wav_bytes([1000, -1000] * 100)
        params, values = read_wav(boost_wav(original))
        self.assertEqual(params, read_wav(original)[0])
        self.assertGreater(max(values), 1000)
        self.assertLessEqual(max(values), 3982)  #12 dB cap

    def test_peak_ceiling_prevents_clipping_with_large_transient(self):
        original = wav_bytes([1000, -1000] * 100 + [32767, -32768])
        _, values = read_wav(boost_wav(original))
        self.assertLessEqual(max(abs(v) for v in values), 29204)  #-1 dBFS
        self.assertGreater(min(values), -32768)

    def test_silence_and_near_silence_are_not_amplified(self):
        for values in ([], [0] * 100, [1, -1] * 100):
            original = wav_bytes(values)
            self.assertEqual(boost_wav(original), original)

    def test_cache_changes_when_gain_settings_change(self):
        a = TTS(Mock(), max_gain_db=6)
        b = TTS(Mock(), max_gain_db=12)
        self.assertNotEqual(a.cache_path("hello"), b.cache_path("hello"))

    def test_mp3_requires_normalization_disabled(self):
        with self.assertRaises(ValueError):
            TTS(Mock(), fmt="mp3", normalize=True)
        self.assertEqual(TTS(Mock(), fmt="mp3", normalize=False).format, "mp3")

    def test_synthesis_adjusts_audio_before_returning(self):
        import tempfile
        client = Mock()
        source = wav_bytes([1000, -1000] * 100)
        response = client.audio.speech.with_streaming_response.create.return_value.__enter__ = Mock()
        #A context manager response that yields the WAV in separate chunks.
        stream = Mock()
        stream.iter_bytes.return_value = [source[:30], source[30:]]
        response.return_value = stream
        client.audio.speech.with_streaming_response.create.return_value.__exit__ = Mock(return_value=False)
        first = Mock()
        with tempfile.TemporaryDirectory(dir=Path(__file__).parent) as folder:
            path = Path(folder) / "speech.wav"
            TTS(client).synthesize("hello", path, first)
            self.assertGreater(max(read_wav(path.read_bytes())[1]), 1000)
        first.assert_called_once()
        self.assertEqual(client.audio.speech.with_streaming_response.create.call_args.kwargs["response_format"], "wav")


if __name__ == "__main__":
    unittest.main()
