import logging
from typing import Optional
from telethon import TelegramClient, events
from telethon.tl.custom import Message
from telethon.errors import RPCError

from app.config import Config
from app.queue_manager import QueueManager
from app.telegram_media import TelegramMediaManager
from app.streamer import Streamer
from app.ffmpeg import FFmpegManager
from app.permissions import PermissionManager
from app.models import MediaType, QueueItem, StreamState

logger = logging.getLogger(__name__)


class TelegramBot:
    """Main bot class handling commands and events"""
    
    def __init__(self, config: Config):
        self.config = config
        self.client: Optional[TelegramClient] = None
        self.queue_manager = QueueManager(max_size=config.max_queue_size)
        self.ffmpeg_manager = FFmpegManager(ffmpeg_path=config.ffmpeg_path)
        self.permission_manager = PermissionManager(config)
        
        # Initialize managers (will be set after client init)
        self.media_manager = None
        self.streamer = None
        
        # Command handlers
        self.commands = {
            "/play": self._handle_play,
            "/skip": self._handle_skip,
            "/stop": self._handle_stop,
            "/pause": self._handle_pause,
            "/resume": self._handle_resume,
            "/queue": self._handle_queue,
            "/now": self._handle_now,
            "/clear": self._handle_clear,
            "/help": self._handle_help,
        }
        
        self._setup_logging()
    
    def _setup_logging(self):
        """Setup logging configuration"""
        logging.basicConfig(
            level=getattr(logging, self.config.log_level),
            format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
            datefmt='%Y-%m-%d %H:%M:%S'
        )
    
    async def initialize(self):
        """Initialize the bot and all components"""
        try:
            # Create Telegram client (user account for streaming)
            self.client = TelegramClient(
                "bot_session",
                self.config.api_id,
                self.config.api_hash
            )
            
            # Start client
            if self.config.session_string:
                await self.client.start(session_string=self.config.session_string)
            else:
                await self.client.start()
            
            logger.info("Telegram client started")
            
            # Initialize managers
            self.media_manager = TelegramMediaManager(self.client)
            self.streamer = Streamer(
                self.config,
                self.client,
                self.queue_manager,
                self.media_manager,
                self.ffmpeg_manager
            )
            
            # Initialize streamer
            await self.streamer.initialize()
            
            # Join target chat
            await self.streamer.join_chat(self.config.target_chat_id)
            
            # Register event handlers
            self._register_handlers()
            
            logger.info("Bot initialized successfully")
            
        except Exception as e:
            logger.error(f"Failed to initialize bot: {e}")
            raise
    
    def _register_handlers(self):
        """Register message and command handlers"""
        
        @self.client.on(events.NewMessage)
        async def handle_messages(event):
            await self._handle_message(event)
    
    async def _handle_message(self, event):
        """Handle incoming messages"""
        message = event.message
        if not message or not message.text:
            return
        
        # Check if it's a command
        if message.text.startswith("/"):
            command = message.text.split()[0].lower()
            if command in self.commands:
                await self._execute_command(command, event)
                return
            
            # Handle file message with /play reply
            if command == "/play" and event.is_reply:
                reply_msg = await event.get_reply_message()
                if reply_msg and reply_msg.media:
                    await self._handle_play_reply(event, reply_msg)
                    return
        
        # Handle media messages (auto-add to queue)
        elif message.media:
            await self._handle_media_message(event)
    
    async def _execute_command(self, command: str, event):
        """Execute a bot command"""
        try:
            # Check if user has permission for control commands
            control_commands = ["/skip", "/stop", "/pause", "/resume", "/clear"]
            if command in control_commands:
                if not self.permission_manager.can_control_stream(event.sender_id):
                    await event.reply("❌ You don't have permission to use this command.")
                    return
            
            handler = self.commands.get(command)
            if handler:
                await handler(event)
            
        except Exception as e:
            logger.error(f"Error executing command {command}: {e}")
            await event.reply(f"❌ Error: {str(e)}")
    
    async def _handle_play(self, event):
        """Handle /play command"""
        # Check if replying to a media message
        if event.is_reply:
            reply_msg = await event.get_reply_message()
            if reply_msg and reply_msg.media:
                await self._handle_play_reply(event, reply_msg)
                return
        
        # Check if command has arguments (file name)
        args = event.text.split()[1:] if len(event.text.split()) > 1 else []
        if args:
            # Search for media by name (not implemented)
            await event.reply("❌ Please reply to a media message with /play")
            return
        
        await event.reply("❌ Please reply to a media message with /play")
    
    async def _handle_play_reply(self, event, reply_msg: Message):
        """Handle /play command with reply to media"""
        try:
            # Extract media info
            media_info = await self.media_manager.get_media_info(reply_msg)
            if not media_info:
                await event.reply("❌ Unsupported media type or no media found.")
                return
            
            # Create queue item
            position = await self.queue_manager.get_queue_size() + 1
            item = await self.media_manager.create_queue_item(
                reply_msg,
                position,
                event.sender_id
            )
            
            if not item:
                await event.reply("❌ Failed to process media.")
                return
            
            # Add to queue
            await self.queue_manager.add_item(item)
            
            # Start streaming if not already playing
            state = await self.queue_manager.get_state()
            if state == StreamState.IDLE or state == StreamState.STOPPED:
                # Start playing immediately
                asyncio.create_task(self.streamer.play_next())
                await event.reply(f"🎵 Playing: {item.title}")
            else:
                await event.reply(f"🎵 Added to queue: {item.title}\nPosition: #{position}")
            
        except Exception as e:
            logger.error(f"Error handling play reply: {e}")
            await event.reply(f"❌ Error: {str(e)}")
    
    async def _handle_media_message(self, event):
        """Handle media messages (auto-add to queue)"""
        try:
            # Check if media is supported
            message = event.message
            media_info = await self.media_manager.get_media_info(message)
            if not media_info:
                return
            
            # Add to queue
            position = await self.queue_manager.get_queue_size() + 1
            item = await self.media_manager.create_queue_item(
                message,
                position,
                event.sender_id
            )
            
            if not item:
                return
            
            await self.queue_manager.add_item(item)
            
            # Start streaming if not already playing
            state = await self.queue_manager.get_state()
            if state == StreamState.IDLE or state == StreamState.STOPPED:
                asyncio.create_task(self.streamer.play_next())
                await event.reply(f"🎵 Playing: {item.title}")
            else:
                await event.reply(f"🎵 Added to queue: {item.title}\nPosition: #{position}")
            
        except Exception as e:
            logger.error(f"Error handling media message: {e}")
    
    async def _handle_skip(self, event):
        """Handle /skip command"""
        try:
            current = await self.queue_manager.get_current()
            if not current:
                await event.reply("❌ No track is currently playing.")
                return
            
            await self.streamer.skip_track()
            new_current = await self.queue_manager.get_current()
            if new_current:
                await event.reply(f"⏭️ Skipped {current.title}\n▶️ Playing {new_current.title}")
            else:
                await event.reply(f"⏭️ Skipped {current.title}")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def _handle_stop(self, event):
        """Handle /stop command"""
        try:
            await self.streamer.stop_stream()
            await event.reply("⏹️ Stream stopped.")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def _handle_pause(self, event):
        """Handle /pause command"""
        try:
            if await self.streamer.pause_stream():
                await event.reply("⏸️ Stream paused.")
            else:
                await event.reply("❌ Failed to pause stream.")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def _handle_resume(self, event):
        """Handle /resume command"""
        try:
            if await self.streamer.resume_stream():
                await event.reply("▶️ Stream resumed.")
            else:
                await event.reply("❌ Failed to resume stream.")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def _handle_queue(self, event):
        """Handle /queue command"""
        try:
            queue_info = await self.queue_manager.get_queue_info()
            await event.reply(queue_info)
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def _handle_now(self, event):
        """Handle /now command"""
        try:
            current = await self.queue_manager.get_current()
            if current:
                await event.reply(f"🎵 Now Playing: {current.title}")
            else:
                await event.reply("❌ No track currently playing.")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def _handle_clear(self, event):
        """Handle /clear command"""
        try:
            await self.streamer.clear_queue()
            await event.reply("🗑️ Queue cleared.")
        except Exception as e:
            await event.reply(f"❌ Error: {str(e)}")
    
    async def _handle_help(self, event):
        """Handle /help command"""
        help_text = """
🤖 **Telegram Live Stream Bot**

Available commands:
/play - Play media (reply to media message)
/skip - Skip current track
/stop - Stop playback
/pause - Pause playback
/resume - Resume playback
/queue - View queue
/now - View current track
/clear - Clear queue
/help - Show this help

**How to use:**
- Send an audio/video file to add to queue
- Reply to a media message with /play
- Admin controls: stop, skip, pause, resume, clear
"""
        await event.reply(help_text)
    
    async def run(self):
        """Run the bot"""
        try:
            logger.info("Starting bot...")
            await self.initialize()
            await self.client.run_until_disconnected()
        except KeyboardInterrupt:
            logger.info("Bot stopped by user")
        except Exception as e:
            logger.error(f"Bot error: {e}")
            raise
        finally:
            await self.shutdown()
    
    async def shutdown(self):
        """Shutdown the bot"""
        logger.info("Shutting down bot...")
        if self.streamer:
            await self.streamer.shutdown()
        if self.client:
            await self.client.disconnect()
        logger.info("Bot shutdown complete")
