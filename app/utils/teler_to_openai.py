import json
import base64
import logging

from fastapi import (APIRouter, WebSocketDisconnect)

from app.schemas.call import Call

from app.utils.audio_resample import AudioResampler

logger = logging.getLogger(__name__)
router = APIRouter()
audio_resampler = AudioResampler()


async def teler_to_openai(call: Call) -> None:
    """
    Receive audio from Teler and send to OpenAI
    """
    try:
        while True:
            data = json.loads(await call.teler_connection.receive_text())
            if data.get("type") != "audio" or not call.session_updated:
                continue
            
            raw_b64 = data["data"]["audio_b64"]
            raw_pcm = base64.b64decode(raw_b64)
            logger.debug(f"[media-stream][teler] Received audio chunk ({len(raw_pcm)} bytes)")

            # upsample the audio before streaming to OpenAI
            upsampled_audio_bytes = call.audio_processor.upsample(raw_pcm)
            upsampled_audio = base64.b64encode(upsampled_audio_bytes).decode("utf-8")
            try:
                await call.openai_connection.send(json.dumps({
                    "type": "input_audio_buffer.append",
                    "audio": upsampled_audio 
                }))
                logger.debug(f"[media-stream][teler] Sent Base64 24k audio to OpenAI")
            except Exception as e:
                logger.error(f"[media-stream][teler] Audio processing error: {e}")
    except WebSocketDisconnect:
        logger.error("[media-stream][teler] Teler WebSocket disconnected.")
    except Exception as e:
        logger.error(f"[media-stream][teler] teler_to_openai error: {type(e).__name__}: {e}")
