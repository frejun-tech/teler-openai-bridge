import json
import base64
import logging

from fastapi import (APIRouter, WebSocket, WebSocketDisconnect)

from app.utils.audio_resample import AudioResampler


logger = logging.getLogger(__name__)
router = APIRouter()
audio_resampler = AudioResampler()


async def send_to_teler(openai_ws: WebSocket, websocket: WebSocket) -> None:
    """
    Receive audio/text from OpenAI, buffer for smooth playback, downsample, and send to Teler
    """
    try:
        chunk_id = 1
        audio_buffer = []

        async for msg in openai_ws:
            data = json.loads(msg)
            msg_type = data.get("type", "unknown")
            logger.info(f"[media-stream][openai] 📥 Received message: type='{msg_type}'")

            # Audio chunks from OpenAI
            if msg_type == "response.output_audio.delta":
                audio_b64 = data.get("delta", "")
                
                if audio_b64:
                    try:
                        pcm_24k = audio_resampler.decode_audio(audio_b64)
                        pcm_16k = audio_resampler.resample_audio(pcm_24k, orig_sr=24000, target_sr=16000)
                        pcm_8k  = audio_resampler.resample_audio(pcm_16k, orig_sr=16000, target_sr=8000)
                        audio_8k_b64 = audio_resampler.encode_audio(pcm_8k)

                        # Append bytes to buffer (decode base64 once)
                        audio_buffer.append(base64.b64decode(audio_8k_b64))
                        
                        # Flush every 3 chunks for smoother playback
                        if len(audio_buffer) >= 3:
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

            # Partial transcript
            elif msg_type == "response.output_audio_transcript.delta":
                transcript = data.get("delta", "")
                if transcript:
                    logger.info(f"[media-stream][openai] ✍️ AI (partial): {transcript}")

            # Final text output
            elif msg_type == "response.completed":
                transcript = data.get("response", {}).get("output_text", "")
                if transcript:
                    logger.info(f"[media-stream][openai] ✍️ AI said: {transcript}")

            # Session events
            elif msg_type == "session.created":
                session_id = data.get("session", {}).get("id")
                logger.info(f"[media-stream][openai] ✅ Session created: {session_id}")

            elif msg_type == "session.updated":
                logger.info("[media-stream][openai] ✅ Session configuration updated")

            elif msg_type == "error":
                error_info = data.get("error", {})
                logger.error(f"Data: {data}")
                logger.warning(f"[media-stream][openai] OpenAI error: {error_info}")

        # Flush any remaining buffered audio
        if audio_buffer:
            combined = b"".join(audio_buffer)
            downsampled_data = audio_resampler.downsample(combined)
            downsampled_b64 = base64.b64encode(downsampled_data).decode("utf-8")
            await websocket.send_json({
                "type": "audio",
                "audio_b64": downsampled_b64,
                "chunk_id": chunk_id
            })
            logger.debug(f"[media-stream][teler] ▶️ Sent final buffered audio chunk {chunk_id} to Teler")

    except WebSocketDisconnect:
        logger.error("[media-stream][teler] 🔌 Teler WebSocket disconnected.")
    except Exception as e:
        logger.error(f"[media-stream][openai] ❌ send_to_teler error: {type(e).__name__}: {e}")
