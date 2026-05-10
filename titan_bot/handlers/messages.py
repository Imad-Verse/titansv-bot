from telebot import types
from titan_bot.core.loader import bot, get_error_markup
import titan_bot.core.loader as loader
from titan_bot.core.config import ADMIN_ID, ALLOWED_PLATFORMS
from titan_bot.services.translation import translation_system
from titan_bot.handlers.user import check_sub
from titan_bot.core.utils import check_disk_space, detect_platform_from_url, generate_sid
from titan_bot.core.database import log_download, is_banned, add_user
import re

@bot.message_handler(func=lambda m: True, content_types=['text'])
def handle_message(message):
    uid = message.from_user.id
    
    # تجاهل الأوامر (تمت معالجتها بالفعل)
    if message.text.startswith('/'): return
    
    # تحقق من الصيانة
    if loader.MAINTENANCE_MODE and uid != ADMIN_ID:
        bot.reply_to(message, translation_system.get(uid, 'maintenance_mode'), parse_mode="HTML", reply_markup=get_error_markup(uid))
        return

    # Check ban status
    if is_banned(uid):
        bot.reply_to(message, translation_system.get(uid, 'banned_user'), parse_mode="HTML", reply_markup=get_error_markup(uid))
        return

    # استخراج الرابط من النص
    url_pattern = r'http[s]?://(?:[a-zA-Z]|[0-9]|[$-_@.&+]|[!*\\(\\),]|(?:%[0-9a-fA-F][0-9a-fA-F]))+'
    match = re.search(url_pattern, message.text)
    
    # إذا لم يوجد رابط، تجاهل الرسالة تماماً (صمت)
    if not match:
        return
        
    url = match.group(0)

    # تسجيل المستخدم عند أول رابط
    add_user(uid, message.from_user.username or "None", message.from_user.first_name or "User")

    # تحقق من الاشتراك
    not_subs = check_sub(uid)
    if not_subs:
        markup = types.InlineKeyboardMarkup()
        for ch in not_subs:
            markup.add(types.InlineKeyboardButton(f"اشترك في {ch}", url=f"https://t.me/{ch.replace('@', '')}"))
        markup.add(types.InlineKeyboardButton("تحقق من الاشتراك 🔄", callback_data="verify_sub"))
        
        bot.send_message(message.chat.id, translation_system.get(uid, 'need_subscription'), reply_markup=markup, parse_mode="HTML")
        return

    # فحص مساحة التخزين
    has_space, free_gb = check_disk_space(min_gb=1)
    if not has_space:
        bot.reply_to(
            message,
            translation_system.get(uid, 'storage_low', free_gb=free_gb),
            parse_mode="HTML",
            reply_markup=get_error_markup(uid)
        )
        return

    # عرض خيارات الجودة
    markup = types.InlineKeyboardMarkup()
    platform = detect_platform_from_url(url)
    if platform not in ALLOWED_PLATFORMS:
        if platform == 'other':
            failure_key = 'invalid_link'
            reply_text = translation_system.get(uid, failure_key)
        else:
            failure_key = 'unsupported_platform'
            platforms_text = ", ".join([p.title() for p in ALLOWED_PLATFORMS])
            reply_text = translation_system.get(uid, failure_key, platforms=platforms_text)

        bot.reply_to(
            message,
            reply_text,
            parse_mode="HTML",
            reply_markup=get_error_markup(uid)
        )
        log_download(uid, url, "failed", platform=platform, error_reason=failure_key)
        return
    
    # تحويل الرابط إلى SID لتجنب تجاوز 64 حرف في بيانات الأزرار
    sid = generate_sid("s")
    log_download(uid, url, "pending", platform=platform, sid=sid, error_reason="")
    
    markup.row(
        types.InlineKeyboardButton("🎬 جودة عالية 720+", callback_data=f"dl_high|{sid}"),
        types.InlineKeyboardButton("🎥 جودة متوسطة 480", callback_data=f"dl_medium|{sid}")
    )
    markup.row(
        types.InlineKeyboardButton("📱 جودة منخفضة 360", callback_data=f"dl_low|{sid}"),
        types.InlineKeyboardButton("🎵 تحميل صوت فقط", callback_data=f"dl_audio|{sid}")
    )
    
    # رسالة اختيار الجودة (تم التحسين للرد على الرسالة الأصلية لسهولة التتبع)
    bot.reply_to(
        message, 
        translation_system.get(uid, 'choose_quality'), 
        reply_markup=markup, 
        parse_mode="HTML"
    )
