import re
from telebot import types
from src.core.config import Config
from src.core.loader import bot, BotState
from src.utils.ui import get_error_markup
from src.services.translation import translation_system
from src.services.download import process_download
from src.handlers.user import check_sub
from src.core.database import add_user, is_banned, log_download
from src.core.utils import generate_sid, detect_platform_from_url

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
        
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("🎬 جودة عالية 720+", callback_data=f"dl_high|{sid}"),
            types.InlineKeyboardButton("🎥 جودة متوسطة 480", callback_data=f"dl_medium|{sid}")
        )
        markup.row(
            types.InlineKeyboardButton("📱 جودة منخفضة 360", callback_data=f"dl_low|{sid}"),
            types.InlineKeyboardButton("🎵 تحميل صوت فقط", callback_data=f"audio_{sid}")
        )
        
        if platform == 'youtube' and ('list=' in url or 'playlist' in url):
            markup.row(
                types.InlineKeyboardButton("📂 تحميل القائمة كاملة", callback_data=f"playlist_{sid}")
            )
        
        bot.reply_to(
            message, 
            translation_system.get(uid, 'choose_quality'), 
            reply_markup=markup, 
            parse_mode="HTML"
        )

@bot.message_handler(func=lambda m: True)
def handle_unknown(message):
    if message.chat.type == 'private' and not message.text.startswith('/'):
        uid = message.from_user.id
        msg = translation_system.get(uid, 'unknown_command')
        bot.reply_to(message, msg, parse_mode="HTML", reply_markup=get_error_markup(uid))
