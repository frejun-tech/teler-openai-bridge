import json
import base64
import logging
import numpy as np
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.utils.audio_resample import AudioResampler

logger = logging.getLogger(__name__)
router = APIRouter()

idSessionCreated = False

async def openai_to_teler(openai_ws: WebSocket, websocket: WebSocket) -> None:
    """
    Receive audio/text from OpenAI Realtime API, resample 24kHz → 8kHz
    with proper anti-aliasing, and forward to Teler over WebSocket.

    Key fixes vs previous version
    ──────────────────────────────
    1. Resampler is actually called (it was commented out before).
    2. AudioResampler is instantiated per-call, not module-level, so the
       soxr filter state is fresh for every session.
    3. Audio chunks are buffered as raw bytes, not base64 strings.
       Concatenating base64 strings is incorrect — the padding chars ('=')
       in the middle of a joined string corrupt the decode.
    4. flush_base64() is called at the end so the soxr tail buffer is
       drained and the last syllable is never cut off.
    5. reset() is called on speech_started so the resampler state is
       clean after an interruption.
    """

    chunk_id = 0
    # Buffer raw PCM bytes (decoded), not base64 strings
    pcm_buffer: list[bytes] = []
    BUFFER_CHUNK_SIZE = 6          # flush every 6 OpenAI deltas (~180 ms at 24kHz/chunk)

    # One resampler per call — carries filter state across all chunks
    resampler = AudioResampler()

    async def _flush_buffer(force: bool = False) -> None:
        """Combine buffered PCM, encode, send; optionally drain soxr tail."""
        nonlocal chunk_id, pcm_buffer

        if not pcm_buffer and not force:
            return

        combined_pcm = b"".join(pcm_buffer)
        pcm_buffer = []

        if combined_pcm:
            audio_8k_b64 = base64.b64encode(combined_pcm).decode()
            await websocket.send_json({
                "type": "audio",
                "audio_b64": audio_8k_b64,
                "chunk_id": chunk_id,
            })
            logger.debug(f"[media-stream] Sent audio chunk {chunk_id} to Teler")
            chunk_id += 1

        if force:
            # Drain any samples still in soxr's sinc filter buffer
            tail_b64 = resampler.flush_base64()
            if tail_b64:
                await websocket.send_json({
                    "type": "audio",
                    "audio_b64": tail_b64,
                    "chunk_id": chunk_id,
                })
                chunk_id += 1

    try:
        async for msg in openai_ws:
            data = json.loads(msg)
            msg_type = data.get("type", "unknown")
            logger.debug(f"[media-stream][openai] type={msg_type}")

            # ── Audio delta from OpenAI ──────────────────────────────
            if msg_type == "response.output_audio.delta":
                raw_b64 = data.get("delta", "")
                if not raw_b64:
                    continue

                # Resample this chunk (soxr keeps state between calls)
                resampled_b64 = resampler.downsample_base64(raw_b64)
                if resampled_b64:
                    pcm_buffer.append(base64.b64decode(resampled_b64))

                if len(pcm_buffer) >= BUFFER_CHUNK_SIZE:
                    await _flush_buffer()

            # ── User started speaking → interrupt ────────────────────
            elif msg_type == "input_audio_buffer.speech_started":
                pcm_buffer = []
                resampler.reset()          # clear filter state for fresh stream
                await websocket.send_json({"type": "clear"})

            elif msg_type == "session.created":
                isSessionCreated = True

            # ── Response finished → drain tail ───────────────────────
            elif msg_type in ("response.audio.done", "response.done"):
                await _flush_buffer(force=True)

            # ── OpenAI error ─────────────────────────────────────────
            elif msg_type == "error":
                logger.error(f"[media-stream][openai] error: {data.get('error', {})}")

    except WebSocketDisconnect:
        logger.warning("[media-stream][teler] Teler WebSocket disconnected.")
    except Exception as e:
        logger.error(f"[media-stream][openai] openai_to_teler: {type(e).__name__}: {e}")
    finally:
        # Best-effort: flush whatever is left before the socket closes
        try:
            await _flush_buffer(force=True)
        except Exception:
            pass