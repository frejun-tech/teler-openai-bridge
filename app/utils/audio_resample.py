import base64
import numpy as np
from scipy.signal import resample_poly
import logging

logger = logging.getLogger(__name__)

class AudioResampler:
    """
    Audio resampler for OpenAI (24kHz) → Teler (8kHz) pipeline.
    """

    def __init__(self):
        self.openai_sample_rate = 24000
        self.teler_output_sample_rate = 8000

    @staticmethod
    def downsample_base64(audio_b64: str) -> str:
        try:
            pcm_24k = np.frombuffer(base64.b64decode(audio_b64), dtype=np.int16)
            if len(pcm_24k) == 0:
                return ""
            pcm_8k = resample_poly(pcm_24k, up=1, down=3).astype(np.int16)
            return base64.b64encode(pcm_8k.tobytes()).decode("utf-8")
        except Exception as e:
            logger.error(f"Downsampling error: {e}")
            return ""

