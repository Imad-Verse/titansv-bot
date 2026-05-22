import time
from telebot import types
from src.core.config import Config
from src.core.loader import bot, BotState
from src.core.database import get_stats, log_broadcast_messages_batch
from src.services.translation import translation_system

def create_broadcast_markup(user_id):
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton(translation_system.get(user_id, 'broadcast_to_all'), callback_data="broadcast_all"),
        types.InlineKeyboardButton(translation_system.get(user_id, 'broadcast_to_user'), callback_data="broadcast_user")
    )
    markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="refresh_stats"))
    return markup

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_menu")
def broadcast_menu_handler(call):
    if call.from_user.id != Config.ADMIN_ID: return
    
    text = "📢 <b>قسم الإذاعة والإعلانات</b>\n\nاختر نوع الإذاعة التي تريد القيام بها:"
    bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=create_broadcast_markup(call.from_user.id))

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_all")
def broadcast_all_handler(call):
    if call.from_user.id != Config.ADMIN_ID: return
    
    msg = bot.edit_message_text("📣 <b>أرسل الآن الرسالة التي تريد إذاعتها للجميع:</b>\n(نص، صورة، فيديو، بصمة...)", call.message.chat.id, call.message.message_id, parse_mode="HTML")
    bot.register_next_step_handler(msg, process_broadcast_step, "all")

@bot.callback_query_handler(func=lambda call: call.data == "broadcast_user")
def broadcast_user_handler(call):
    if call.from_user.id != Config.ADMIN_ID: return
    
    msg = bot.edit_message_text("👤 <b>أرسل الآن آيدي (ID) المستخدم الذي تريد مراسلته:</b>", call.message.chat.id, call.message.message_id, parse_mode="HTML")
    bot.register_next_step_handler(msg, process_target_user_step)

def process_target_user_step(message):
    target_uid = message.text.strip()
    if not target_uid.isdigit():
        bot.send_message(message.chat.id, "❌ الآيدي يجب أن يكون أرقاماً فقط. حاول مجدداً:")
        bot.register_next_step_handler(message, process_target_user_step)
        return
        
    msg = bot.send_message(message.chat.id, f"📝 <b>أرسل الآن الرسالة التي تريد إرسالها للمستخدم {target_uid}:</b>")
    bot.register_next_step_handler(msg, process_broadcast_step, target_uid)

def process_broadcast_step(message, target_type):
    if message.text in ['🔙 الغاء', '/admin']:
        from src.handlers.admin import send_admin_panel
        send_admin_panel(message.chat.id)
        return

    if target_type == "all":
        from src.services.broadcast import perform_all_broadcast
        import threading
        threading.Thread(target=perform_all_broadcast, args=(message,), daemon=True).start()
    else:
        from src.services.broadcast import perform_specific_broadcast
        perform_specific_broadcast(message, target_type)
        
        from src.handlers.admin import send_admin_panel
        send_admin_panel(message.chat.id)

