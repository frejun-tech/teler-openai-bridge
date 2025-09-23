import json
import base64
import asyncio
import logging

import websockets
from fastapi import (APIRouter, HTTPException, Request, WebSocket, WebSocketDisconnect, status)
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketState
from pydantic import BaseModel

from app.core.config import settings
from app.utils.teler_client import TelerClient
from app.utils.audio_resample import AudioResampler

logger = logging.getLogger(__name__)
router = APIRouter()
audio_resampler = AudioResampler()

class CallFlowRequest(BaseModel):
    call_id: str
    account_id: str
    from_number: str
    to_number: str

class CallRequest(BaseModel):
    from_number: str
    to_number: str

# FastAPI Endpoints 

@router.get("/")
async def root():
    return {"message": "Welcome to the Teler-OpenAI bridge"}

@router.post("/flow", status_code=status.HTTP_200_OK, include_in_schema=False)
async def stream_flow(payload: CallFlowRequest):
    """
    Build and return stream flow
    """
    # Build ws_url from configured server domain
    ws_url = f"wss://{settings.server_domain}/api/v1/calls/media-stream"
    stream_flow = {
        "action": "stream",
        "ws_url": ws_url,
        "chunk_size": 500,
        "sample_rate": "8k",
        "record": True
    }
    return JSONResponse(stream_flow)

@router.post("/incoming-call")
async def incoming_call(request: Request):
    try:
        body = await request.json()
        if settings.teler_account_id and body.get("account_id") != settings.teler_account_id:
            raise HTTPException(status_code=403, detail="Invalid account_id")

        call_id = body.get("call_id")
        logger.info(f"Incoming call {call_id}, responding with stream action.")
        stream_flow = {
            "action": "stream",
            "ws_url": f"wss://{settings.server_domain}/api/v1/calls/media-stream",
            "chunk_size": 500,
            "sample_rate": "8k",
            "record": True
        }
        return JSONResponse(stream_flow)
    except Exception as e:
        logger.error(f"Error in /incoming-call: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.post("/initiate-call", status_code=status.HTTP_200_OK)
async def initiate_call(call_request: CallRequest):
    """
    Initiate a call using Teler SDK.
    """
    try:
        if not settings.openai_api_key:
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="OPENAI_API_KEY not configured"
            )
        teler_client = TelerClient(api_key=settings.teler_api_key)
        call = await teler_client.create_call(
            from_number=call_request.from_number,
            to_number=call_request.to_number,
            flow_url=f"https://{settings.server_domain}/api/v1/calls/flow",
            status_callback_url=f"https://{settings.server_domain}/api/v1/webhooks/receiver",
            record=True,
        )
        logger.info(f"Call created: {call}")
        return JSONResponse(content={"success": True, "call": call})
    except Exception as e:
        logger.error(f"Failed to create call: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Call creation failed."
        )

@router.post("/call-status")
async def call_status(request: Request):
    try:
        body = await request.json()
        logger.info(f"Call status update: {body.get('event')}")
        return {"status": "ok"}
    except Exception as e:
        logger.error(f"Error in /call-status: {e}")
        raise HTTPException(status_code=500, detail="Internal Server Error")


@router.websocket("/media-stream")
async def media_stream(ws: WebSocket):
    print("\n\n--- RUNNING THE LATEST VERSION OF THE CODE ---\n\n")
    await ws.accept()
    logger.info("Web Socket Connected")

    try:
        if not settings.openai_api_key:
            await ws.close(code=1008, reason="OPENAI_API_KEY not configured")
            return
        
        print(
            f"[media-stream] 🔑 Connecting to OpenAI with API Key: {settings.openai_api_key[:4]}"
        )
        
        async with websockets.connect(
                settings.openai_ws_url,
                extra_headers={
                    "Authorization": f"Bearer {settings.openai_api_key}",
                    "OpenAI-Beta": "realtime=v1"
                }) as openai_ws:
            print(
                "[media-stream] ✅ Successfully connected to OpenAI WebSocket")

            # Send proper session update
            session_update = {
                "type": "session.update",
                "session": {
                    "modalities": ["text", "audio"],
                    "instructions": settings.system_message,
                    "voice": settings.voice,
                    "input_audio_format": "pcm16",
                    "output_audio_format": "pcm16",
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "turn_detection": {
                        "type": "server_vad",
                        "threshold": 0.5,
                        "prefix_padding_ms": 300,
                        "silence_duration_ms": 200
                    }
                }
            }
            print("[media-stream][openai] 📤 Sending session update...")
            await openai_ws.send(json.dumps(session_update))

            # Wait for session confirmation
            response_data = json.loads(await openai_ws.recv())
            print(f"[media-stream][openai] 📥 Session response: {json.dumps(response_data, indent=2)}")
            
            if response_data.get('type') == 'session.created':
                session_id = response_data.get('session', {}).get('id')
                print(f"[media-stream][openai] ✅ Session created with ID: {session_id}")
                
                # Check audio configuration
                session = response_data.get('session', {})
                input_format = session.get('input_audio_format')
                output_format = session.get('output_audio_format')
                print(f"[media-stream][openai] 🎧 Audio formats - Input: {input_format}, Output: {output_format}")
                
            else:
                print(f"[media-stream][openai] ❌ Failed to setup session: {response_data}")
                return

            # Send initial response to start conversation
            print("[media-stream][openai] 🎤 Creating initial response...")
            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "modalities": ["text", "audio"],
                    "instructions": "Greet the user and ask how you can help them today."
                }
            }))

            async def recv_from_teler():
                try:
                    while True:
                        data = json.loads(await ws.receive_text())
                        if data.get("type") == "audio":
                            audio_b64 = data["data"]["audio_b64"]
                            print(f"[media-stream][teler] 🎵 Received audio chunk")
                            
                            try:
                                # Decode PCM audio from Teler (8kHz, 16-bit)
                                pcm_data = base64.b64decode(audio_b64)
                                
                                # Upsample from 8kHz to 24kHz for OpenAI
                                upsampled_data = audio_resampler.upsample(pcm_data)
                                
                                # Encode back to base64 for OpenAI
                                upsampled_b64 = base64.b64encode(upsampled_data).decode('utf-8')
                                
                                # Send audio using input_audio_buffer.append (OpenAI expects PCM16 at 24kHz)
                                await openai_ws.send(json.dumps({
                                    "type": "input_audio_buffer.append",
                                    "audio": upsampled_b64
                                }))
                                print(f"[media-stream][teler] 📤 Sending upsampled PCM16 audio to OpenAI")
                                
                            except Exception as e:
                                print(f"[media-stream][teler] ❌ Audio processing error: {e}")
                except WebSocketDisconnect:
                    print(
                        "[media-stream][teler] 🔌 Teler WebSocket disconnected."
                    )
                except Exception as e:
                    print(
                        f"[media-stream][teler] ❌ Error in recv_from_teler: {type(e).__name__}: {e}"
                    )

            async def send_to_teler():
                try:
                    chunk_id = 1
                    audio_chunks = []  # Buffer to accumulate raw audio chunks from OpenAI
                    chunk_count = 0
                    async for msg in openai_ws:
                        data = json.loads(msg)
                        msg_type = data.get('type', 'unknown')
                        print(
                            f"[media-stream][openai] 📥 Received message: type='{msg_type}'"
                        )
                        if msg_type == "response.audio.delta":
                            # Handle audio output from OpenAI (PCM16 format at 24kHz)
                            audio_b64 = data.get("delta", "")
                            if audio_b64:
                                print(f"[media-stream][openai] 🔊 Received audio delta (length: {len(audio_b64)})")
                                
                                try:
                                    # Decode PCM audio from OpenAI (24kHz, 16-bit) and add to buffer
                                    pcm_data = base64.b64decode(audio_b64)
                                    audio_chunks.append(pcm_data)
                                    chunk_count += 1
                                    print(f"[media-stream][openai] 📦 Buffered audio chunk {chunk_count} (size: {len(pcm_data)} bytes)")
                                    
                                    # Check if we have enough chunks to process
                                    if chunk_count >= AUDIO_CHUNK_COUNT:
                                        # Combine all buffered chunks
                                        combined_audio = b"".join(audio_chunks)
                                        
                                        # Downsample the combined audio from 24kHz to 8kHz for Teler
                                        downsampled_data = audio_resampler.downsample(combined_audio)
                                        
                                        # Encode to base64 for Teler
                                        downsampled_b64 = base64.b64encode(downsampled_data).decode('utf-8')
                                        
                                        await ws.send_json({
                                            "type": "audio",
                                            "audio_b64": downsampled_b64,
                                            "chunk_id": chunk_id
                                        })
                                        chunk_id += 1
                                        print(f"[media-stream][openai] 📤 Sending downsampled PCM16 audio to Teler (chunk {chunk_id-1}, processed {chunk_count} chunks, size: {len(downsampled_data)} bytes)")
                                        
                                        # Clear the buffer
                                        audio_chunks = []
                                        chunk_count = 0
                                    
                                except Exception as e:
                                    print(f"[media-stream][openai] ❌ Audio processing error: {e}")

                        elif msg_type == "session.created":
                            print(f"[media-stream][openai] ✅ Session created: {data.get('session', {}).get('id')}")

                        elif msg_type == "session.updated":
                            print("[media-stream][openai] ✅ Session configuration updated")

                        elif msg_type == "conversation.item.input_audio_transcription.completed":
                            transcript = data.get("transcript", "")
                            print(f"[media-stream][openai] ✍️ User said: {transcript}")

                        elif msg_type == "response.text.delta":
                            text_delta = data.get("delta", "")
                            if text_delta:
                                print(f"[media-stream][openai] 💭 AI thinking: {text_delta}")

                        elif msg_type == "error":
                            error_info = data.get("error", {})
                            print(f"[media-stream][openai] ❌ Error from OpenAI: {error_info}")                        
                except websockets.exceptions.ConnectionClosed:
                    print("[media-stream][openai] 🔌 OpenAI connection closed.")
                except Exception as e:
                    print(
                        f"[media-stream][openai] ❌ Error in send_to_teler: {type(e).__name__}: {e}"
                    )

            recv_task = asyncio.create_task(recv_from_teler())
            send_task = asyncio.create_task(send_to_teler())
            await asyncio.gather(recv_task, send_task)

    except websockets.exceptions.InvalidStatusCode as e:
        logger.info(
            f"[media-stream] ❌ WebSocket connection failed with status {e.status_code}: {e}"
        )
        if e.status_code == 403:
            logger.info(
                "[media-stream] 🔍 Possible causes: Invalid API key, insufficient permissions, or rate limits."
            )
    except Exception as e:
        logger.info(f"[media-stream] ❌ Top-level error: {type(e).__name__}: {e}")
    finally:
        if ws.client_state != WebSocketState.DISCONNECTED:
            await ws.close()
        logger.info("[media-stream] 🔄 Connection closed.")

