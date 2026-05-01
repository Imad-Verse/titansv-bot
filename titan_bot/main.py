import sys
import os
from telebot import types
from titan_bot.core.utils import logger, clean_on_startup, start_cleanup_scheduler, check_ffmpeg_available
from titan_bot.core.config import RESTART_LOG, ADMIN_ID
from titan_bot.core.loader import bot
from titan_bot.services.translation import translation_system

# Import handlers to register them
from titan_bot.core.database import init_db, get_user_languages
import titan_bot.handlers.admin
import titan_bot.handlers.user
import titan_bot.handlers.callbacks
import titan_bot.handlers.messages

def check_restart():
    """Check if bot restarted and send notification"""
    if os.path.exists(RESTART_LOG):
        try:
            with open(RESTART_LOG, "r", encoding='utf-8') as f: 
                cid = int(f.read())
            bot.send_message(cid, "✅ <b>تمت إعادة التشغيل التلقائي بنجاح!</b>", parse_mode="HTML")
            os.remove(RESTART_LOG)
        except Exception as e:
            logger.error(f"Restart log error: {e}")

def configure_bot_commands():
    """Set the Telegram command menu entries."""
    try:
        # الأوامر العامة التي ستظهر لجميع المستخدمين
        commands = [
            types.BotCommand("start", "🚀 بدء استخدام البوت"),
            types.BotCommand("help", "🆘 دليل الاستخدام"),
            types.BotCommand("language", "🌍 تغيير اللغة"),
            types.BotCommand("contact", "👨‍💻 مراسلة المطور"),
            types.BotCommand("bots_list", "🤖 قائمة بوتاتنا")
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
    print("   🤖  T I T A N   S V   B O T   S Y S T E M  🤖")
    print("==================================================")
    print("")

    logger.info("🚀 System is initializing...")
    
    # Cleanups
    clean_on_startup()
    start_cleanup_scheduler()

    if not check_ffmpeg_available():
        logger.warning("FFmpeg not found. Audio extraction and mute features will fail.")
    
    # Check restart
    check_restart()
    configure_bot_commands()
    
    logger.info("✅ Bot is online and ready to serve!")
    print("")
    print("==================================================")
    print("      ✅  B O T   I S   R U N N I N G  ✅")
    print("==================================================")
    print("")

    # Start Polling
    try:
        # skip_pending=True ignores messages sent while bot was offline
        bot.infinity_polling(timeout=30, long_polling_timeout=10, skip_pending=True)
    except Exception as e:
        logger.critical(f"Fatal Error: {e}")
        print(f"Fatal Error: {e}")
        # Optional: Auto-restart logic here or just exit
        sys.exit(1)

if __name__ == "__main__":
    main()
