import json
import base64
import logging

from fastapi import (APIRouter, WebSocket, WebSocketDisconnect)

from app.utils.audio_resample import AudioResampler


logger = logging.getLogger(__name__)
router = APIRouter()
audio_resampler = AudioResampler()


async def recv_from_teler(openai_ws: WebSocket, websocket: WebSocket) -> None:
    """
    Receive audio from Teler, upsample, and send to OpenAI
    """
    try:
        while True:
            data = json.loads(await websocket.receive_text())
            if data.get("type") != "audio":
                continue

            audio_b64 = data["data"]["audio_b64"]
            logger.info(f"[media-stream][teler] 🎵 Received audio chunk ({len(audio_b64)} bytes)")
            try:
                # Decode base64 to bytes
                pcm_8k = base64.b64decode(audio_b64)
                # Upsample 8k -> 24k
                upsampled_data = audio_resampler.upsample(pcm_8k)
                # Encode back to base64 for OpenAI
                upsampled_b64_24k = base64.b64encode(upsampled_data).decode("utf-8")

                await openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": upsampled_b64_24k
                }))
                logger.debug(f"[media-stream][teler] 📤 Sent upsampled PCM16 24k audio to OpenAI")
            except Exception as e:
                logger.error(f"[media-stream][teler] ❌ Audio processing error: {e}")
    except WebSocketDisconnect:
        logger.error("[media-stream][teler] 🔌 Teler WebSocket disconnected.")
    except Exception as e:
        logger.error(f"[media-stream][teler] ❌ recv_from_teler error: {type(e).__name__}: {e}")
