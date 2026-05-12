import sys
import os
from telebot import types
from src.core.utils import logger, clean_on_startup, start_cleanup_scheduler, check_ffmpeg_available
from src.core.config import Config
from src.core.loader import bot
from src.services.translation import translation_system

# Import handlers to register them
from src.core.database import init_db, get_user_languages
import src.handlers.admin
import src.handlers.user
import src.handlers.callbacks
import src.handlers.messages

def check_restart():
    """Check if bot restarted and send notification"""
    restart_log = Config.RESTART_LOG
    if restart_log.exists():
        try:
            with open(restart_log, "r", encoding='utf-8') as f: 
                cid = f.read().strip()
                if cid:
                    bot.send_message(int(cid), "✅ <b>تمت إعادة التشغيل التلقائي بنجاح!</b>", parse_mode="HTML")
            restart_log.unlink(missing_ok=True)
        except Exception as e:
            logger.error(f"Restart log error: {e}")

def configure_bot_commands():
    """Set the Telegram command menu entries."""
    try:
        # الأوامر العامة التي ستظهر لجميع المستخدمين
        commands = [
            types.BotCommand("start", "🚀 بدء استخدام البوت"),
            types.BotCommand("help", "🆘 دليل الاستخدام"),
            types.BotCommand("contact", "👨‍💻 مراسلة المطور"),
            types.BotCommand("bots_list", "🤖 قائمة بوتاتنا"),
            types.BotCommand("stats", "📊 إحصائياتي")
        ]
        
        bot.set_my_commands(commands)
        logger.info("Telegram bot command menu configured successfully")
    except Exception as e:
        logger.warning(f"Failed to configure bot commands: {e}")

def main():
    # Initialize Database
    init_db()
    try:
        languages = get_user_languages()
        for uid, lang in languages:
            translation_system.set_language(uid, lang)
        logger.info(f"Loaded {len(languages)} user language preferences")
    except Exception as e:
        logger.warning(f"Failed to load user languages: {e}")
    
    print("==================================================")
    print("      T I T A N   S V   B O T   S Y S T E M")
    print("==================================================")
    print("")

    logger.info("System is initializing...")
    
    # Cleanups
    clean_on_startup()
    start_cleanup_scheduler()

    if not check_ffmpeg_available():
        logger.warning("FFmpeg not found. Audio extraction and mute features will fail.")
    
    # Check restart
    check_restart()
    configure_bot_commands()
    
    logger.info("Bot is online and ready to serve!")
    print("")
    print("==================================================")
    print("           B O T   I S   R U N N I N G")
    print("==================================================")
    print("")

    # Start Polling
    try:
        # skip_pending=True ignores messages sent while bot was offline
        bot.infinity_polling(timeout=30, long_polling_timeout=10, skip_pending=True)
    except Exception as e:
        logger.critical(f"Fatal Error: {e}")
        print(f"Fatal Error: {e}")
        sys.exit(1)

if __name__ == "__main__":
    main()

