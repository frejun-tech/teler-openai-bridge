from fastapi import WebSocket
from dataclasses import dataclass, field
from typing import Optional

from app.utils.audio_resample import AudioResampler

@dataclass
class Call:
    call_id: Optional[str] = None
    session_created: bool = False
    session_updated: bool = False
    teler_connection: Optional[WebSocket] = None
    openai_connection: Optional[WebSocket] = None
    audio_processor: Optional[AudioResampler] = None

    def __init__(self):
        self.audio_processor = AudioResampler()