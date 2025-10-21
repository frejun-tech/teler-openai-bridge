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
    chunk_id = 0
    audio_buffer = []
    buffer_chunk_size = 6

    try:
        async for msg in openai_ws:
            data = json.loads(msg)
            msg_type = data.get("type", "unknown")
            logger.info(f"[media-stream][openai] 📥 Received message: type='{msg_type}'")

            # Audio chunks from OpenAI
            if msg_type == "response.output_audio.delta":
                audio_b64 = data.get("delta", "")
                if audio_b64:
                    audio_8k_b64 = audio_resampler.downsample_base64(audio_b64)
                    if audio_8k_b64:
                        audio_buffer.append(audio_8k_b64)

                    if len(audio_buffer) >= buffer_chunk_size:
                        combined_b64 = "".join(audio_buffer)
                        await websocket.send_json({
                            "type": "audio",
                            "audio_b64": combined_b64,
                            "chunk_id": chunk_id
                        })
                        logger.info('Sent audio chunks from OpenAI to Teler')
                        audio_buffer = []
                        chunk_id += 1

            # Clear buffer
            elif msg_type == "input_audio_buffer.speech_started":
                audio_buffer = []
                await websocket.send_json({"type": "clear"})

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
            combined_b64 = "".join(audio_buffer)
            await websocket.send_json({
                "type": "audio",
                "audio_b64": combined_b64,
                "chunk_id": chunk_id
            })

