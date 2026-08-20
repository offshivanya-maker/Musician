import asyncio
import logging
from typing import Optional
from telethon import TelegramClient
from pytgcalls import PyTgCalls
from pytgcalls.types import (
    MediaStream,
    AudioQuality,
    VideoQuality
)

from app.config import Config
from app.queue_manager import QueueManager
from app.telegram_media import TelegramMediaManager
from app.ffmpeg import FFmpegManager
from app.models import QueueItem, StreamState, MediaType

logger = logging.getLogger(__name__)


class Streamer:
    """Manages the Telegram live stream"""
    
    def __init__(
        self,
        config: Config,
        client: TelegramClient,
        queue_manager: QueueManager,
        media_manager: TelegramMediaManager,
        ffmpeg_manager: FFmpegManager
    ):
        self.config = config
        self.client = client
        self.queue_manager = queue_manager
        self.media_manager = media_manager
        self.ffmpeg_manager = ffmpeg_manager
        self.pytgcalls: Optional[PyTgCalls] = None
        self.is_streaming = False
        self._shutdown_event = asyncio.Event()
        self.current_chat_id = None
        
    async def initialize(self) -> None:
        """Initialize the PyTgCalls streamer"""
        try:
            self.pytgcalls = PyTgCalls(self.client)
            
            @self.pytgcalls.on_stream_end()
            async def on_stream_end(chat_id: int):
                logger.info(f"Stream ended in chat {chat_id}")
                await self._handle_stream_end()
            
            await self.pytgcalls.start()
            logger.info("PyTgCalls initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize PyTgCalls: {e}")
            raise
    
    async def _handle_stream_end(self):
        """Handle stream end event"""
        if not self._shutdown_event.is_set():
            logger.info("Stream ended, playing next track")
            await self.play_next()
    
    async def join_chat(self, chat_id: int) -> bool:
        """Join the target chat voice chat"""
        try:
            if not self.pytgcalls:
                await self.initialize()
            
            self.current_chat_id = chat_id
            await self.pytgcalls.join_group_call(
                chat_id,
                MediaStream(
                    "silent.mp3"
                )
            )
            logger.info(f"Successfully joined chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to join chat: {e}")
            return False
    
    async def play_track(self, item: QueueItem) -> bool:
        """Play a single track"""
        try:
            logger.info(f"Playing track: {item.title}")
            
            message = await self.client.get_messages(item.chat_id, ids=item.message_id)
            if not message:
                logger.error(f"Message {item.message_id} not found")
                return False
            
            media_path = await self.media_manager.download_temp_media(message)
            if not media_path:
                logger.error("Failed to download media")
                return False
            
            await self.queue_manager.set_current(item)
            await self.queue_manager.set_state(StreamState.PLAYING)
            
            is_video = item.media_type == MediaType.VIDEO
            media_stream = MediaStream(
                media_path,
                audio_parameters=AudioQuality.HIGH,
                video_parameters=VideoQuality.HIGH_720p if is_video else None
            )
            
            if self.pytgcalls and self.current_chat_id:
                await self.pytgcalls.change_stream(
                    self.current_chat_id,
                    media_stream
                )
                self.is_streaming = True
                logger.info(f"Now streaming: {item.title}")
                
                asyncio.create_task(self._cleanup_after_play(item))
                return True
            
            return False
            
        except Exception as e:
            logger.error(f"Error playing track: {e}")
            await self.queue_manager.set_state(StreamState.ERROR)
            return False
    
    async def _cleanup_after_play(self, item: QueueItem):
        """Clean up temporary files after playing"""
        await asyncio.sleep(10)
        self.media_manager.cleanup_temp_files()
        await self.queue_manager.set_state(StreamState.IDLE)
        await self.play_next()
    
    async def play_next(self) -> bool:
        """Play the next track in the queue"""
        if self._shutdown_event.is_set():
            return False
        
        next_item = await self.queue_manager.get_next()
        if next_item:
            return await self.play_track(next_item)
        else:
            logger.info("Queue empty, stopping stream")
            await self.stop_stream()
            return False
    
    async def skip_track(self) -> bool:
        """Skip the current track"""
        current = await self.queue_manager.get_current()
        if current:
            logger.info(f"Skipping: {current.title}")
            await self.queue_manager.set_current(None)
        
        if self.pytgcalls and self.current_chat_id:
            try:
                await self.pytgcalls.pause_stream(self.current_chat_id)
            except:
                pass
        
        return await self.play_next()
    
    async def pause_stream(self) -> bool:
        """Pause the current stream"""
        if not self.pytgcalls or not self.is_streaming or not self.current_chat_id:
            return False
        
        try:
            await self.pytgcalls.pause_stream(self.current_chat_id)
            await self.queue_manager.set_state(StreamState.PAUSED)
            logger.info("Stream paused")
            return True
        except Exception as e:
            logger.error(f"Failed to pause stream: {e}")
            return False
    
    async def resume_stream(self) -> bool:
        """Resume the current stream"""
        if not self.pytgcalls or not self.is_streaming or not self.current_chat_id:
            return False
        
        try:
            await self.pytgcalls.resume_stream(self.current_chat_id)
            await self.queue_manager.set_state(StreamState.PLAYING)
            logger.info("Stream resumed")
            return True
        except Exception as e:
            logger.error(f"Failed to resume stream: {e}")
            return False
    
    async def stop_stream(self) -> bool:
        """Stop the current stream"""
        try:
            if self.pytgcalls and self.current_chat_id:
                await self.pytgcalls.leave_group_call(self.current_chat_id)
                logger.info("Left group call")
            
            self.is_streaming = False
            await self.queue_manager.set_current(None)
            await self.queue_manager.set_state(StreamState.STOPPED)
            logger.info("Stream stopped")
            
            await self.ffmpeg_manager.kill_process()
            return True
            
        except Exception as e:
            logger.error(f"Error stopping stream: {e}")
            return False
    
    async def clear_queue(self) -> int:
        """Clear the queue and stop current stream"""
        await self.stop_stream()
        cleared = await self.queue_manager.clear_queue()
        logger.info(f"Cleared {cleared} items from queue")
        return cleared
    
    async def shutdown(self):
        """Shutdown the streamer"""
        self._shutdown_event.set()
        await self.stop_stream()
        
        if self.pytgcalls:
            try:
                await self.pytgcalls.leave_all_group_calls()
                await self.pytgcalls.stop()
                logger.info("PyTgCalls stopped")
            except Exception as e:
                logger.error(f"Error stopping PyTgCalls: {e}")
        
        self.media_manager.cleanup_temp_files()
