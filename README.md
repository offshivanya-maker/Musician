# Telegram Live Music/Video Stream Bot

A production-ready Telegram bot that streams audio/video from Telegram messages into a Telegram Group Voice Chat.

## Features

- 🎵 Stream audio files from Telegram messages
- 🎬 Stream video files (audio only due to Telegram API limitations)
- 📋 Queue management with position tracking
- ⏯️ Playback controls (play, pause, resume, skip, stop)
- 📊 Queue display and current track info
- 🔒 Permission-based access control
- 🚀 Ready for Railway deployment
- 🔄 Automatic next-track playback
- 🗑️ Temporary file management (no permanent storage)

## Prerequisites

- Python 3.11+
- FFmpeg installed on the system
- Telegram API credentials (api_id and api_hash)
- Telegram Bot Token from BotFather
- Target Telegram group/channel ID

## Installation

### Local Development

1. Clone the repository:
```bash
git clone https://github.com/yourusername/telegram-stream-bot.git
cd telegram-stream-bot
