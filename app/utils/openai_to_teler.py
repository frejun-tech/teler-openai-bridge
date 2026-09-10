from app.core.config import settings
import json
import base64
import logging

from app.schemas.call import Call
from fastapi import APIRouter, WebSocketDisconnect

logger = logging.getLogger(__name__)
router = APIRouter()


async def openai_to_teler(call: Call) -> None:
    """
    Receive audio from OpenAI Realtime API -> downsample -> relay to Teler.
    """
    chunk_id = 1
    message_buffer: list[bytes] = []
    BUFFER_CHUNK_SIZE = settings.buffer_size

    async def _flush():
        nonlocal chunk_id, message_buffer

        if not message_buffer:
            return

        try:
            combined_audio = b"".join(message_buffer)

            # downsample the audio before streaming to Teler
            downsampled_audio_bytes = call.audio_processor.downsample(combined_audio)
            downsampled_audio = base64.b64encode(downsampled_audio_bytes).decode("utf-8")

            await call.teler_connection.send_json({
                "type": "audio",
                "audio_b64": downsampled_audio,
                "chunk_id": chunk_id
            })

            logger.debug(f"Sent audio to Teler (chunk {chunk_id})")

            message_buffer = []
            chunk_id += 1
        except Exception as e:
            logger.error(f"Error processing buffered audio: {e}")
            message_buffer = []

    try:
        while True:
            try:
                async for msg in call.openai_connection:
                    data = json.loads(msg)
                    msg_type = data.get("type", "unknown")

                    logger.debug(f"[media-stream][openai] type={msg_type}")

                    if msg_type == "response.output_audio.delta":
                        raw_b64 = data.get("delta", "")

                        if not raw_b64:
                            continue

                        try:
                            # Buffer raw PCM
                            raw_pcm = base64.b64decode(raw_b64)
                            message_buffer.append(raw_pcm)
                            logger.debug(f"Received OpenAI audio chunk "f"({len(raw_pcm)} bytes)")

                            # Flush after enough chunks
                            if len(message_buffer) >= BUFFER_CHUNK_SIZE:
                                await _flush()

                        except Exception as e:
                            logger.error(f"Error processing audio chunk: {e}")

                    elif msg_type == "input_audio_buffer.speech_started":
                        logger.debug("Interruption detected — clearing remaining buffer")
                        message_buffer = []
                        await call.teler_connection.send_json({"type": "clear"})

                    elif msg_type in ("response.output_audio.done"):
                        logger.debug("Response completed - flushing remaining buffer")
                        await _flush()

                    elif msg_type == "error":
                        logger.error(f"[media-stream][openai] error: {data.get('error', {})}")

            except WebSocketDisconnect:
                logger.warning("[media-stream][teler] Teler WebSocket disconnected.")

    except Exception as e:
        logger.error(f"[media-stream][openai_to_teler] {type(e).__name__}: {e}")

    finally:
        try:
            await _flush()
        except Exception as e:
            logger.debug(f"Final audio flush failed: {e}")