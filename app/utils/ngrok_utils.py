import httpx
import logging
from typing import Optional

logger = logging.getLogger(__name__)

def get_current_ngrok_url() -> Optional[str]:
    """
    Dynamically fetch the current ngrok public URL from ngrok's API
    """
    try:
        with httpx.Client(timeout=5.0) as client:
            response = client.get("http://ngrok:4040/api/tunnels")
            if response.status_code == 200:
                tunnels = response.json().get("tunnels", [])
                for tunnel in tunnels:
                    if tunnel.get("proto") == "https":
                        public_url = tunnel.get("public_url")
                        if public_url:
                            domain = public_url.replace("https://", "")
                            logger.info(f"Detected ngrok URL: {public_url}")
                            return domain
            else:
                logger.warning(f"Failed to fetch ngrok tunnels: {response.status_code}")
    except httpx.RequestError as e:
        logger.warning(f"Could not connect to ngrok API: {e}")
    except Exception as e:
        logger.error(f"Error fetching ngrok URL: {e}")
    
    return None

def get_server_domain() -> str:
    """
    Get the server domain, preferring the dynamic ngrok URL over environment variable
    """
    # Get the current ngrok URL 
    ngrok_url = get_current_ngrok_url()
    if ngrok_url:
        return ngrok_url
    
    # Fall back to environment variable if ngrok is not available
    import os
    fallback_domain = os.getenv("server_domain", "")
    if fallback_domain:
        logger.info(f"Using fallback server_domain: {fallback_domain}")
        return fallback_domain
    
    logger.warning("No SERVER_DOMAIN available - ngrok may not be running")
    return ""