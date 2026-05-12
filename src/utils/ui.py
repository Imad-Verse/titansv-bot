from telebot import types
from src.services.translation import translation_system

def get_error_markup(user_id):
    """إنشاء أزرار المساعدة والمراسلة عند حدوث خطأ"""
    markup = types.InlineKeyboardMarkup()
    
    # جلب النصوص المترجمة
    help_text = translation_system.get(user_id, 'main_menu_buttons', key='help')
    contact_text = translation_system.get(user_id, 'contact_dev')
    
    markup.row(
        types.InlineKeyboardButton(help_text, callback_data="menu_help"),
        types.InlineKeyboardButton(contact_text, url="https://t.me/abulharith_imad")
    )
    return markup
