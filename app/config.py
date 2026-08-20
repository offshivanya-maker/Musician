import os
from dataclasses import dataclass
from typing import List, Optional


@dataclass
class Config:
    """Application configuration from environment variables"""
    
    # Required
    bot_token: str
    api_id: int
    api_hash: str
    target_chat_id: int
    
    # Optional
    session_string: Optional[str] = None
    admin_user_ids: List[int] = None
    target_live_stream_id: Optional[int] = None
    
    # Defaults
    ffmpeg_path: str = "ffmpeg"
    stream_timeout: int = 300
    max_queue_size: int = 50
    log_level: str = "INFO"
    
    @classmethod
    def from_env(cls) -> "Config":
        """Load configuration from environment variables"""
        
        admin_ids = os.getenv("ADMIN_USER_IDS", "")
        admin_user_ids = []
        if admin_ids:
            admin_user_ids = [int(x.strip()) for x in admin_ids.split(",") if x.strip()]
        
        return cls(
            bot_token=os.getenv("BOT_TOKEN", ""),
            api_id=int(os.getenv("API_ID", 0)),
            api_hash=os.getenv("API_HASH", ""),
            target_chat_id=int(os.getenv("TARGET_CHAT_ID", 0)),
            session_string=os.getenv("SESSION_STRING"),
            admin_user_ids=admin_user_ids,
            target_live_stream_id=os.getenv("TARGET_LIVE_STREAM_ID"),
            ffmpeg_path=os.getenv("FFMPEG_PATH", "ffmpeg"),
            stream_timeout=int(os.getenv("STREAM_TIMEOUT", 300)),
            max_queue_size=int(os.getenv("MAX_QUEUE_SIZE", 50)),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )
    
    def validate(self) -> None:
        """Validate required configuration"""
        missing = []
        if not self.bot_token:
            missing.append("BOT_TOKEN")
        if not self.api_id:
            missing.append("API_ID")
        if not self.api_hash:
            missing.append("API_HASH")
        if not self.target_chat_id:
            missing.append("TARGET_CHAT_ID")
        
        if missing:
            raise ValueError(f"Missing required environment variables: {', '.join(missing)}")
