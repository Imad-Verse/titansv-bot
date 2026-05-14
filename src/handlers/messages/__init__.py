import re
from telebot import types
from src.core.config import Config
from src.core.loader import bot, BotState
from src.utils.ui import get_error_markup
from src.services.translation import translation_system
from src.services.download import process_download
from src.handlers.user import check_sub
from src.core.database import add_user, is_banned, log_download
from src.core.utils import generate_sid, detect_platform_from_url, logger
import threading

# ريجكس للتحقق من الروابط
URL_PATTERN = re.compile(r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+')

@bot.message_handler(func=lambda m: m.text and not m.text.startswith('/') and URL_PATTERN.search(m.text))
def handle_urls(message):
    uid = message.from_user.id
    
    # 1. التحقق من وضع الصيانة
    if BotState.is_maintenance and uid != Config.ADMIN_ID:
        bot.reply_to(message, translation_system.get(uid, 'maintenance_on'), parse_mode="HTML")
        return

    # Check ban status
    if is_banned(uid):
        bot.reply_to(message, translation_system.get(uid, 'banned_user'), parse_mode="HTML", reply_markup=get_error_markup(uid))
        return

    # 2. التحقق من الاشتراك الإجباري
    not_subbed = check_sub(uid)
    if not_subbed:
        channels_str = "\n".join([f"• {ch}" for ch in not_subbed])
        msg = translation_system.get(uid, 'force_sub_msg', channels=channels_str)
        
        markup = types.InlineKeyboardMarkup()
        for ch in not_subbed:
            clean_ch = ch.strip().replace("@", "")
            markup.add(types.InlineKeyboardButton(f"🔗 {ch}", url=f"https://t.me/{clean_ch}"))
        
        markup.add(types.InlineKeyboardButton(translation_system.get(uid, 'check_sub_btn'), callback_data="check_sub"))
        bot.reply_to(message, msg, parse_mode="HTML", reply_markup=markup)
        return

    # 3. معالجة الرابط
    urls = URL_PATTERN.findall(message.text)
    if urls:
        url = urls[0]
        platform = detect_platform_from_url(url)
        
        if platform not in Config.ALLOWED_PLATFORMS:
            platforms_text = ", ".join([p.title() for p in Config.ALLOWED_PLATFORMS])
            msg = translation_system.get(uid, 'unsupported_platform', platforms=platforms_text)
            bot.reply_to(message, msg, parse_mode="HTML", reply_markup=get_error_markup(uid))
            return
            
        sid = generate_sid("s")
        log_download(uid, url, "pending", platform=platform, sid=sid)
        
        # رسالة جاري المعالجة
        processing_msg = bot.reply_to(
            message, 
            translation_system.get(uid, 'extracting_info', default="🔍 جاري فحص الرابط واستخراج الجودات المتاحة..."),
            parse_mode="HTML"
        )
        
        def async_extract_and_show_keyboard(u, p_msg, s, pform):
            from src.services.download import extract_media_info
            from src.core.utils import get_cookies_path
            
            info = extract_media_info(u, cookies_file=get_cookies_path(pform))
            
            from src.utils.ui import create_quality_keyboard
            markup = create_quality_keyboard(uid, s, info=info)
                


            # تحديث الرسالة بالخيارات الجديدة
            try:
                text = translation_system.get(uid, 'choose_quality')
                if info and info.get('title'):
                    title = info['title']
                    if len(title) > 50: title = title[:47] + "..."
                    text = f"<b>📄 {title}</b>\n\n" + text
                
                bot.edit_message_text(
                    text,
                    p_msg.chat.id,
                    p_msg.message_id,
                    reply_markup=markup,
                    parse_mode="HTML"
                )
            except Exception as e:
                logger.error(f"Failed to update quality keyboard: {e}")

        # تشغيل الاستخراج في ثريد منفصل لعدم حظر البوت
        threading.Thread(target=async_extract_and_show_keyboard, args=(url, processing_msg, sid, platform), daemon=True).start()

@bot.message_handler(func=lambda m: True)
def handle_unknown(message):
    if message.chat.type == 'private' and not message.text.startswith('/'):
        uid = message.from_user.id
        msg = translation_system.get(uid, 'unknown_command')
        bot.reply_to(message, msg, parse_mode="HTML", reply_markup=get_error_markup(uid))
