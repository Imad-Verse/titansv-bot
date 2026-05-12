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

    BotState.is_broadcast_active = True
    
    if target_type == "all":
        from src.core.database import get_active_user_ids
        users = get_active_user_ids()
        total_users = len(users)
        status_msg = bot.send_message(message.chat.id, f"🚀 <b>بدء الإذاعة لـ {total_users} مستخدم...</b>", parse_mode="HTML")
    else:
        # إذا كان الإرسال لمستخدم واحد
        users = [target_type]
        status_msg = bot.send_message(message.chat.id, f"⏳ جاري الإرسال للمستخدم {target_type}...")

    success = 0
    failed = 0
    broadcast_id = f"bc_{int(time.time())}"
    batch_logs = []

    for user_id in users:
        if not BotState.is_broadcast_active: break
        try:
            sent_msg = bot.copy_message(user_id, message.chat.id, message.message_id)
            success += 1
            batch_logs.append((broadcast_id, str(user_id), str(sent_msg.message_id)))
            
            if len(batch_logs) >= 50:
                log_broadcast_messages_batch(batch_logs)
                batch_logs = []
                
        except Exception:
            failed += 1
        
        if len(users) > 20 and (success + failed) % 20 == 0:
            try:
                bot.edit_message_text(f"⏳ جاري الإرسال...\n✅ نجاح: {success}\n❌ فشل: {failed}\n📊 الإجمالي: {success+failed}/{len(users)}", message.chat.id, status_msg.message_id)
            except: pass

    if batch_logs:
        log_broadcast_messages_batch(batch_logs)

    BotState.is_broadcast_active = False
    final_text = f"✅ <b>اكتمل الإرسال!</b>\n\n🎯 نجاح: <code>{success}</code>\n🚫 فشل: <code>{failed}</code>"
    bot.send_message(message.chat.id, final_text, parse_mode="HTML")
    
    from src.handlers.admin import send_admin_panel
    send_admin_panel(message.chat.id)

