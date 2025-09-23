import logging

import numpy as np
from scipy import signal

logger = logging.getLogger(__name__)

# --- Audio Resampling Class ---

class AudioResampler:
    """
    High-quality audio resampling for real-time communication between OpenAI (24kHz) and Teler (8kHz).
    """
    
    def __init__(self):
        self.openai_sample_rate = 24000
        self.teler_sample_rate = 8000
    
    def downsample(self, audio_data: bytes) -> bytes:
        """
        Downsample audio from OpenAI's 24kHz to Teler's 8kHz.
        
        Args:
            audio_data: Raw PCM audio data as bytes (pcm_s16le format at 24kHz)
        
        Returns:
            Downsampled audio data as bytes (pcm_s16le format at 8kHz)
        """
        try:
            # Convert bytes to numpy array (pcm_s16le format)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Calculate downsampling factor
            factor = self.openai_sample_rate // self.teler_sample_rate  # 24000 // 8000 = 3
            
            # Use scipy.decimate - optimized for integer downsampling with anti-aliasing
            # This method is fast, high quality, and specifically designed for downsampling
            downsampled_array = signal.decimate(
                audio_array, 
                q=factor,      # q=3 for 24kHz->8kHz
                n=8,           # Filter order for high quality
                ftype='iir'    # IIR filter for better performance
            )
            
            # Convert back to 16-bit PCM (pcm_s16le)
            downsampled_int16 = downsampled_array.astype(np.int16)
            
            return downsampled_int16.tobytes()
            
        except Exception as e:
            logger.error(f"Error downsampling audio: {e}")
            # Return original audio if downsampling fails
            return audio_data
    
    def upsample(self, audio_data: bytes) -> bytes:
        """
        Upsample audio from Teler's 8kHz to OpenAI's 24kHz.
        
        Args:
            audio_data: Raw PCM audio data as bytes (pcm_s16le format at 8kHz)
        
        Returns:
            Upsampled audio data as bytes (pcm_s16le format at 24kHz)
        """
        try:
            # Convert bytes to numpy array (pcm_s16le format)
            audio_array = np.frombuffer(audio_data, dtype=np.int16)
            
            # Calculate upsampling factor
            factor = self.openai_sample_rate / self.teler_sample_rate  # 24000 / 8000 = 3.0
            
            # Use scipy.resample for upsampling
            upsampled_array = signal.resample(
                audio_array, 
                int(len(audio_array) * factor)
            )
            
            # Convert back to 16-bit PCM (pcm_s16le)
            upsampled_int16 = upsampled_array.astype(np.int16)
            
            return upsampled_int16.tobytes()
            
        except Exception as e:
            logger.error(f"Error upsampling audio: {e}")
            # Return original audio if upsampling fails
            return audio_data



