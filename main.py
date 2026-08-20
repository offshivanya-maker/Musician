#!/usr/bin/env python3
"""
Telegram Live Music/Video Stream Bot
Main entry point for the application
"""

import asyncio
import logging
import sys
import signal
from app.config import Config
from app.bot import TelegramBot

logger = logging.getLogger(__name__)


async def main():
    """Main application entry point"""
    try:
        # Load configuration
        config = Config.from_env()
        config.validate()
        
        # Create and run bot
        bot = TelegramBot(config)
        
        # Setup signal handlers for graceful shutdown
        loop = asyncio.get_event_loop()
        for sig in (signal.SIGTERM, signal.SIGINT):
            loop.add_signal_handler(sig, lambda: asyncio.create_task(bot.shutdown()))
        
        await bot.run()
        
    except ValueError as e:
        logger.error(f"Configuration error: {e}")
        sys.exit(1)
    except Exception as e:
        logger.error(f"Fatal error: {e}")
        sys.exit(1)


if __name__ == "__main__":
    asyncio.run(main())
