import logging

import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)


class AudioResampler:
    """
    High-quality audio resampling for real-time communication between Gemini (16kHz/24kHz) and Teler (16kHz→8kHz).
    """

    def __init__(self):
        self.teler_input_sample_rate = 8000  # Teler expects 8kHz input
        self.teler_output_sample_rate = 16000 # Teler output 16kHz

        self.openai_input_sample_rate = 24000 # OpenAI expects 24kHz input
        self.openai_output_sample_rate = 24000  # OpenAI outputs 24kHz

    def downsample(self, audio_data: bytes) -> bytes:
        """
        Downsample audio to Teler's required 8kHz.

        Args:
            audio_data: Raw PCM audio data as bytes

        Returns:
            Downsampled audio data as bytes (pcm_s16le format at 8kHz)
        """
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            factor = self.openai_output_sample_rate // self.teler_input_sample_rate

            # Use scipy.decimate for high-quality downsampling
            downsampled_array = signal.decimate(
                audio_array, 
                q=factor,
                n=8,
                ftype='iir'
            )
            downsampled_int16 = downsampled_array.astype(np.int16)

            return downsampled_int16.tobytes()
        except Exception as e:
            logger.error(f"Error downsampling audio: {e}")
            return audio_data


    def upsample(self, audio_data: bytes) -> bytes:
        """
        Upsample audio to OpenAI's required 24kHz.

        Args:
            audio_data: Raw PCM audio data as bytes

        Returns:
            Upsampled audio data as bytes (pcm_s16le format at 24kHz)
        """
        try:
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            factor = self.openai_input_sample_rate // self.teler_output_sample_rate

            # Use scipy.resample for upsampling
            upsampled_array = signal.resample(
                audio_array, 
                int(len(audio_array) * factor)
            )
            upsampled_int16 = upsampled_array.astype(np.int16)

            return upsampled_int16.tobytes()
        except Exception as e:
            logger.error(f"Error upsampling audio: {e}")
            return audio_data