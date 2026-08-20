import asyncio
import logging
from typing import Optional
from telethon import TelegramClient
from pytgcalls import GroupCallFactory
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
        self.group_call = None
        self.is_streaming = False
        self._shutdown_event = asyncio.Event()
        self._current_stream_task: Optional[asyncio.Task] = None
        
    async def initialize(self) -> None:
        """Initialize the PyTgCalls streamer"""
        try:
            # Create group call factory
            self.group_call = GroupCallFactory(
                self.client,
                GroupCallFactory.MTProto()
            ).get_file_group_call()
            
            # Set up event handlers
            self.group_call.add_handler(self._on_stream_end, "stream_end")
            
            logger.info("PyTgCalls initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize PyTgCalls: {e}")
            raise
    
    async def _on_stream_end(self, event):
        """Handle stream end event"""
        logger.info(f"Stream ended: {event}")
        if not self._shutdown_event.is_set():
            await self.play_next()
    
    async def join_chat(self, chat_id: int) -> bool:
        """Join the target chat voice chat"""
        try:
            if not self.group_call:
                await self.initialize()
            
            # Join the chat
            logger.info(f"Joining chat {chat_id}")
            await self.group_call.start(chat_id)
            logger.info(f"Successfully joined chat {chat_id}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to join chat: {e}")
            return False
    
    async def play_track(self, item: QueueItem) -> bool:
        """Play a single track"""
        try:
            logger.info(f"Playing track: {item.title}")
            
            # Download media to temporary file
            message = await self.client.get_messages(item.chat_id, ids=item.message_id)
            if not message:
                logger.error(f"Message {item.message_id} not found")
                return False
            
            media_path = await self.media_manager.download_temp_media(message)
            if not media_path:
                logger.error("Failed to download media")
                return False
            
            # Update current track
            await self.queue_manager.set_current(item)
            await self.queue_manager.set_state(StreamState.PLAYING)
            
            # Create media stream
            is_video = item.media_type == MediaType.VIDEO
            await self.group_call.play(
                media_path,
                audio_quality=AudioQuality.HIGH,
                video_quality=VideoQuality.HIGH_720p if is_video else None
            )
            
            self.is_streaming = True
            logger.info(f"Now streaming: {item.title}")
            
            # Clean up temp file after playing
            asyncio.create_task(self._cleanup_after_play(item))
            return True
            
        except Exception as e:
            logger.error(f"Error playing track: {e}")
            await self.queue_manager.set_state(StreamState.ERROR)
            return False
    
    async def _cleanup_after_play(self, item: QueueItem):
        """Clean up temporary files after playing"""
        # Wait a bit before cleanup
        await asyncio.sleep(10)
        self.media_manager.cleanup_temp_files()
        await self.queue_manager.set_state(StreamState.IDLE)
    
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
        
        # Stop current stream
        if self.group_call:
            try:
                await self.group_call.pause()
            except:
                pass
        
        # Play next
        return await self.play_next()
    
    async def pause_stream(self) -> bool:
        """Pause the current stream"""
        if not self.group_call or not self.is_streaming:
            return False
        
        try:
            await self.group_call.pause()
            await self.queue_manager.set_state(StreamState.PAUSED)
            logger.info("Stream paused")
            return True
        except Exception as e:
            logger.error(f"Failed to pause stream: {e}")
            return False
    
    async def resume_stream(self) -> bool:
        """Resume the current stream"""
        if not self.group_call or not self.is_streaming:
            return False
        
        try:
            await self.group_call.resume()
            await self.queue_manager.set_state(StreamState.PLAYING)
            logger.info("Stream resumed")
            return True
        except Exception as e:
            logger.error(f"Failed to resume stream: {e}")
            return False
    
    async def stop_stream(self) -> bool:
        """Stop the current stream"""
        try:
            if self.group_call:
                # Stop the stream
                await self.group_call.stop()
                logger.info("Stream stopped")
            
            self.is_streaming = False
            await self.queue_manager.set_current(None)
            await self.queue_manager.set_state(StreamState.STOPPED)
            
            # Clean up FFmpeg process
            await self.ffmpeg_manager.kill_process()
            
            return True
            
        except Exception as e:
            logger.error(f"Error stopping stream: {e}")
            return False
    
    async def clear_queue(self) -> int:
        """Clear the queue and stop current stream"""
        # Stop current stream
        await self.stop_stream()
        
        # Clear queue
        cleared = await self.queue_manager.clear_queue()
        logger.info(f"Cleared {cleared} items from queue")
        return cleared
    
    async def shutdown(self):
        """Shutdown the streamer"""
        self._shutdown_event.set()
        
        if self._current_stream_task:
            self._current_stream_task.cancel()
            try:
                await self._current_stream_task
            except asyncio.CancelledError:
                pass
        
        await self.stop_stream()
        
        if self.group_call:
            try:
                await self.group_call.stop()
                logger.info("Group call stopped")
            except Exception as e:
                logger.error(f"Error stopping group call: {e}")
        
        self.media_manager.cleanup_temp_files()
