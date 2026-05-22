class TranslationSystem:
    LANGUAGES = {
        'ar': 'العربية'
    }
    
    TRANSLATIONS = {
        'ar': {
            'start_message': """🚀 <b>أهلاً بك في بوت التحميل الذكي!</b>

أرسل رابط أي فيديو (يوتيوب، فيسبوك، إنستقرام، تيك توك، إلخ) للبدء في التحميل فوراً بأفضل جودة متوفرة.

⚠️ <b>تنبيه:</b> يرجى عدم استخدام البوت فيما يغضب الله عز وجل.
{bot_sig}""",
            'maintenance_on': "🛠 <b>البوت في صيانة مؤقتة للتحديث. سنعود قريباً إن شاء الله!</b>",
            'banned_user': "🚫 <b>عذراً، تم حظر حسابك من استخدام البوت.</b>",
            'invalid_link': "❌ <b>عذراً، هذا الرابط غير صالح أو غير مدعوم!</b>",
            'unsupported_platform': "❌ <b>عذراً، هذه المنصة غير مدعومة حالياً!</b>\nالمنصات المدعومة: {platforms}",
            'force_sub_msg': "⚠️ <b>عذراً، يجب عليك الاشتراك في قنوات البوت أولاً للبدء:</b>\n\n{channels}",
            'choose_quality': "🎥 <b>اختر جودة التحميل:</b>\nتظهر فقط الجودات المتوفرة في هذا الفيديو.\n\n⚠️ <b>تنبيه:</b> يرجى اختيار جودة لا تتجاوز <b>50 ميغابايت</b>، حيث أنها الحد الأقصى المسموح به للرفع عبر تيليجرام.",
            'check_sub_btn': "🔄 تفعيل البوت",
            'main_menu': "🏠 القائمة الرئيسية",
            'unknown_command': "❓ <b>عذراً، يرجى إرسال رابط فيديو مباشر وصالح للتحميل.</b>",
            'contact_dev': "👨‍💻 الدعم الفني",
            'bots_list_text': "🤖 <b>قائمة بوتاتنا المميزة والمفيدة:</b>\n\nتفضل بزيارة قناتنا للمزيد.",
            'user_stats_msg': """📊 <b>إحصائيات حسابك:</b>

👤 <b>الاسم:</b> {name}
🆔 <b>المعرف:</b> <code>{uid}</code>
📥 <b>إجمالي التحميلات:</b> {download_count} فيديو
🏆 <b>ترتيبك:</b> {rank} من أصل {total_users} مستخدم""",
            'main_menu_buttons': {
                'start_download': '📢 مشاركة البوت',
                'help': '🆘 المساعدة',
                'language': '🌍 اللغة',
                'contact': '👨‍💻 المطور',
                'bots_list': '🤖 قائمة بوتاتنا',
                'user_stats': '📊 إحصائياتي',
                'admin_panel': '🛠 لوحة التحكم'
            },
            'link_expired': "⚠️ انتهت صلاحية الجلسة، يرجى إعادة إرسال الرابط.",
            'extracting_info': "🔍 <b>جاري فحص الرابط واستخراج البيانات...</b>",
            'download_started': "⏳ جاري تحميل الفيديو من المصدر...",
            'download_progress': "⏳ تحميل: {percent}%",
            'upload_progress': "🚀 رفع: {percent}%",
            'download_error': "❌ فشل سحب البيانات! يرجى التأكد من الرابط والمحاولة لاحقاً.",
            'audio_success': "✅ تم استخراج الصوت بنجاح!\n{bot_sig}",
            'mute_success': "✅ تم تحميل الفيديو بدون صوت!\n{bot_sig}",
            'video_caption': """🎬 <b>{title}</b>

⏱ <b>المدة:</b> {duration} | 💾 <b>الحجم:</b> {size} MB

{bot_sig}""",
            'extract_audio': "🎵 تحميل كصوت MP3",
            'mute_video': "🔇 فيديو بدون صوت",
            'share_bot': "📢 مشاركة البوت",
            'cancel_download': "❌ إلغاء التحميل",
            'download_completed': "✅ تم تحميل الفيديو! جاري إرساله إليك...",
            'file_too_large': "⚠️ حجم الفيديو ({size:.1f} MB) يتجاوز الحد المسموح للرفع ({limit_mb} ميغابايت).\nيرجى إعادة المحاولة واختيار جودة أقل.",
            'file_too_large_unknown': "⚠️ حجم الفيديو يتجاوز الحد المسموح للرفع ({limit_mb} ميغابايت).\nيرجى إعادة المحاولة واختيار جودة أقل.",
            'weak_connection': "📡 مشكلة في الاتصال بالمصدر! يرجى إعادة المحاولة.",
            'temporary_source_issue': "🛠 تعذر جلب البيانات من المنصة حالياً، يرجى المحاولة بعد قليل.",
            'video_unavailable': "🚫 الفيديو غير متاح أو محذوف أو خاص.",
            'private_or_login': "🔒 هذا الفيديو خاص أو يتطلب تسجيل دخول.",
            'unsupported_url': "❌ الرابط لا يحتوي على فيديو قابل للتحميل.",
            'no_video_in_post': "❌ لم يتم العثور على أي فيديو في هذا الرابط.",
            'service_blocked': "🚫 المنصة حظرت الطلب مؤقتاً، يرجى المحاولة لاحقاً.",
            'photo_not_supported': "📸 البوت يدعم تحميل الفيديوهات والصوتيات فقط.",
            'processing_error': "❌ خطأ أثناء معالجة الفيديو!",
            'already_processing': "⏳ لديك تحميل جارٍ بالفعل، يرجى الانتظار لحين اكتماله.",
            'server_busy': "🚦 السيرفر مزدحم حالياً، يرجى الانتظار قليلاً.",
            'send_link_prompt': "🔗 أرسل رابط الفيديو الآن وسأقوم بتحميله فوراً!",
            'request_processing_failed': "❌ تعذر إتمام طلبك حالياً!",
            'subscription_incomplete': "⚠️ يرجى الاشتراك في جميع القنوات لتفعيل البوت.",
            'subscription_verified': "✅ تم التحقق وتفعيل البوت!",
            'subscribed_success': "✅ تم التفعيل بنجاح! أرسل الروابط الآن للتحميل.",
            'processing': "⏳ جاري التحضير...",
            'operation_failed': "❌ فشلت العملية!",
            'link_sent': "✅ تم إرسال الرابط.",
            'link_missing': "❌ الرابط غير متوفر!",
            'no_active_download': "❌ لا يوجد تنزيل نشط حالياً.",
            'share_message': "🚀 جرب هذا البوت الرائع لتحميل الفيديوهات فوراً وبأعلى جودة!",
            'help_title': "🆘 <b>دليل الاستخدام والتشغيل:</b>",
            'help_message': """🎬 <b>طريقة التحميل:</b>
1. انسخ رابط الفيديو من أي منصة.
2. أرسله في المحادثة مباشرة.
3. اختر الجودة المناسبة من الأزرار المتوفرة (عالية، متوسطة، ضعيفة).

📡 <b>أهم الأوامر:</b>
/start - تشغيل وإعادة تهيئة البوت
/help - دليل الاستخدام والدعم
/stats - عرض إحصائياتك الشخصية""",
            'downgraded_due_to_size': "⚠️ حجم الفيديو يتجاوز الحد! جاري التحميل تلقائياً بجودة أقل...",
            'already_in_queue': "⚠️ أنت موجود بالفعل في طابور الانتظار!",
            'starting_download': "⏳ جاري بدء التحميل...",
            'added_to_queue': "⏳ السيرفر مزدحم حالياً. تم وضع طلبك في الطابور (الترتيب: {pos}). سيبدأ التحميل تلقائياً.",
            'queue_turn_arrived': "🚀 <b>حان دورك!</b> جاري معالجة طلبك الآن...",
            'upload_started': "🚀 جاري الرفع إلى تيليجرام...",
            'session_expired': "⚠️ انتهت صلاحية الجلسة، يرجى إعادة إرسال الرابط.",
            'download_cancelled': "❌ تم إلغاء عملية التحميل بنجاح.",
            'ffmpeg_missing': "⚠️ عذراً، مكون معالجة الفيديو (FFmpeg) غير متوفر حالياً. يرجى التواصل مع المطور.",
            'broadcast_to_all': "📢 إرسال للكل",
            'broadcast_to_user': "👤 إرسال لمستخدم محدد"
        }
    }

    def __init__(self):
        pass

    def get(self, user_id, translation_key, **kwargs):
        # Default to Arabic since we only support Arabic
        data = self.TRANSLATIONS['ar']
        
        # Extract default fallback if provided
        default_val = kwargs.pop('default', translation_key)
        
        text = data.get(translation_key)
        if text is None:
            text = default_val
            
        if isinstance(text, dict) and 'key' in kwargs:
            subkey = kwargs.pop('key')
            text = text.get(subkey, subkey)
            
        if kwargs and isinstance(text, str):
            try:
                return text.format(**kwargs)
            except Exception:
                return text
        return text

    def set_language(self, user_id, lang_code):
        pass

    def get_user_lang(self, user_id):
        return 'ar'

translation_system = TranslationSystem()
