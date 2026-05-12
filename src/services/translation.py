from src.core.database import get_user_language

class TranslationSystem:
    LANGUAGES = {
        'ar': 'العربية'
    }
    
    TRANSLATIONS = {
        'ar': {
            'welcome_title': "🎉 مرحباً بك في {bot_name}",
            'welcome_message': """⚡️ <b>مميزات البوت:</b>
• تحميل من يوتيوب، تيك توك، فيسبوك، إنستقرام
• دعم بينترست، تويتر (X)، سناب شات، ثريدز
• دعم دقة تصل إلى 1080p وجودة MP3
• استخراج الصوت من الفيديو
• كتم صوت الفيديو
• دعم الفيديوهات الطويلة جداً
• تحميل الحالات (Stories) والريمات (Reels)

📊 <b>إحصائيات البوت:</b>
• عدد المستخدمين: {total_users}
• التحميلات اليومية: {daily_downloads}

🎬 <b>كيفية الاستخدام:</b>
1. أرسل رابط الفيديو
2. اختر الجودة المطلوبة
3. استلم ملفك فوراً 🚀

⚠️ <b>ملاحظات مهمة:</b>
• الحد الأقصى: {max_size} MB
• يمنع استخدام البوت للمحرمات""",
            'start_message': """<b>{bot_sig}</b>

أرسل رابط فيديو من (يوتيوب، تيك توك، فيسبوك، إنستقرام، بينترست، تويتر).

⛔️ تنبيه: لا تستخدم البوت فيما يغضب الله عز وجل كتحميل الموسيقى والصور المحرمة، ولا أجعلك في حل ان فعلت ذلك.

🔥ماذا تنتظر! أرسل الرابط الآن ودعنا نبدأ!""",
            'maintenance_on': "🛠 <b>المعذرة، البوت في وضع الصيانة حالياً لإضافة تحسينات جديدة. حاول لاحقاً.</b>",
            'banned_user': "🚫 <b>عذراً، تم حظرك من استخدام البوت.</b>",
            'invalid_link': "❌ <b>تعذر التعرف على رابط صالح قابل للتحميل.</b>\nأرسل رابط منشور أو فيديو مباشر من منصة مدعومة.",
            'unsupported_platform': "❌ <b>المنصة الموجودة في هذا الرابط غير مدعومة حالياً.</b>\nالمنصات المدعومة: {platforms}",
            'force_sub_msg': "<b>⚠️ عذراً، يجب عليك الاشتراك في القنوات أدناه لتتمكن من استخدام البوت:</b>\n\n{channels}",
            'choose_quality': "🎥 <b>اختر جودة التحميل المطلوبة:</b>",
            'check_sub_btn': "🔄 تحقق من الاشتراك",
            'main_menu': "🏠 القائمة الرئيسية",
            'unknown_command': "❓ <b>عذراً، لم أفهم هذا الأمر.</b>\nيرجى إرسال رابط فيديو صالح للتحميل.",
            'language_set': "✅ تم تغيير اللغة إلى {language}",
            'select_language': "🌍 <b>اختر لغتك المفضلة:</b>",
            'contact_dev': "👨‍💻 مراسلة المطور",
            'bots_list_text': "🤖 <b>قائمة بوتاتنا المميزة:</b>\n\nتفضل بزيارة @abulharith_imad للمزيد.",
            'user_stats_msg': """📊 <b>إحصائياتك الشخصية:</b>

👤 <b>الاسم:</b> {name}
🆔 <b>المعرف:</b> <code>{uid}</code>
📅 <b>تاريخ الانضمام:</b> {join_date}
📥 <b>إجمالي التحميلات:</b> {download_count} فيديو
🏆 <b>رتبتك:</b> {rank} من أصل {total_users} مستخدم""",
            'main_menu_buttons': {
                'start_download': '📢 مشاركة البوت',
                'help': '🆘 المساعدة',
                'language': '🌍 اللغة',
                'contact': '👨‍💻 المطور',
                'bots_list': '🤖 قائمة بوتاتنا',
                'user_stats': '📊 إحصائياتي',
                'admin_panel': '🛠 لوحة التحكم'
            },
            'link_expired': "⚠️ انتهت صلاحية هذا الرابط. أرسل الرابط مرة أخرى.",
            'choose_quality_btn': "🎥 اختر الجودة",
            'download_started': "⏳ جاري بدء التحميل...",
            'download_progress': "⏳ جاري التحميل: {percent}%",
            'upload_progress': "⏳ جاري الرفع: {percent}%",
            'download_error': "❌ حدث خطأ أثناء التحميل.",
            'audio_success': "✅ تم تحميل الصوت بنجاح\n{bot_sig}",
            'mute_success': "✅ تم تحميل الفيديو صامتاً\n{bot_sig}",
            'video_caption': """🎬 <b>{title}</b>

{description}

📱 <b>المنصة:</b> {platform}
⏱ <b>المدة:</b> {duration}
💾 <b>الحجم:</b> {size} MB

{bot_sig}""",
            'extract_audio': "🎵 استخراج الصوت",
            'mute_video': "🔇 فيديو بدون صوت",
            'share_bot': "📢 مشاركة البوت",
            'cancel_download': "❌ إلغاء التحميل",
            'download_completed': "✅ اكتمل التحميل، جاري الرفع...",
            'file_too_large': "⚠️ حجم الملف ({size} MB) يتجاوز الحد المسموح به للرفع ({limit_mb} MB).",
            'file_too_large_unknown': "⚠️ حجم الملف يتجاوز الحد المسموح به للرفع ({limit_mb} MB).",
            'weak_connection': "📡 فشل الاتصال، يبدو أن المصدر يواجه ضغطاً أو اتصالك ضعيف.",
            'temporary_source_issue': "🛠 عذراً، نواجه مشكلة مؤقتة في سحب البيانات من هذا الرابط. حاول لاحقاً.",
            'video_unavailable': "🚫 هذا الفيديو غير متاح حالياً (قد يكون محذوفاً أو خاصاً).",
            'private_or_login': "🔒 هذا الفيديو خاص أو يتطلب تسجيل دخول لمشاهدته.",
            'unsupported_url': "❌ الرابط غير مدعوم أو لا يحتوي على فيديو قابل للتحميل.",
            'no_video_in_post': "❌ لا يوجد فيديو في هذا المنشور.",
            'service_blocked': "🚫 الخدمة محجوبة مؤقتاً من قبل المنصة، يرجى المحاولة لاحقاً.",
            'photo_not_supported': "📸 عذراً، البوت يدعم تحميل الفيديوهات فقط حالياً.",
            'processing_error': "❌ حدث خطأ أثناء معالجة الفيديو.",
            'already_processing': "⏳ لديك عملية تحميل جارية بالفعل. يرجى الانتظار.",
            'server_busy': "🚦 السيرفر مشغول حالياً بمعالجة الكثير من الطلبات. حاول بعد قليل.",
            'send_link_prompt': "🔗 أرسل رابط الفيديو الآن للتحميل.",
            'request_processing_failed': "❌ تعذر معالجة طلبك حالياً.",
            'subscription_incomplete': "⚠️ لم تشترك في كافة القنوات المطلوبة بعد.",
            'subscription_verified': "✅ تم التحقق من الاشتراك بنجاح!",
            'subscribed_success': "✅ شكراً لاشتراكك! يمكنك الآن إرسال الروابط والتحميل.",
            'processing': "⏳ جاري المعالجة...",
            'operation_failed': "❌ فشلت العملية.",
            'link_sent': "✅ تم إرسال الرابط.",
            'link_missing': "❌ الرابط غير موجود.",
            'no_active_download': "❌ لا يوجد تحميل نشط حالياً للإلغاء.",
            'share_message': "🚀 جرب هذا البوت الرهيب لتحميل الفيديوهات من كل المنصات مجاناً!",
            'help_title': "🆘 <b>دليل استخدام العملاق للتحميل</b>",
            'help_message': """🎬 <b>كيفية التحميل:</b>
1. انسخ رابط الفيديو من أي منصة مدعومة.
2. أرسل الرابط مباشرة هنا.
3. اختر الجودة التي تناسبك.

📡 <b>المنصات المدعومة:</b>
{channels}

⚠️ <b>حدود التحميل:</b>
• الحد الأقصى لحجم الملف: {max_size} MB
• المدة القصوى: {max_duration} دقيقة

🛠 <b>الأوامر المتاحة:</b>
/start - تشغيل البوت
/help - المساعدة والمنصات
/stats - إحصائياتك الشخصية"""
        }
    }

    def __init__(self):
        pass

    def get(self, user_id, translation_key, **kwargs):
        # Default to Arabic since we removed other languages
        data = self.TRANSLATIONS['ar']
        text = data.get(translation_key, translation_key)
        
        if isinstance(text, dict) and 'key' in kwargs:
            subkey = kwargs.pop('key')
            text = text.get(subkey, subkey)
            
        if kwargs:
            try:
                return text.format(**kwargs)
            except:
                return text
        return text

    def set_language(self, user_id, lang_code):
        pass

    def get_user_lang(self, user_id):
        return 'ar'

translation_system = TranslationSystem()
