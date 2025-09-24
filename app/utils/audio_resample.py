import logging
import base64
import numpy as np
from scipy import signal
from scipy.signal import resample_poly

logger = logging.getLogger(__name__)

class AudioResampler:
    """
    High-quality audio resampling for real-time communication between OpenAI (24kHz) and Teler (8kHz).
    """

    def __init__(self):
        self.openai_sample_rate = 24000
        self.teler_sample_rate = 8000


    @staticmethod
    def safe_b64decode(data: str) -> bytes:
        if not data:
            return b""
        try:
            missing_padding = len(data) % 4
            if missing_padding:
                data += "=" * (4 - missing_padding)
            return base64.b64decode(data)
        except Exception as e:
            logger.error(f"Base64 decode error: {e}")
            return b""


    def downsample(self, audio_data: bytes) -> bytes:
        """
            Downsample 24k Hz audio from OpenAI to 8k Hz audio for Teler
        """
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            factor = self.openai_sample_rate // self.teler_sample_rate
            downsampled_array = signal.decimate(audio_array, q=factor, n=8, ftype="iir")
            return downsampled_array.astype(np.int16).tobytes()
        except Exception as e:
            logger.error(f"Error downsampling audio: {e}")
            return audio_data


    def upsample(self, audio_data: bytes) -> bytes:
        """
            Upsample 8k Hz audio from Teler to 24k Hz audio for OpenAI 
        """
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            factor = self.openai_sample_rate // self.teler_sample_rate  # 24k / 8k = 3
            upsampled_array = signal.resample(audio_array, len(audio_array) * factor)
            return upsampled_array.astype(np.int16).tobytes()
        except Exception as e:
            logger.error(f"Error upsampling 8k → 24k: {e}")
            return audio_data


    def decode_audio(self, audio_b64: str) -> np.ndarray:
        """
            Decode base64 to numpy for resampling
        """
        raw = self.safe_b64decode(audio_b64)
        return np.frombuffer(raw, dtype=np.int16)


    def encode_audio(self, pcm: np.ndarray) -> str:
        """
            Encode numpy to base64 for resampling
        """
        return base64.b64encode(pcm.astype(np.int16).tobytes()).decode("utf-8")


    def resample_audio(self, pcm: np.ndarray, orig_sr: int, target_sr: int) -> np.ndarray:
        """
            Resample audio using resample_poly
        """
        try:
            gcd = np.gcd(orig_sr, target_sr)
            up = target_sr // gcd
            down = orig_sr // gcd
            resampled = resample_poly(pcm, up, down)
            return resampled.astype(np.int16)
        except Exception as e:
            logger.error(f"Error resampling audio from {orig_sr} -> {target_sr}: {e}")
            return pcm
