import json
import asyncio
import logging

import websockets
from fastapi import (APIRouter, HTTPException, WebSocket, status)
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketState
from pydantic import BaseModel

from app.core.config import settings
from app.utils.teler_to_openai import teler_to_openai
from app.utils.openai_to_teler import openai_to_teler
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

@router.get("/")
async def root():
    return {"message": "Welcome to the Teler-OpenAI bridge"}

@router.post("/flow", status_code=status.HTTP_200_OK, include_in_schema=False)
async def stream_flow(payload: CallFlowRequest):
    """
    Return stream flow as JSON Response containing websocket url to connect
    """
    ws_url = f"wss://{settings.server_domain}/api/v1/calls/media-stream"
    stream_flow = {
        "action": "stream",
        "ws_url": ws_url,
        "chunk_size": 1200,
        "sample_rate": "16k",  
        "record": True
    }
    return JSONResponse(stream_flow)

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
        return JSONResponse(content={"success": True, "call_id": call.id})
    except Exception as e:
        logger.error(f"Failed to create call: {e}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, 
            detail="Call creation failed."
        )

@router.websocket("/media-stream")
async def media_stream(websocket: WebSocket):
    """
    Handle received and sent audio chunks, Teler -> OpenAI, OpenAI -> Teler
    """
    await websocket.accept()
    logger.info("Web Socket Connected")

    try:
        if not settings.openai_api_key:
            await websocket.close(code=1008, reason="OPENAI_API_KEY not configured")
            return
        
        async with websockets.connect(
                settings.openai_ws_url,
                extra_headers={"Authorization": f"Bearer {settings.openai_api_key}"}) as openai_ws:
            logger.info(
                "[media-stream] Successfully connected to OpenAI WebSocket")

            session_update = {
                "type": "session.update",
                "session": {
                    "type": "realtime",
                    "instructions": settings.system_message,
                    "voice": settings.voice,
                    "input_audio_transcription": {
                        "model": "whisper-1"
                    },
                    "modalities": ["text", "audio"],
                    "conversation": "default"
                }
            }

            await openai_ws.send(json.dumps(session_update))

            response_data = json.loads(await openai_ws.recv())
            logger.debug(f"[media-stream][openai] Session response: {json.dumps(response_data, indent=2)}")
            
            if response_data.get('type') == 'session.created':
                session_id = response_data.get('session', {}).get('id')
                logger.info(f"[media-stream][openai] Session created with ID: {session_id}")
                
            else:
                logger.error(f"[media-stream][openai] Failed to setup session: {response_data}")
                return

            await openai_ws.send(json.dumps({
                "type": "response.create",
                "response": {
                    "instructions": "Greet the user warmly in one short sentence and ask how you can help. Be clear and concise. If the user requests more details, provide them simply."
                }
            }))

            recv_task = asyncio.create_task(teler_to_openai(openai_ws, websocket))
            send_task = asyncio.create_task(openai_to_teler(openai_ws, websocket))
            
            await asyncio.gather(recv_task, send_task)

    except websockets.exceptions.InvalidStatusCode as e:
        logger.error(
            f"[media-stream] WebSocket connection failed with status {e.status_code}: {e}"
        )
        if e.status_code == 403:
            logger.error(
                "[media-stream] Possible causes: Invalid API key, insufficient permissions, or rate limits."
            )
    except Exception as e:
        logger.error(f"[media-stream] Top-level error: {type(e).__name__}: {e}")
    finally:
        if websocket.client_state != WebSocketState.DISCONNECTED:
            await websocket.close()
        logger.info("[media-stream] Connection closed.")
