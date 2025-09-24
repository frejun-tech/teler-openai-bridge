import os

from pydantic_settings import BaseSettings
from app.utils.ngrok_utils import get_server_domain

class Setting(BaseSettings):
    """Application settings"""
    
    # Open AI configuration
    openai_api_key: str = os.getenv("openai_api_key", "")
    openai_ws_url: str = os.getenv("openai_ws_url") or f"wss://api.openai.com/v1/realtime?model=gpt-4o-realtime-preview-2024-10-01"
    
    #server configuration - dynamically get ngrok URL
    @property
    def server_domain(self) -> str:
        return get_server_domain()
    
    server_host: str = os.getenv("SERVER_HOST", "0.0.0.0")
    server_port: int = int(os.getenv("SERVER_PORT", "8000"))
    
    # Teler configuration
    teler_account_id: str = os.getenv("teler_account_id")
    teler_api_key: str = os.getenv("teler_api_key", "")
    from_number: str = os.getenv("from_number", "")
    to_number: str = os.getenv("to_number", "")
    
    # AI and Call Configuration 
    voice: str = "alloy"
    system_message: str = "Speak clearly and briefly. Confirm understanding before taking actions."
    
    # Logging
    log_level: str = os.getenv("LOG_LEVEL", "INFO")
    
    class Config:
        env_file = ".env"
        case_sensitive = False
    
    
# settings instance
settings = Setting()