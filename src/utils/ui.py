from telebot import types
from src.services.translation import translation_system

def get_error_markup(user_id):
    """إنشاء أزرار المساعدة والمراسلة عند حدوث خطأ"""
    markup = types.InlineKeyboardMarkup()
    
    help_text = translation_system.get(user_id, 'main_menu_buttons', key='help')
    contact_text = translation_system.get(user_id, 'contact_dev')
    
    markup.row(
        types.InlineKeyboardButton(help_text, callback_data="menu_help"),
        types.InlineKeyboardButton(contact_text, url="https://t.me/abulharith_imad")
    )
    return markup

def create_quality_keyboard(user_id, sid, info=None):
    """إنشاء لوحة مفاتيح خيارات الجودة بشكل ديناميكي"""
    markup = types.InlineKeyboardMarkup()
    
    if not info:
        # أزرار افتراضية في حال فشل الاستخراج
        markup.row(
            types.InlineKeyboardButton("🎬 جودة عالية 720+", callback_data=f"dl_high|{sid}"),
            types.InlineKeyboardButton("🎥 جودة متوسطة 480", callback_data=f"dl_medium|{sid}")
        )
        markup.row(
            types.InlineKeyboardButton("📱 جودة منخفضة 360", callback_data=f"dl_low|{sid}"),
            types.InlineKeyboardButton("🎵 تحميل صوت فقط", callback_data=f"audio_{sid}")
        )
    else:
        resolutions = info.get('resolutions', [])
        if resolutions:
            # ترتيب الجودات لصفوف (كل صف جودتين)
            for i in range(0, len(resolutions), 2):
                row = []
                for res in resolutions[i:i+2]:
                    label = f"🎥 {res}p"
                    if res >= 2160: label = f"💎 4K ({res}p)"
                    elif res >= 1440: label = f"🌟 2K ({res}p)"
                    elif res >= 1080: label = f"🎬 Full HD ({res}p)"
                    elif res >= 720: label = f"🎥 HD ({res}p)"
                    
                    row.append(types.InlineKeyboardButton(label, callback_data=f"dl_{res}|{sid}"))
                markup.row(*row)
        else:
            markup.row(
                types.InlineKeyboardButton("🎬 أفضل جودة متاحة", callback_data=f"dl_high|{sid}"),
                types.InlineKeyboardButton("🎥 جودة متوسطة", callback_data=f"dl_medium|{sid}")
            )
        
        # إضافة خيار الصوت
        markup.row(types.InlineKeyboardButton("🎵 تحميل صوت فقط (MP3)", callback_data=f"audio_{sid}"))
    
    # زر الرجوع للقائمة الرئيسية
    markup.row(types.InlineKeyboardButton("🔙 إلغاء والرجوع", callback_data="menu_back_to_main"))
    
    return markup
