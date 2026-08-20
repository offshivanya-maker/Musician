import logging
import tempfile
import os
from typing import Optional
from telethon import TelegramClient
from telethon.tl.custom import Message

from app.models import QueueItem, MediaType

logger = logging.getLogger(__name__)


class TelegramMediaManager:
    """Manages Telegram media access and processing"""
    
    def __init__(self, client: TelegramClient):
        self.client = client
        self.temp_files = []
    
    async def get_media_info(self, message: Message) -> Optional[dict]:
        """Extract media information from a message"""
        if not message.media:
            return None
        
        media_info = {
            "message_id": message.id,
            "chat_id": message.chat_id,
            "media_type": MediaType.UNKNOWN,
            "file_name": None,
            "duration": None,
        }
        
        if message.audio:
            media_info["media_type"] = MediaType.AUDIO
            media_info["file_name"] = f"audio_{message.id}.mp3"
            if hasattr(message.audio, "duration"):
                media_info["duration"] = message.audio.duration
        elif message.video:
            media_info["media_type"] = MediaType.VIDEO
            media_info["file_name"] = f"video_{message.id}.mp4"
            if hasattr(message.video, "duration"):
                media_info["duration"] = message.video.duration
        elif message.voice:
            media_info["media_type"] = MediaType.AUDIO
            media_info["file_name"] = f"voice_{message.id}.ogg"
            if hasattr(message.voice, "duration"):
                media_info["duration"] = message.voice.duration
        elif message.document:
            media_info["media_type"] = MediaType.AUDIO
            media_info["file_name"] = f"file_{message.id}.mp3"
        else:
            return None
        
        logger.info(f"Media info extracted: {media_info}")
        return media_info
    
    async def download_temp_media(self, message: Message) -> Optional[str]:
        """Download media to a temporary file"""
        try:
            if not message.media:
                return None
            
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            temp_path = temp_file.name
            temp_file.close()
            
            logger.info(f"Downloading media from message {message.id}")
            await self.client.download_media(
                message.media,
                file=temp_path
            )
            
            self.temp_files.append(temp_path)
            logger.info(f"Media downloaded to: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to download media: {e}")
            return None
    
    def cleanup_temp_files(self):
        """Clean up temporary files"""
        for file_path in self.temp_files:
            try:
                if os.path.exists(file_path):
                    os.unlink(file_path)
                    logger.debug(f"Removed temp file: {file_path}")
            except Exception as e:
                logger.error(f"Failed to remove temp file {file_path}: {e}")
        self.temp_files = []
    
    async def create_queue_item(
        self,
        message: Message,
        position: int,
        added_by: Optional[int] = None
    ) -> Optional[QueueItem]:
        """Create a queue item from a Telegram message"""
        media_info = await self.get_media_info(message)
        if not media_info:
            return None
        
        return QueueItem(
            message_id=media_info["message_id"],
            chat_id=media_info["chat_id"],
            media_type=media_info["media_type"],
            file_name=media_info["file_name"],
            title=media_info.get("title") or media_info["file_name"],
            duration=media_info.get("duration"),
            position=position,
            added_by=added_by,
        )
