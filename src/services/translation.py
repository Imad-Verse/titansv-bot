from src.core.database import get_user_language

class TranslationSystem:
    LANGUAGES = {
        'ar': 'العربية',
        'en': 'English',
        'fr': 'Français'
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
                'language': '🌍 تغيير اللغة',
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
            'mute_success': "✅ تم تحميل الفيديو صامتاً\n{bot_sig}"
        },
        'en': {
            'welcome_title': "🎉 Welcome to {bot_name}",
            'start_message': """<b>{bot_sig}</b>

Send a video link from (YouTube, TikTok, Facebook, Instagram, Pinterest, Twitter).

⛔️ Warning: Do not use the bot for forbidden content!""",
            'maintenance_on': "🛠 <b>Sorry, the bot is currently under maintenance. Please try again later.</b>",
            'banned_user': "🚫 <b>Sorry, you are banned from using the bot.</b>",
            'invalid_link': "❌ <b>Could not recognize a valid link.</b>",
            'unsupported_platform': "❌ <b>This platform is not supported.</b>\nSupported: {platforms}",
            'force_sub_msg': "<b>⚠️ Sorry, you must subscribe to these channels first:</b>\n\n{channels}",
            'choose_quality': "🎥 <b>Choose download quality:</b>",
            'check_sub_btn': "🔄 Check Subscription",
            'main_menu': "🏠 Main Menu",
            'unknown_command': "❓ <b>Sorry, I didn't understand that.</b>",
            'language_set': "✅ Language changed to {language}",
            'select_language': "🌍 <b>Select your language:</b>",
            'contact_dev': "👨‍💻 Contact Developer",
            'bots_list_text': "🤖 <b>Our Bots List:</b>",
            'user_stats_msg': """📊 <b>Your Stats:</b>

👤 <b>Name:</b> {name}
🆔 <b>ID:</b> <code>{uid}</code>
📅 <b>Joined:</b> {join_date}
📥 <b>Total Downloads:</b> {download_count}
🏆 <b>Rank:</b> {rank} / {total_users}""",
            'main_menu_buttons': {
                'start_download': '📢 Share Bot',
                'help': '🆘 Help',
                'language': '🌍 Change Language',
                'contact': '👨‍💻 Developer',
                'bots_list': '🤖 Our Bots',
                'user_stats': '📊 My Stats',
                'admin_panel': '🛠 Admin Panel'
            },
            'link_expired': "⚠️ Link expired. Send it again.",
            'download_started': "⏳ Starting download...",
            'audio_success': "✅ Audio downloaded\n{bot_sig}",
            'mute_success': "✅ Video muted\n{bot_sig}"
        },
        'fr': {
            'welcome_title': "🎉 Bienvenue sur {bot_name}",
            'start_message': """<b>{bot_sig}</b>

Envoyez un lien vidéo de (YouTube, TikTok, Facebook, Instagram, Pinterest, Twitter).""",
            'maintenance_on': "🛠 <b>Désolé, le bot est en maintenance.</b>",
            'banned_user': "🚫 <b>Désolé, vous êtes banni.</b>",
            'invalid_link': "❌ <b>Lien invalide.</b>",
            'unsupported_platform': "❌ <b>Plateforme non supportée.</b>\nSupportées: {platforms}",
            'force_sub_msg': "<b>⚠️ Désolé, vous devez vous abonner d'abord:</b>\n\n{channels}",
            'choose_quality': "🎥 <b>Choisissez la qualité:</b>",
            'check_sub_btn': "🔄 Vérifier l'abonnement",
            'main_menu': "🏠 Menu Principal",
            'language_set': "✅ Langue changée en {language}",
            'select_language': "🌍 <b>Choisissez votre langue:</b>",
            'contact_dev': "👨‍💻 Développeur",
            'main_menu_buttons': {
                'start_download': '📢 Partager',
                'help': '🆘 Aide',
                'language': '🌍 Langue',
                'contact': '👨‍💻 Développeur',
                'bots_list': '🤖 Nos Bots',
                'user_stats': '📊 Mes Stats',
                'admin_panel': '🛠 Admin'
            },
            'audio_success': "✅ Audio téléchargé\n{bot_sig}",
            'mute_success': "✅ Vidéo muette\n{bot_sig}"
        }
    }

    def __init__(self):
        self._user_langs = {} # Cache for user languages

    def get_user_lang(self, user_id):
        if user_id in self._user_langs:
            return self._user_langs[user_id]
        
        lang = get_user_language(user_id) or 'ar'
        self._user_langs[user_id] = lang
        return lang

    def set_language(self, user_id, lang_code):
        if lang_code in self.LANGUAGES:
            self._user_langs[user_id] = lang_code

    def get(self, user_id, translation_key, **kwargs):
        lang = self.get_user_lang(user_id)
        data = self.TRANSLATIONS.get(lang, self.TRANSLATIONS['ar'])
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

translation_system = TranslationSystem()
