from telebot import types
import os
import time
from src.core.config import Config
from src.core.loader import bot, BotState
from src.services.translation import translation_system
from src.core.database import get_stats, ban_unban, get_top_users, auto_backup_database, get_detailed_stats

# استيراد وحدة الإذاعة لتفعيل معالجاتها
import src.handlers.admin.broadcast

def create_admin_markup():
    markup = types.InlineKeyboardMarkup(row_width=2)
    markup.add(
        types.InlineKeyboardButton("📢 ارسال اذاعة", callback_data="broadcast_menu"),
        types.InlineKeyboardButton("📊 إحصائيات تفصيلية", callback_data="more_stats")
    )
    markup.add(
        types.InlineKeyboardButton("⛔ حظر / الغاء حظر", callback_data="ban_unban_ask"),
        types.InlineKeyboardButton("🍪 تفقد الكوكيز", callback_data="check_cookies")
    )
    markup.add(
        types.InlineKeyboardButton("💾 نسخة احتياطية", callback_data="backup_db"),
        types.InlineKeyboardButton(f"وضع الصيانة: {'✅' if BotState.is_maintenance else '❌'}", callback_data="toggle_maint")
    )
    markup.add(
        types.InlineKeyboardButton("🖥 حالة السيرفر", callback_data="pc_status"),
        types.InlineKeyboardButton("🔁 إعادة تشغيل", callback_data="sys_restart")
    )
    markup.add(types.InlineKeyboardButton("🔄 تحديث الإحصائيات", callback_data="refresh_stats"))
    return markup

@bot.message_handler(commands=['boss', 'admin'])
def admin_panel_command(message):
    if message.from_user.id != Config.ADMIN_ID: 
        return
    send_admin_panel(message.chat.id)

def send_admin_panel(chat_id, message_id=None):
    stats = get_stats()
    if not stats:
        bot.send_message(chat_id, "❌ خطأ في جلب البيانات.")
        return
        
    _, week_dl, failed_today = get_detailed_stats()
    
    # تحسين عرض الإحصائيات مع إضافة عدد المشتركين
    total_mb = stats.get('total_size_mb', 0)
    transfer_text = f"{total_mb:.1f} MB" if total_mb < 1024 else f"{total_mb/1024:.2f} GB"
    
    text = (
        f"<b>⚜️ لوحة تحكم العملاق </b>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"👥 <b>إجمالي المشتركين:</b> <code>{stats.get('total_users', 0)}</code>\n"
        f"📥 <b>المشتركين الجدد (اليوم):</b> <code>{stats.get('new_users_today', 0)}</code>\n"
        f"🔥 <b>النشطين (هذا الشهر):</b> <code>{stats.get('active_this_month', 0)}</code>\n"
        f"🚫 <b>المحظورين:</b> <code>{stats.get('banned_users', 0)}</code>\n"
        f"━━━━━━━━━━━━━━━\n"
        f"📊 <b>إجمالي التحميلات:</b>\n"
        f" └ اليوم: <code>{stats.get('today_downloads', 0)}</code> | الأسبوع: <code>{week_dl}</code>\n"
        f" └ الشهر: <code>{stats.get('monthly_downloads', 0)}</code>\n"
        f"📉 <b>عمليات فاشلة (اليوم):</b> <code>{failed_today}</code>\n"
        f"📡 <b>إجمالي البيانات:</b> <code>{transfer_text}</code>\n"
        f"━━━━━━━━━━━━━━━"
    )
    
    markup = create_admin_markup()
    
    if message_id:
        try:
            bot.edit_message_text(text, chat_id, message_id, parse_mode="HTML", reply_markup=markup)
        except:
            bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)
    else:
        bot.send_message(chat_id, text, parse_mode="HTML", reply_markup=markup)

@bot.callback_query_handler(func=lambda call: call.data in ['refresh_stats', 'toggle_maint', 'more_stats', 'ban_unban_ask', 'backup_db', 'check_cookies', 'pc_status', 'sys_restart', 'menu_admin_panel', 'broadcast_menu'])
def admin_actions(call):
    if call.from_user.id != Config.ADMIN_ID: return
    
    if call.data == 'refresh_stats' or call.data == 'menu_admin_panel':
        send_admin_panel(call.message.chat.id, call.message.message_id)
        bot.answer_callback_query(call.id, "✅ تم التحديث" if call.data == 'refresh_stats' else None)
        
    elif call.data == 'broadcast_menu':
        from src.handlers.admin.broadcast import broadcast_menu_handler
        broadcast_menu_handler(call)

    elif call.data == 'pc_status':
        import shutil
        total, used, free = shutil.disk_usage(Config.BASE_DIR)
        disk_percent = (used / total) * 100
        free_gb = free / (2**30)
        status_msg = f"🖥 <b>حالة السيرفر:</b>\n💾 <b>القرص:</b> {disk_percent:.1f}% ({free_gb:.2f} GB free)"
        bot.answer_callback_query(call.id)
        bot.send_message(call.message.chat.id, status_msg, parse_mode="HTML")

    elif call.data == 'sys_restart':
        import sys
        bot.answer_callback_query(call.id, "🔁 جاري إعادة تشغيل البوت...", show_alert=True)
        with open(Config.RESTART_LOG, "w") as f: 
            f.write(str(call.message.chat.id))
        os.execl(sys.executable, sys.executable, *sys.argv)

    elif call.data == 'toggle_maint':
        BotState.is_maintenance = not BotState.is_maintenance
        
        status = "مفعل ✅" if BotState.is_maintenance else "معطل ❌"
        bot.answer_callback_query(call.id, f"تم تغيير وضع الصيانة إلى: {status}", show_alert=True)
        send_admin_panel(call.message.chat.id, call.message.message_id)
        
    elif call.data == 'more_stats':
        top_users = get_top_users(5)
        text = "📊 <b>أكثر 5 مستخدمين تحميلاً:</b>\n\n"
        if not top_users:
            text += "لا توجد بيانات."
        else:
            for i, (uid_val, uname, count) in enumerate(top_users, 1):
                if uname and uname.lower() not in ['none', 'nouser', 'no name']:
                    safe_name = f"@{uname.lstrip('@')}"
                else:
                    safe_name = "No Username"
                text += f"{i}. <code>{uid_val}</code> | {safe_name} | 📥 <b>{count}</b>\n"
        
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="refresh_stats"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

    elif call.data == 'ban_unban_ask':
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 الغاء", callback_data="refresh_stats"))
        msg = bot.edit_message_text("🚫 <b>أرسل الآيدي (ID) للمستخدم:</b>\nسيتم عكس حالته (حظر / الغاء حظر)", call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)
        bot.register_next_step_handler(msg, perform_ban_unban_step)

    elif call.data == 'backup_db':
        auto_backup_database()
        bot.answer_callback_query(call.id, "✅ تم إنشاء النسخة الاحتياطية", show_alert=True)

    elif call.data == 'check_cookies':
        text = "🍪 <b>حالة ملفات الكوكيز:</b>\n\n"
        now = time.time()
        found_issue = False
        
        for platform, path in Config.COOKIES_FILES.items():
            if path.exists() and path.stat().st_size > 0:
                age_days = (now - path.stat().st_mtime) / (3600 * 24)
                status = "✅ جيد"
                if age_days > 7:
                    status = "⚠️ قديم (> 7 أيام)"
                    found_issue = True
                text += f"🔹 <b>{platform.title()}:</b> {status} ({age_days:.1f} يوم)\n"
            else:
                text += f"🔸 <b>{platform.title()}:</b> ❌ غير موجود\n"
                found_issue = True
        
        if found_issue:
            text += "\n⚠️ <b>يوصى بتحديث ملفات الكوكيز!</b>"
        else:
            text += "\n✅ <b>كل الملفات بحالة جيدة.</b>"
            
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🔙 رجوع", callback_data="refresh_stats"))
        bot.edit_message_text(text, call.message.chat.id, call.message.message_id, parse_mode="HTML", reply_markup=markup)

def perform_ban_unban_step(message):
    if message.text in ['/start', '/admin', '🔙 الغاء']:
        send_admin_panel(message.chat.id)
        return
        
    uid_to_ban = message.text.strip()
    if not uid_to_ban.isdigit():
        bot.send_message(message.chat.id, "❌ الآيدي يجب أن يكون أرقاماً فقط. أرسل الآيدي الصحيح أو /admin للالغاء.")
        return

    # استخدام الدالة الجاهزة للتحقق من حالة الحظر
    from src.core.database import is_banned as check_ban
    
    already_banned = check_ban(uid_to_ban)
    new_status = not already_banned
    
    if ban_unban(uid_to_ban, new_status):
        action = "تم حظره بنجاح 🚫" if new_status else "تم إلغاء الحظر بنجاح ✅"
        bot.send_message(message.chat.id, f"👤 المستخدم: <code>{uid_to_ban}</code>\n<b>{action}</b>", parse_mode="HTML")
    else:
        bot.send_message(message.chat.id, "❌ حدث خطأ أثناء محاولة تعديل حالة المستخدم. تأكد أن المستخدم موجود في قاعدة البيانات.")
        
    send_admin_panel(message.chat.id)

@bot.message_handler(func=lambda m: m.text in ["🛠 لوحة التحكم", "🛠 Control Panel", "🛠 Panneau de Contrôle"])
def admin_panel_button(message):
    admin_panel_command(message)
