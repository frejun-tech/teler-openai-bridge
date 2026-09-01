import base64
import logging
import numpy as np
import soxr

logger = logging.getLogger(__name__)


class AudioResampler:
    """
    Stateful audio resampler: OpenAI 24kHz PCM16 → Teler 8kHz PCM16.

    Uses soxr (libsoxr) with HQ mode — Kaiser-windowed sinc filter with
    proper anti-aliasing. The ResampleStream instance carries internal
    filter state across chunks, so there are zero boundary artifacts
    between consecutive WebSocket frames.

    One instance per call/session. Call reset() when a new call starts.
    """

    OPENAI_RATE = 24_000
    TELER_RATE  = 8_000

    def __init__(self):
        self._stream = self._make_stream()

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    def downsample_base64(self, audio_b64: str) -> str:
        """
        Accept a single base64-encoded PCM16 chunk at 24kHz,
        return a base64-encoded PCM16 chunk at 8kHz.

        Returns "" on empty input or error (caller can skip sending).
        """
        if not audio_b64:
            return ""
        try:
            pcm_24k = np.frombuffer(base64.b64decode(audio_b64), dtype=np.int16)
            if pcm_24k.size == 0:
                return ""
            pcm_8k: np.ndarray = self._stream.resample_chunk(pcm_24k)
            if pcm_8k.size == 0:
                # soxr buffers a few samples at the start — nothing to emit yet
                return ""
            return base64.b64encode(pcm_8k.tobytes()).decode()
        except Exception as e:
            logger.error(f"[AudioResampler] downsample error: {e}")
            return ""

    def flush_base64(self) -> str:
        """
        Drain any samples still held in soxr's internal filter buffer.
        Call this at end-of-utterance / end-of-call to avoid a short
        tail of audio being silently dropped.

        Returns "" if nothing is buffered.
        """
        try:
            pcm_8k: np.ndarray = self._stream.resample_chunk(
                np.array([], dtype=np.int16), last=True
            )
            if pcm_8k.size == 0:
                return ""
            return base64.b64encode(pcm_8k.tobytes()).decode()
        except Exception as e:
            logger.error(f"[AudioResampler] flush error: {e}")
            return ""

    def reset(self) -> None:
        """
        Re-initialise the resampler state for a new call/session.
        Must be called whenever a fresh audio stream begins, otherwise
        the old filter state bleeds into the new stream.
        """
        self._stream = self._make_stream()

    # ------------------------------------------------------------------
    # Internal
    # ------------------------------------------------------------------

    @classmethod
    def _make_stream(cls) -> soxr.ResampleStream:
        return soxr.ResampleStream(
            in_rate=cls.OPENAI_RATE,
            out_rate=cls.TELER_RATE,
            num_channels=1,
            quality="HQ",   # HQ = 20-bit SNR, good anti-alias, low latency
            dtype="int16",
        )