import logging
import base64
import numpy as np
from scipy.signal import resample_poly

logger = logging.getLogger(__name__)

class AudioResampler:
    """
    Audio resampler for OpenAI (24kHz) → Teler (8kHz) pipeline.
    """

    def __init__(self):
        self.openai_sample_rate = 24000
        self.teler_output_sample_rate = 8000

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

    def decode_audio(self, audio_b64: str) -> np.ndarray:
        """Decode base64 to PCM16 numpy array"""
        raw = self.safe_b64decode(audio_b64)
        return np.frombuffer(raw, dtype=np.int16)

    def encode_audio(self, pcm: np.ndarray) -> str:
        """Encode PCM16 numpy array to base64"""
        return base64.b64encode(pcm.astype(np.int16).tobytes()).decode("utf-8")

    def downsample(self, audio_data: np.ndarray) -> np.ndarray:
        """
        Downsample 24kHz audio from OpenAI to 8kHz for Teler.
        Input: np.ndarray (int16)
        Output: np.ndarray (int16)
        """
        try:
            # 24k → 8k (factor = 3)
            downsampled = resample_poly(audio_data, up=1, down=3)
            return downsampled.astype(np.int16)
        except Exception as e:
            logger.error(f"Error downsampling audio: {e}")
            return audio_data
