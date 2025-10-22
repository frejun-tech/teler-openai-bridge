import json
import base64
import logging

from fastapi import (APIRouter, WebSocket, WebSocketDisconnect)

from app.utils.audio_resample import AudioResampler


logger = logging.getLogger(__name__)
router = APIRouter()
audio_resampler = AudioResampler()


async def teler_to_openai(openai_ws: WebSocket, websocket: WebSocket) -> None:
    """
    Receive audio from Teler and send to OpenAI
    """
    try:
        while True:
            data = json.loads(await websocket.receive_text())
            if data.get("type") != "audio":
                continue

            audio_b64 = data["data"]["audio_b64"]
            logger.debug(f"[media-stream][teler] Received audio chunk ({len(audio_b64)} bytes)")
            try:
                await openai_ws.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": audio_b64 
                }))
                logger.debug(f"[media-stream][teler] Sent Base64 16k audio to OpenAI")
            except Exception as e:
                logger.error(f"[media-stream][teler] Audio processing error: {e}")
    except WebSocketDisconnect:
        logger.error("[media-stream][teler] Teler WebSocket disconnected.")
    except Exception as e:
        logger.error(f"[media-stream][teler] teler_to_openai error: {type(e).__name__}: {e}")
