import logging
import tempfile
from typing import Optional, Tuple
from telethon import TelegramClient
from telethon.tl.types import (
    MessageMediaDocument, MessageMediaPhoto, Document,
    TypeMessageMedia, TypeDocument
)
from telethon.tl.custom import Message
import os

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
        
        # Check media type
        if message.audio:
            media_info["media_type"] = MediaType.AUDIO
            media_info["file_name"] = message.audio.attributes[0].title or f"audio_{message.id}"
            if hasattr(message.audio, "duration"):
                media_info["duration"] = message.audio.duration
        elif message.video:
            media_info["media_type"] = MediaType.VIDEO
            media_info["file_name"] = message.video.attributes[0].title or f"video_{message.id}"
            if hasattr(message.video, "duration"):
                media_info["duration"] = message.video.duration
        elif message.document:
            media_info["media_type"] = MediaType.AUDIO  # Assume audio file
            media_info["file_name"] = message.document.attributes[0].title or f"file_{message.id}"
        elif message.voice:
            media_info["media_type"] = MediaType.AUDIO
            media_info["file_name"] = f"voice_{message.id}"
            if hasattr(message.voice, "duration"):
                media_info["duration"] = message.voice.duration
        elif message.video_note:
            media_info["media_type"] = MediaType.VIDEO
            media_info["file_name"] = f"video_note_{message.id}"
        else:
            # Try to detect from document
            if message.media:
                if isinstance(message.media, MessageMediaDocument):
                    doc = message.media.document
                    if doc:
                        # Check mime type
                        mime_type = getattr(doc, "mime_type", "")
                        if mime_type and mime_type.startswith("audio/"):
                            media_info["media_type"] = MediaType.AUDIO
                        elif mime_type and mime_type.startswith("video/"):
                            media_info["media_type"] = MediaType.VIDEO
                        # Get file name
                        for attr in doc.attributes:
                            if hasattr(attr, "title"):
                                media_info["file_name"] = attr.title
                                break
                    else:
                        return None
        
        # Default file name if not set
        if not media_info["file_name"]:
            media_info["file_name"] = f"{media_info['media_type'].value}_{message.id}"
        
        # Ensure file name has extension
        if not self._has_extension(media_info["file_name"]):
            ext = self._get_extension_for_type(media_info["media_type"])
            media_info["file_name"] += ext
        
        logger.info(f"Media info extracted: {media_info}")
        return media_info
    
    def _has_extension(self, filename: str) -> bool:
        """Check if filename has an extension"""
        return "." in filename
    
    def _get_extension_for_type(self, media_type: MediaType) -> str:
        """Get default extension for media type"""
        if media_type == MediaType.AUDIO:
            return ".mp3"
        elif media_type == MediaType.VIDEO:
            return ".mp4"
        return ".bin"
    
    async def download_temp_media(self, message: Message) -> Optional[str]:
        """Download media to a temporary file"""
        try:
            if not message.media:
                return None
            
            # Create temp file
            temp_file = tempfile.NamedTemporaryFile(delete=False, suffix=".mp4")
            temp_path = temp_file.name
            temp_file.close()
            
            # Download media
            logger.info(f"Downloading media from message {message.id}")
            await self.client.download_media(
                message.media,
                file=temp_path,
                progress_callback=self._download_progress_callback
            )
            
            self.temp_files.append(temp_path)
            logger.info(f"Media downloaded to: {temp_path}")
            return temp_path
            
        except Exception as e:
            logger.error(f"Failed to download media: {e}")
            return None
    
    def _download_progress_callback(self, current: int, total: int):
        """Callback for download progress"""
        if total > 0:
            progress = (current / total) * 100
            if progress % 10 < 0.1:  # Log every 10%
                logger.debug(f"Download progress: {progress:.1f}%")
    
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
            title=media_info.get("title"),
            duration=media_info.get("duration"),
            position=position,
            added_by=added_by,
        )
