# 🤖 Titan Downloader Bot

A professional Telegram bot for downloading high-quality videos and audio from various social media platforms.

## ⚡ Features

- **Multi-platform Support**: YouTube, TikTok, Facebook, Instagram, Pinterest, Twitter (X), Snapchat, Threads.
- **High Quality**: Supports resolutions up to 1080p and beyond.
- **Audio Extraction**: Convert any video to high-quality MP3.
- **Video Muting**: Download videos without sound.
- **Progress Tracking**: Real-time progress bar during download and upload.
- **Multi-language**: Fully supports Arabic, English, and French.
- **Admin Panel**: Comprehensive dashboard for bot management and statistics.
- **Forced Subscription**: Option to require users to join specific channels.

## 🏗 Project Structure

```text
TitanSv_bot/
├── data/               # SQLite database and backups
├── logs/               # Bot and system logs
├── cookies/            # Cookies for platform authentication
├── src/                # Core source code
│   ├── core/           # Configuration and database engine
│   ├── handlers/       # Categorized Telegram handlers
│   ├── services/       # External services (yt-dlp integration)
│   └── utils/          # Utility helper functions
├── .env                # Environment variables
├── requirements.txt    # Python dependencies
└── run.py              # Main entry point
```

## 🚀 Setup & Installation

1. **Clone the repository**:
   ```bash
   git clone <repository-url>
   cd TitanSv_bot
   ```

2. **Install dependencies**:
   ```bash
   pip install -r requirements.txt
   ```

3. **Configure Environment Variables**:
   Create a `.env` file based on the provided template and add your `TELEGRAM_BOT_TOKEN` and `ADMIN_ID`.

4. **Install FFmpeg**:
   Ensure `ffmpeg` is installed on your system and added to your PATH.

5. **Run the bot**:
   ```bash
   python run.py
   ```

## 👨‍💻 Developer

- **Imad** - [@abulharith_imad](https://t.me/abulharith_imad)

## ⚠️ Disclaimer

This bot is intended for personal use and downloading content you have permission to access. Please respect the copyrights and terms of service of the respective platforms.
