from telebot import types
from urllib.parse import quote
from titan_bot.core.config import BOT_SIG, CHANNELS, ADMIN_ID, TELEGRAM_UPLOAD_LIMIT_MB
from titan_bot.core.loader import bot, BOT_USERNAME
from titan_bot.services.translation import translation_system
from titan_bot.core.database import add_user
from titan_bot.core.utils import logger

LEGACY_KEYBOARD_CLEARED = set()

def check_sub(user_id):
    """التحقق من الاشتراك في القنوات"""
    not_subscribed = []
    for channel in CHANNELS:
        try:
            # تنظيف اسم القناة
            clean_channel = channel.strip()
            if not clean_channel.startswith("@"): 
                continue # تخطي القنوات غير الصالحة
                
            status = bot.get_chat_member(clean_channel, user_id).status
            if status not in ['member', 'administrator', 'creator']:
                not_subscribed.append(clean_channel)
        except Exception as e:
            # في حالة خطأ (مثل البوت ليس مشرفاً)، نعتبر المستخدم مشتركاً لتجنب تعطيل البوت
            logger.warning(f"Subscription check error for {channel}: {e}")
            continue
    return not_subscribed

def create_main_markup(user_id, is_admin=False):
    markup = types.InlineKeyboardMarkup(row_width=2)
    
    start_btn = translation_system.get(user_id, 'main_menu_buttons', key='start_download')
    help_btn = translation_system.get(user_id, 'main_menu_buttons', key='help')
    lang_btn = translation_system.get(user_id, 'main_menu_buttons', key='language')
    contact_btn = translation_system.get(user_id, 'main_menu_buttons', key='contact')
    bots_list_btn = translation_system.get(user_id, 'main_menu_buttons', key='bots_list')
    
    share_msg = translation_system.get(user_id, 'share_message', bot_username=BOT_USERNAME or "bot")
    share_url = f"https://t.me/share/url?url=https://t.me/{BOT_USERNAME or ''}&text={quote(share_msg)}"
    markup.row(
        types.InlineKeyboardButton(start_btn, url=share_url),
        types.InlineKeyboardButton(lang_btn, callback_data="menu_language")
    )
    markup.row(
        types.InlineKeyboardButton(help_btn, callback_data="menu_help"),
        types.InlineKeyboardButton(contact_btn, callback_data="menu_contact")
    )
    markup.row(
        types.InlineKeyboardButton(bots_list_btn, callback_data="menu_bots_list")
    )
    
    if is_admin:
        admin_btn = translation_system.get(user_id, 'main_menu_buttons', key='admin_panel')
        markup.add(types.InlineKeyboardButton(admin_btn, callback_data="menu_admin_panel"))
        
    return markup

def clear_legacy_keyboard(chat_id):
    if chat_id in LEGACY_KEYBOARD_CLEARED:
        return

    try:
        cleanup_message = bot.send_message(chat_id, "…", reply_markup=types.ReplyKeyboardRemove())
        try:
            bot.delete_message(chat_id, cleanup_message.message_id)
        except Exception:
            pass
        LEGACY_KEYBOARD_CLEARED.add(chat_id)
    except Exception as e:
        logger.debug(f"Legacy keyboard cleanup skipped for chat {chat_id}: {e}")

def send_main_menu(chat_id, user_id, username=None, first_name=None):
    add_user(user_id, username or "None", first_name or "User")
    clear_legacy_keyboard(chat_id)

    is_admin = (user_id == ADMIN_ID)
    start_text = translation_system.get(user_id, 'start_message', bot_sig=BOT_SIG)

    bot.send_message(
        chat_id,
        start_text,
        parse_mode="HTML",
        reply_markup=create_main_markup(user_id, is_admin)
    )

@bot.message_handler(commands=['start'])
def start_command(message):
    uid = message.from_user.id
    fname = message.from_user.first_name or "User"
    username = message.from_user.username or "None"
    send_main_menu(message.chat.id, uid, username, fname)

@bot.message_handler(commands=['help', 'مساعدة'])
def help_command(message):
    uid = message.from_user.id
    fname = message.from_user.first_name or "User"
    username = message.from_user.username or "None"
    add_user(uid, username, fname)
    
    # إعداد نص القنوات
    channels_text = "\n".join([f"• {ch}" for ch in CHANNELS])
    
    help_title = translation_system.get(uid, 'help_title')
    help_message = translation_system.get(
        uid,
        'help_message',
        bot_name="العملاق للتحميل",
        channels=channels_text,
        max_size=TELEGRAM_UPLOAD_LIMIT_MB
    )
    if uid != ADMIN_ID:
        help_message = "\n".join(
            line for line in help_message.splitlines()
            if '/boss' not in line and '/admin' not in line
        )
    
    # أزرار الروابط (القنوات في سطر واحد والمطور في سطر منفصل)
    markup = types.InlineKeyboardMarkup()
    
    channel_btns = []
    for ch in CHANNELS:
        clean_ch = ch.strip().replace("@", "")
        channel_btns.append(types.InlineKeyboardButton(f"🔗 {ch}", url=f"https://t.me/{clean_ch}"))
    
    if channel_btns:
        markup.row(*channel_btns)
        
    dev_text = translation_system.get(uid, 'contact_dev')
    markup.row(types.InlineKeyboardButton(dev_text, url="https://t.me/abulharith_imad"))
        
    bot.send_message(message.chat.id, f"{help_title}\n\n{help_message}", parse_mode="HTML", reply_markup=markup)

@bot.message_handler(commands=['language', 'lang', 'اللغة'])
def language_command(message):
    uid = message.from_user.id
    add_user(uid, message.from_user.username, message.from_user.first_name)
    
    select_text = translation_system.get(uid, 'select_language')
    
    markup = types.InlineKeyboardMarkup(row_width=3)
    markup.add(
        types.InlineKeyboardButton("العربية 🇸🇦", callback_data="lang_ar"),
        types.InlineKeyboardButton("English 🇺🇸", callback_data="lang_en"),
        types.InlineKeyboardButton("Français 🇫🇷", callback_data="lang_fr")
    )
    
    bot.send_message(message.chat.id, select_text, parse_mode="HTML", reply_markup=markup)

# Button Handlers
@bot.message_handler(func=lambda m: m.text in ["📢 مشاركة البوت", "📢 Share Bot", "📢 Partager le bot", "مشاركة البوت"])
def start_download_button(message):
    start_command(message)

@bot.message_handler(func=lambda m: m.text in ["🆘 المساعدة", "🆘 Help", "🆘 Aide", "مساعدة"])
def help_button(message):
    help_command(message)

@bot.message_handler(func=lambda m: m.text in ["🌍 تغيير اللغة", "🌍 Change Language", "🌍 Changer Langue", "تغيير اللغة"])
def language_button(message):
    language_command(message)

@bot.message_handler(commands=['contact', 'المطور'])
@bot.message_handler(func=lambda m: m.text in ["👨‍💻 المطور", "👨‍💻 Developer", "👨‍💻 Développeur", "راسل المطور"])
def contact_button(message):
    uid = message.from_user.id
    contact_text = translation_system.get(uid, 'contact_dev')
    
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(contact_text, url="https://t.me/abulharith_imad"))
    
    bot.send_message(
        message.chat.id,
        f"📞 <b>{contact_text}</b>\n\nللتحدث مع المطور بشكل مباشر:\n\n👉 @abulharith_imad",
        parse_mode="HTML",
        reply_markup=markup
    )

@bot.message_handler(commands=['bots_list', 'قائمة_بوتاتنا'])
@bot.message_handler(func=lambda m: m.text in ["🤖 قائمة بوتاتنا", "🤖 Our Bots List", "🤖 Nos Bots", "قائمة بوتاتنا"])
def bots_list_command(message):
    uid = message.from_user.id
    bots_text = translation_system.get(uid, 'bots_list_text')
    contact_text = translation_system.get(uid, 'contact_dev')
    main_menu_text = translation_system.get(uid, 'main_menu')
    
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(contact_text, url="https://t.me/abulharith_imad"),
        types.InlineKeyboardButton(main_menu_text, callback_data="menu_back_to_main")
    )
    
    bot.send_message(message.chat.id, bots_text, parse_mode="HTML", reply_markup=markup)
