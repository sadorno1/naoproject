"""Offline audio tests; no API or robot required."""
from array import array
import io
from pathlib import Path
import sys
import struct
import unittest
from unittest.mock import Mock
import wave

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from audio_levels import boost_wav
from speech import TTS


def wav_bytes(values, channels=1):
    samples = array("h", values)
    if sys.byteorder != "little":
        samples.byteswap()
    out = io.BytesIO()
    with wave.open(out, "wb") as f:
        f.setnchannels(channels)
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
    def test_streamed_stereo_preserves_channels_and_actual_frame_count(self):
        streamed = bytearray(wav_bytes([1000, -1000, 500, -500] * 50, channels=2))
        struct.pack_into("<I", streamed, 4, 0xffffffff)
        struct.pack_into("<I", streamed, 40, 0xffffffff)
        params, samples = read_wav(boost_wav(bytes(streamed)))
        self.assertEqual(params.nchannels, 2)
        self.assertEqual(params.framerate, 24000)
        self.assertEqual(params.nframes, 100)
        self.assertEqual(len(samples), 200)

    def test_streamed_wav_placeholder_lengths_are_replaced_with_actual_lengths(self):
        #Streaming encoders can put UINT32_MAX in RIFF/data sizes until length is known.
        for values in ([1000, -1000] * 100, [0] * 100, []):
            with self.subTest(sample_count=len(values)):
                streamed = bytearray(wav_bytes(values))
                struct.pack_into("<I", streamed, 4, 0xffffffff)
                struct.pack_into("<I", streamed, 40, 0xffffffff)
                result = boost_wav(bytes(streamed))
                params, samples = read_wav(result)
                self.assertEqual(params.nframes, len(values))
                self.assertEqual(len(samples), len(values))
                self.assertEqual(struct.unpack_from("<I", result, 4)[0], len(result) - 8)
                self.assertEqual(struct.unpack_from("<I", result, 40)[0], len(values) * 2)

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
        source = bytearray(wav_bytes([1000, -1000] * 100))
        struct.pack_into("<I", source, 4, 0xffffffff)
        struct.pack_into("<I", source, 40, 0xffffffff)
        source = bytes(source)
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
