import json
import asyncio
import logging

import websockets
from fastapi import (APIRouter, HTTPException, WebSocket, status)
from fastapi.responses import JSONResponse
from fastapi.websockets import WebSocketState
from pydantic import BaseModel

from app.core.config import settings
from app.schemas.call import Call
from app.core.openai_config import openai_configurations, initial_instruction
from app.utils.teler_to_openai import teler_to_openai
from app.utils.openai_to_teler import openai_to_teler
from teler import AsyncClient, CallFlow
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
    return JSONResponse(
        CallFlow.stream(
            ws_url=ws_url,
            sample_rate="16k",
            chunk_size=1600,
            record=False,
        )
    )

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
        async with AsyncClient(api_key=settings.teler_api_key, timeout=10) as client:
            call = await client.voice.calls.create(
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
            logger.info("[media-stream] Successfully connected to OpenAI WebSocket")

            call = Call()
            call.teler_connection = websocket
            call.openai_connection = openai_ws

            await call.openai_connection.send(json.dumps(openai_configurations))
            logger.info("[media-stream] Sent session.update")
            response_data = json.loads(await call.openai_connection.recv())
            logger.debug("[media-stream][openai] Session response: %s", json.dumps(response_data, indent=2))
            
            # Send Open AI config and wait for session.updated event
            while True:
                response_data = json.loads(await call.openai_connection.recv())

                logger.debug("[media-stream][openai] Event: %s", json.dumps(response_data, indent=2))

                event_type = response_data.get("type")

                if event_type == "session.updated":
                    call.session_updated = True
                    logger.info("[media-stream] OpenAI session updated")
                    break

                if event_type == "session.created":
                    call.session_created = True
                    logger.info("OpenAI Realtime session created")

                if event_type == "error":
                    raise RuntimeError(f"OpenAI session update failed: {response_data}")

            # Send initial instruction
            await call.openai_connection.send(json.dumps(initial_instruction))
            # Ask OpenAI to generate response
            await call.openai_connection.send(json.dumps({"type": "response.create"}))
            logger.info("[media-stream] Requested initial greeting")


            # Start bi-directional media processing
            recv_task = asyncio.create_task(teler_to_openai(call))
            send_task = asyncio.create_task(openai_to_teler(call))
            
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
