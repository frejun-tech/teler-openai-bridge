import json
import base64
import logging
from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from app.utils.audio_resample import AudioResampler

logger = logging.getLogger(__name__)
router = APIRouter()
audio_resampler = AudioResampler()


async def openai_to_teler(openai_ws: WebSocket, websocket: WebSocket) -> None:
    """
    Receive audio/text from OpenAI, downsample 24kHz → 8kHz, buffer, and send to Teler.
    Flushes buffered audio on normal completion or interruption.
    """
    chunk_id = 1 
    audio_buffer = []

    try:
        async for msg in openai_ws:
            data = json.loads(msg)
            msg_type = data.get("type", "unknown")
            logger.info(f"[media-stream][openai] 📥 Received message: type='{msg_type}'")

            # Audio chunks from OpenAI
            if msg_type == "response.output_audio.delta":
                audio_b64 = data.get("delta", "")
                if audio_b64:
                    try:
                        # Decode 24kHz audio from OpenAI
                        pcm_24k = audio_resampler.decode_audio(audio_b64)
                        # Downsample to 8kHz for Teler using the new downsample
                        pcm_8k = audio_resampler.downsample(pcm_24k)
                        # Encode to base64
                        audio_8k_b64 = audio_resampler.encode_audio(pcm_8k)
                        # Append to buffer
                        audio_buffer.append(base64.b64decode(audio_8k_b64))

                        combined = b"".join(audio_buffer)
                        combined_b64 = base64.b64encode(combined).decode("utf-8")

                        await websocket.send_json({
                            "type": "audio",
                            "audio_b64": combined_b64,
                            "chunk_id": chunk_id
                        })
                        logger.debug(f"[media-stream][teler] ▶️ Sent buffered audio chunk {chunk_id} to Teler")
                        chunk_id += 1
                        audio_buffer = []

                    except Exception as e:
                        logger.error(f"[media-stream][openai] ❌ Audio processing error: {e}")

            # Clear buffer
            elif msg_type == "input_audio_buffer.speech_started ":
                audio_buffer = []

            elif msg_type == "session.updated":
                logger.info("[media-stream][openai] ✅ Session configuration updated")

            elif msg_type == "error":
                error_info = data.get("error", {})
                logger.error(f"Data: {data}")
                logger.warning(f"[media-stream][openai] OpenAI error: {error_info}")

    except WebSocketDisconnect:
        logger.error("[media-stream][teler] 🔌 Teler WebSocket disconnected.")
    except Exception as e:
        logger.error(f"[media-stream][openai] ❌ openai_to_teler error: {type(e).__name__}: {e}")
    finally:
        # Flush any remaining buffered audio even if interrupted
        if audio_buffer:
            try:
                combined = b"".join(audio_buffer)
                combined_b64 = base64.b64encode(combined).decode("utf-8")
                await websocket.send_json({
                    "type": "audio",
                    "audio_b64": combined_b64,
                    "chunk_id": chunk_id
                })
                audio_buffer = []
                logger.debug(f"[media-stream][teler] ▶️ Sent final buffered audio chunk {chunk_id} to Teler")
            except Exception as e:
                logger.warning(f"[media-stream][teler] ⚠️ Could not flush remaining audio: {e}")
