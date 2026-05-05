class TranslationSystem:
    LANGUAGES = {
        'ar': 'العربية',
        'en': 'English',
        'fr': 'Français'
    }
    
    def __init__(self):
        self.user_languages = {}  # user_id -> language
    
    def set_language(self, user_id, lang):
        self.user_languages[user_id] = lang
    
    def get(self, user_id, translation_key, **kwargs):
        lang = self.user_languages.get(user_id, 'ar')
        
        # قائمة الترجمات
        translations = {
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
                'maintenance_mode': "🛠 <b>المعذرة، البوت في وضع الصيانة، حاول لاحقا.</b>",
                'banned_user': "🚫 <b>عذراً، تم حظرك من استخدام البوت.</b>",
                'invalid_link': "❌ <b>تعذر التعرف على رابط صالح قابل للتحميل.</b>\nأرسل رابط منشور أو فيديو مباشر من منصة مدعومة.",
                'unsupported_platform': "❌ <b>المنصة الموجودة في هذا الرابط غير مدعومة حالياً.</b>\nالمنصات المدعومة: {platforms}",
                'unsupported_url': "⚠️ <b>تم التعرف على المنصة، لكن صيغة هذا الرابط غير مدعومة حالياً.</b>\nافتح المنشور أو الفيديو نفسه وأرسل رابطه المباشر.",
                'photo_not_supported': "📸 <b>هذا الرابط لا يحتوي على فيديو قابل للتحميل.</b>\nالبوت يدعم الفيديو فقط حالياً، وليس الصور أو المنشورات النصية.",
                'cancel_download': "❌ إلغاء التحميل",
                'download_cancelled': "✅ تم إلغاء التحميل بنجاح.",
                'already_processing': "✋ <b>لديك عملية قيد التنفيذ!</b>\nيرجى انتظار انتهاء التحميل السابق قبل إرسال رابط جديد.",
                'need_subscription': "<b>⚠️ عذراً، يجب عليك الاشتراك في القنوات أدناه لتتمكن من استخدام البوت:</b>",
                'choose_quality': "🎥 <b>اختر جودة التحميل المطلوبة:</b>",
                'download_started': "⏳ جاري جلب الفيديو من المصدر...",
                'download_completed': "📥 تم التحميل للسيرفر! جاري الرفع لك الآن... 🚀",
                'video_caption': "🎬 <b>العنوان والوصف الذي وضعه الناشر:</b>\n\n<b>{title}</b>\n\n{description}\n\n📱 <b>المنصة:</b> {platform} | ⏱ <b>المدة:</b> {duration}\n💾 <b>الحجم:</b> {size} MB\n\n✅ <b>تم التحميل بواسطة:</b>\n{bot_sig}",
                'extract_audio': "🎵 استخراج الصوت",
                'mute_video': "🔇 فيديو صامت",
                'share_bot': "📢 شارك البوت",
                'contact_dev': "👨‍💻 مراسلة المطور",
                'verify_subscription': "🔄 تحقق من الاشتراك",
                'subscribed_success': "<b>✅ تم التحقق بنجاح! يمكنك إرسال الرابط الآن.</b>",
                'not_subscribed': "❌ لم يتم العثور على اشتراكك في جميع القنوات، اشترك ثم حاول مجدداً.",
                'processing': "⏳ جاري المعالجة والفحص...",
                'ffmpeg_missing': "❌ <b>ميزة استخراج الصوت أو كتمه غير متاحة حالياً.</b>\nهناك مشكلة تقنية مؤقتة في أداة المعالجة.",
                'extract_timeout': "⚠️ <b>انتهت صلاحية هذا الطلب.</b>\nأعد إرسال الرابط ثم اختر العملية مرة أخرى.",
                'processing_error': "❌ <b>تم تنزيل الملف لكن تعذر تجهيزه للإرسال.</b>\nحاول مرة أخرى بعد قليل.",
                'download_error': "❌ <b>تعذر إكمال التحميل من المصدر.</b>\nقد يكون الرابط غير مباشر، أو أن المنصة لم تُرجع الملف بشكل صحيح. جرّب لاحقاً أو أرسل الرابط المباشر للمنشور.",
                'weak_connection': "📡 <b>حدثت مشكلة اتصال مؤقتة أثناء الوصول إلى المصدر أو أثناء الإرسال إلى تيليجرام.</b>\nيرجى المحاولة بعد قليل.",
                'file_too_large': "⚠️ <b>حجم الملف كبير للإرسال ({size:.1f} MB).</b>\nالملف يتجاوز حد الرفع الحالي عبر تيليجرام للبوت ({limit_mb} MB).",
                'file_too_large_unknown': "⚠️ <b>حجم الملف أكبر من حد الرفع الحالي عبر تيليجرام للبوت ({limit_mb} MB).</b>\nجرّب جودة أقل أو رابطاً أقصر.",
                'private_or_login': "🔒 <b>هذا المحتوى خاص أو يتطلب تسجيل دخول أو متابعة الحساب لفتحه.</b>",
                'video_unavailable': "❌ <b>هذا الفيديو غير متاح حالياً.</b>\nقد يكون محذوفاً أو مقيّداً أو لم يعد متاحاً من المنصة.",
                'session_expired': "⚠️ <b>انتهت صلاحية الجلسة.</b>\nأعد إرسال الرابط لبدء طلب جديد.",
                'server_busy': "⚠️ <b>الخادم مشغول حالياً بعدة طلبات.</b>\nانتظر قليلاً ثم حاول مرة أخرى.",
                'storage_low': "⚠️ <b>مساحة التخزين على الخادم غير كافية حالياً.</b>\nالمساحة الحرة: {free_gb} GB\nيرجى المحاولة لاحقاً.",
                'no_video_in_post': "📸 <b>هذا المنشور لا يحتوي على فيديو.</b>\nالبوت يدعم الفيديو فقط حالياً.",
                'temporary_source_issue': "⚠️ <b>تعذر قراءة الملف من المنصة حالياً.</b>\nجرّب فتح المنشور وإرسال رابطه المباشر، أو أعد المحاولة لاحقاً.",
                'service_blocked': "⚠️ <b>المنصة رفضت الطلب من جهة الخادم حالياً.</b>\nحاول مرة أخرى لاحقاً.",
                'link_expired': "⚠️ انتهت صلاحية هذا الزر. أعد إرسال الرابط ثم حاول مرة أخرى.",
                'request_processing_failed': "❌ تعذر بدء تنفيذ هذا الطلب حالياً.",
                'operation_failed': "❌ تعذر تنفيذ العملية حالياً.",
                'link_sent': "✅ تم إرسال الرابط في رسالة جديدة.",
                'link_missing': "❌ تعذر العثور على الرابط المرتبط بهذا الطلب.",
                'no_active_download': "❌ لا يوجد تحميل نشط مرتبط بهذا الزر.",
                'subscription_incomplete': "❌ لم يكتمل التحقق من اشتراكك بعد.\nاشترك في جميع القنوات ثم حاول مرة أخرى.",
                'subscription_verified': "✅ تم التحقق من اشتراكك. أرسل الرابط الآن.",
                'id_must_be_numeric': "❌ يجب أن يكون المعرّف أرقاماً فقط. حاول مرة أخرى.",
                'language_set': "✅ تم تغيير اللغة إلى {language}",
                'select_language': "🌍 <b>اختر لغتك المفضلة:</b>",
                'send_link_prompt': "أرسل رابط الفيديو الآن لبدء التحميل.",
                'audio_success': "✅ تم تحميل الصوت\n<b>{bot_sig}</b>",
                'mute_success': "✅ تم كتم الصوت\n<b>{bot_sig}</b>",
                'help_title': "📖 <b>دليل استخدام البوت</b>",
                'help_message': """🤖 <b>{bot_name} - بوت تحميل الفيديوهات العملاق</b>

⚡️ <b>المميزات:</b>
• التحميل من: يوتيوب، فيسبوك، إنستقرام، تيك توك
• التحميل من: بينترست، تويتر (X)، سناب شات، ثريدز
• دقات متعددة: 1080p, 720p, 480p, 360p
• استخراج الصوت كملف MP3 عالي الجودة
• كتم صوت الفيديو (فيديو صامت)
• دعم تحميل الحالات والستوريات

📱 <b>كيفية الاستخدام:</b>
1. أرسل رابط الفيديو أو المنشور
2. اختر الجودة من القائمة التي ستظهر
3. انتظر ثواني ليتم المعالجة والرفع
4. استلم ملفك واستمتع!

⚠️ <b>ملاحظات هامة:</b>
• الحد الأقصى لحجم الملف: {max_size} MB
• تأكد من اشتراكك في القنوات الإجبارية
• لا تستخدم البوت فيما يغضب الله عز وجل كتحميل الموسيقى والصور المحرمة، ولا أجعلك في حل ان فعلت ذلك.
• في حال الفشل، تأكد أن الحساب عام وغير خاص

🔗 <b>القنوات المطلوبة للاشتراك:</b>
{channels}

📞 <b>للتواصل والدعم:</b>
يمكنك التواصل مع المطور لأي استفسار أو مساعدة.""",
                'admin_panel': "🛠 <b>لوحة تحكم المدير</b>",
                'main_menu_buttons': {
                    'start_download': '📢 مشاركة البوت',
                    'help': '🆘 المساعدة',
                    'language': '🌍 تغيير اللغة',
                    'contact': '👨‍💻 المطور',
                    'bots_list': '🤖 قائمة بوتاتنا',
                    'user_stats': '📊 إحصائياتي',
                    'admin_panel': '🛠 لوحة التحكم'
                },
                'bots_list_text': """هذه قائمة البوتات الخاصة بنا:

1- 🤖 إدارة الفتاوى | Fatwa CMS:
مشروع خيري يهدف لأرشفة ونشر فتاوى العلماء الثقات، وتسهيل الوصول إليها عبر التليجرام.

🎯 ماذا يمكنه أن يفعل لك؟
• محرك بحث سريع ودقيق.
• تصنيف موضوعي شامل.
• دعم الوسائط المتعددة (نص، صوت، روابط).
• إمكانية النشر التلقائي للقنوات والمجموعات.

🔥 جربه الآن: @Fatwa_CMS_Bot

2- 🤖 العملاق للمستندات | Titan Pdf Pro :

🎯 ماذا يمكنه أن يفعل لك؟

بوت متخصص في معالجة ملفات PDF والصور والنصوص، يقوم بالعديد من المهام:
• تحويل الصور إلى PDF والعكس
• دمج وتقسيم ملفات PDF
• حماية وضغط الملفات
• إضافة علامات مائية والمزيد

🔥 جربه الآن: @TitanPdfBot

3- 🤖 العملاق للتحميل | Titan Downloader :

🎯 ماذا يمكنه أن يفعل لك؟

يتيح لك تحميل فيديوهاتك المفضلة بأعلى جودة ممكنة، بالإضافة إلى استخراج الصوت منها بكل سهولة وسرعة، حيث يُعتبر سريعًا ومجانيًا وسهل الاستخدام ✅️. يمكنه تحميل الفيديوهات القصيرة من منصات مثل يوتيوب، تيك توك، فيسبوك، وإنستجرام.

⛔️ تنبيه: لا تستخدم البوت فيما يغضب الله عز وجل كتحميل الموسيقى والصور المحرمة!

🔥 جربه الآن: @TitanSvBot

4- 🤖 بوت فذكر الدعوي:

بوت "فَذَكِّر" رفيقك اليومي للتذكير بالصلوات، الأذكار، والسنن، ونشر الفوائد والفيديوهات الدعوية، أضفه لقناتك أو مجموعتك لنشر الخير.

🔥 جربه الآن:  @Fadhakir_bot""",
                'main_menu': "🏠 القائمة الرئيسية",
                'broadcast_to_all': '📢 لكل المستخدمين',
                'broadcast_to_user': '👤 لمستخدم محدد',
                'cancel_broadcast': '❌ إلغاء البث',
                'share_message': """🚀 إليك بوت العملاق للتحميل!
📥 حمّل فيديوهاتك المفضلة من يوتيوب، تيك توك، فيسبوك، وإنستقرام بأعلى جودة وبكل سهولة.

جرب البوت الآن من هنا:
@{bot_username}""",
                'user_stats_msg': """📊 <b>إحصائياتك الشخصية:</b>

👤 <b>الاسم:</b> {name}
🆔 <b>المعرف:</b> <code>{uid}</code>
📅 <b>تاريخ الانضمام:</b> {join_date}
📥 <b>إجمالي التحميلات:</b> {download_count} فيديو
🏆 <b>رتبتك:</b> {rank} من أصل {total_users} مستخدم""",
            },
            'en': {
                'welcome_title': "🎉 Welcome to {bot_name}",
                'welcome_message': """⚡️ <b>Features:</b>
• Download from YouTube, TikTok, Facebook, Instagram
• Support for high and medium quality
• Extract audio from video
• Mute video
• Support for long videos

📊 <b>Bot Statistics:</b>
• Total users: {total_users}
• Daily downloads: {daily_downloads}

🎬 <b>How to use:</b>
1. Send video link
2. Choose quality
3. Receive video

⚠️ <b>Important notes:</b>
• Maximum size: {max_size} MB
• Prohibited use of the bot for forbidden content""",
                'start_message': """<b>{bot_sig}</b>

Send a video link from (YouTube, TikTok, Facebook, Instagram).

⛔️ Warning: Do not use the bot for what angers Allah Almighty such as downloading music and forbidden images!

🔥What are you waiting for! Send the link now and let's start!""",
                'maintenance_mode': "🛠 <b>Sorry, the bot is in maintenance mode, try later.</b>",
                'banned_user': "🚫 <b>Sorry, you are banned from using the bot.</b>",
                'invalid_link': "❌ <b>Couldn't detect a valid video link.</b>\nSend a direct post or video link from a supported platform.",
                'unsupported_platform': "⚠️ <b>This platform is not supported right now.</b>\nSupported platforms: {platforms}",
                'unsupported_url': "⚠️ <b>The platform was recognized, but this link format is not supported right now.</b>\nOpen the post or video itself and send its direct link.",
                'photo_not_supported': "⚠️ <b>This link does not point to a downloadable video.</b>\nThe bot currently supports videos only, not photo or text posts.",
                'cancel_download': "❌ Cancel Download",
                'download_cancelled': "✅ Download cancelled.",
                'already_processing': "✋ <b>You have a download in progress!</b>\nPlease wait until the current video finishes, then resend the link.",
                'need_subscription': "<b>Sorry dear, you must subscribe to the following channels to use the bot:</b>",
                'choose_quality': "🎥 <b>Choose download quality:</b>",
                'download_started': "Downloading from source...",
                'download_completed': "📥 Downloaded to server! Uploading to you... 🚀",
                'video_caption': "🎬 <b>Title and description set by the publisher:</b>\n\n{title}\n\n{description}\n\n📱 <b>Platform:</b> {platform}\n⏱ <b>Duration:</b> {duration}\n💾 <b>Size:</b> {size} MB\n✅ <b>Downloaded successfully</b>\n{bot_sig}",
                'extract_audio': "🎵 Extract Audio",
                'mute_video': "🔇 Mute Video",
                'share_bot': "📢 Share Bot",
                'contact_dev': "👨‍💻 Contact Developer",
                'verify_subscription': "🔄 Verify Subscription",
                'subscribed_success': "<b>✅ Subscribed successfully! Send the link now.</b>",
                'not_subscribed': "❌ Not subscribed yet! Subscribe and try again.",
                'processing': "⏳ Processing...",
                'ffmpeg_missing': "❌ <b>Audio extraction or mute is temporarily unavailable.</b>\nThere is a technical issue with the processing tool.",
                'extract_timeout': "⚠️ <b>This request has expired.</b>\nPlease resend the link and choose the action again.",
                'processing_error': "❌ <b>The file was downloaded, but it could not be prepared for sending.</b>\nPlease try again later.",
                'download_error': "❌ <b>Couldn't complete the download from the source.</b>\nThe link may not be direct, or the platform did not return the media properly. Try again later or send the direct post link.",
                'weak_connection': "📡 <b>A temporary network issue happened while reaching the source or sending the file to Telegram.</b>\nPlease try again in a moment.",
                'file_too_large': "⚠️ <b>The file is too large to send ({size:.1f} MB).</b>\nIt exceeds the bot's current Telegram upload limit ({limit_mb} MB).",
                'file_too_large_unknown': "⚠️ <b>The file is larger than the bot's current Telegram upload limit ({limit_mb} MB).</b>\nTry a lower quality or a shorter link.",
                'private_or_login': "🔒 <b>This content is private or requires login or following the account to access it.</b>",
                'video_unavailable': "❌ <b>This video is not currently available.</b>\nIt may have been deleted, restricted, or removed by the platform.",
                'session_expired': "⚠️ <b>This session has expired.</b>\nPlease resend the link to start a new request.",
                'server_busy': "⚠️ <b>The server is busy with several requests right now.</b>\nPlease wait a little and try again.",
                'storage_low': "⚠️ <b>The server does not currently have enough free storage.</b>\nFree space: {free_gb} GB\nPlease try again later.",
                'no_video_in_post': "⚠️ <b>This post does not contain a video.</b>\nThe bot currently supports videos only.",
                'temporary_source_issue': "⚠️ <b>The platform could not return the media properly right now.</b>\nTry opening the post and sending its direct link, or try again later.",
                'service_blocked': "⚠️ <b>The platform is temporarily rejecting requests from the server.</b>\nPlease try again later.",
                'link_expired': "⚠️ This button has expired. Resend the link and try again.",
                'request_processing_failed': "❌ Could not start this request right now.",
                'operation_failed': "❌ Could not complete this action right now.",
                'link_sent': "✅ The link was sent in a new message.",
                'link_missing': "❌ The link for this request could not be found.",
                'no_active_download': "❌ There is no active download linked to this button.",
                'subscription_incomplete': "❌ Your subscription check is not complete yet.\nSubscribe to all required channels, then try again.",
                'subscription_verified': "✅ Subscription verified. You can send the link now.",
                'id_must_be_numeric': "❌ The user ID must contain digits only. Please try again.",
                'language_set': "✅ Language changed to {language}",
                'select_language': "🌍 <b>Select your preferred language:</b>",
                'send_link_prompt': "Send the video link now to start downloading.",
                'audio_success': "✅ Audio downloaded\n<b>{bot_sig}</b>",
                'mute_success': "✅ Video muted\n<b>{bot_sig}</b>",
                'help_title': "📖 <b>Bot User Guide</b>",
                'help_message': """🤖 <b>{bot_name} - Video Downloader Bot</b>

⚡️ <b>Features:</b>
• Download videos from YouTube, TikTok, Facebook, Instagram
• Multiple quality options (High, Medium)
• Extract audio from videos
• Mute video sound
• Support for long videos

📱 <b>How to Use:</b>
1. Send the video link
2. Choose download quality
3. Wait for the download to complete
4. Receive the ready video

⚙️ <b>Available Commands:</b>
• /start - Start using the bot
• /help - Show this message
• /language - Change language
• /boss - Control Panel (Admin Only)

⚠️ <b>Important Notes:</b>
• Maximum video size: {max_size} MB
• Ensure you are subscribed to required channels
• Do not use the bot for forbidden content
• Contact developer if you encounter issues

🔗 <b>Required Channels:</b>
{channels}

📞 <b>Contact & Support:</b>
Contact developer for any inquiries.""",
                'admin_panel': "🛠 <b>Admin Control Panel</b>",
                'main_menu_buttons': {
                    'start_download': '📢 Share Bot',
                    'help': '🆘 Help',
                    'language': '🌍 Change Language',
                    'contact': '👨‍💻 Developer',
                    'bots_list': '🤖 Our Bots List',
                    'user_stats': '📊 My Stats',
                    'admin_panel': '🛠 Admin Panel'
                },
                'bots_list_text': """This is our list of bots:

1- 🤖 Fatwa Management | Fatwa CMS:
A charitable project aimed at archiving and publishing the fatwas of trusted scholars, and facilitating access to them via Telegram.

🎯 What can it do for you?
• Fast and accurate search engine.
• Comprehensive thematic classification.
• Multimedia support (text, audio, links).
• Automatic publishing to channels and groups.

🔥 Try it now: @Fatwa_CMS_Bot

2- 🤖 Titan PDF Pro:

🎯 What can it do for you?

A bot specialized in processing PDF files, images, and text, performing many tasks:
• Convert images to PDF and vice versa
• Merge and split PDF files
• Protect and compress files
• Add watermarks and more

🔥 Try it now: @TitanPdfBot

3- 🤖 Titan Downloader:

🎯 What can it do for you?

Allows you to download your favorite videos in the highest possible quality, plus extract audio easily and quickly. It's fast, free, and easy to use ✅. Can download shorts from platforms like YouTube, TikTok, Facebook, and Instagram.

⛔️ Warning: Do not use the bot for what angers Allah Almighty!

🔥 Try it now: @TitanSvBot

4- 🤖 Fadhakir Bot:

The "Fadhakir" bot is your daily companion for reminders of prayers, dhikr, and sunnahs... Add it to your channel or group to spread goodness.

🔥 Try it now: @Fadhakir_bot""",
                'main_menu': "🏠 Main Menu",
                'broadcast_to_all': '📢 To All Users',
                'broadcast_to_user': '👤 To Specific User',
                'cancel_broadcast': '❌ Cancel Broadcast',
                'share_message': """🚀 Check out the Giant Downloader Bot!
📥 Download your favorite videos from YouTube, TikTok, Facebook, and Instagram in high quality.

Try it now: @{bot_username}""",
                'user_stats_msg': """📊 <b>Your Personal Stats:</b>

👤 <b>Name:</b> {name}
🆔 <b>ID:</b> <code>{uid}</code>
📅 <b>Join Date:</b> {join_date}
📥 <b>Total Downloads:</b> {download_count} videos
🏆 <b>Your Rank:</b> {rank} out of {total_users} users""",
            },
            'fr': {
                'welcome_title': "🎉 Bienvenue sur {bot_name}",
                'welcome_message': """⚡️ <b>Fonctionnalités :</b>
• Télécharger depuis YouTube, TikTok, Facebook, Instagram
• Support haute et moyenne qualité
• Extraire l'audio de la vidéo
• Couper le son de la vidéo
• Support des vidéos longues

📊 <b>Statistiques du Bot :</b>
• Utilisateurs : {total_users}
• Téléchargements quotidiens : {daily_downloads}

🎬 <b>Comment utiliser :</b>
1. Envoyez le lien vidéo
2. Choisissez la qualité
3. Recevez la vidéo

⚠️ <b>Notes importantes :</b>
• Taille max : {max_size} MB
• Interdit d'utiliser le bot pour du contenu illicite""",
                'start_message': """<b>{bot_sig}</b>

Envoyez un lien vidéo de (YouTube, TikTok, Facebook, Instagram).

⛔️ Avertissement : N'utilisez pas le bot pour ce qui met Dieu en colère comme la musique et les images interdites !

🔥Qu'attendez-vous ! Envoyez le lien maintenant et commençons !""",
                'maintenance_mode': "🛠 <b>Désolé, le bot est en maintenance, réessayez plus tard.</b>",
                'banned_user': "🚫 <b>Désolé, vous êtes banni de l'utilisation du bot.</b>",
                'invalid_link': "❌ <b>Impossible de reconnaître un lien vidéo valide.</b>\nEnvoyez un lien direct de post ou de vidéo depuis une plateforme prise en charge.",
                'unsupported_platform': "⚠️ <b>Cette plateforme n'est pas prise en charge pour le moment.</b>\nPlateformes supportées : {platforms}",
                'unsupported_url': "⚠️ <b>La plateforme a été reconnue, mais ce format de lien n'est pas pris en charge pour le moment.</b>\nOuvrez le post ou la vidéo et envoyez son lien direct.",
                'photo_not_supported': "⚠️ <b>Ce lien ne pointe pas vers une vidéo téléchargeable.</b>\nLe bot prend actuellement en charge les vidéos uniquement, pas les publications photo ou texte.",
                'cancel_download': "❌ Annuler le téléchargement",
                'download_cancelled': "✅ Téléchargement annulé.",
                'already_processing': "✋ <b>Vous avez un téléchargement en cours !</b>\nVeuillez attendre que la vidéo actuelle se termine, puis renvoyez le lien.",
                'need_subscription': "<b>Désolé cher, vous devez vous abonner aux chaînes suivantes :</b>",
                'choose_quality': "🎥 <b>Choisissez la qualité :</b>",
                'download_started': "Téléchargement depuis la source...",
                'download_completed': "📥 Téléchargé sur le serveur ! Envoi vers vous... 🚀",
                'video_caption': "🎬 <b>Titre et description définis par l'éditeur :</b>\n\n{title}\n\n{description}\n\n📱 <b>Plateforme :</b> {platform}\n⏱ <b>Durée :</b> {duration}\n💾 <b>Taille :</b> {size} MB\n✅ <b>Téléchargé avec succès</b>\n{bot_sig}",
                'extract_audio': "🎵 Extraire l'audio",
                'mute_video': "🔇 Muet",
                'share_bot': "📢 Partager",
                'contact_dev': "👨‍💻 Contact dév",
                'verify_subscription': "🔄 Vérifier l'abonnement",
                'subscribed_success': "<b>✅ Abonné avec succès ! Envoyez le lien maintenant.</b>",
                'not_subscribed': "❌ Pas encore abonné ! Abonnez-vous et réessayez.",
                'processing': "⏳ Traitement...",
                'ffmpeg_missing': "❌ <b>L'extraction audio ou le mode muet est temporairement indisponible.</b>\nIl y a un problème technique avec l'outil de traitement.",
                'extract_timeout': "⚠️ <b>Cette demande a expiré.</b>\nRenvoyez le lien puis choisissez l'action à nouveau.",
                'processing_error': "❌ <b>Le fichier a été téléchargé, mais il n'a pas pu être préparé pour l'envoi.</b>\nVeuillez réessayer plus tard.",
                'download_error': "❌ <b>Impossible de terminer le téléchargement depuis la source.</b>\nLe lien n'est peut-être pas direct, ou la plateforme n'a pas renvoyé correctement le média. Réessayez plus tard ou envoyez le lien direct du post.",
                'weak_connection': "📡 <b>Un problème réseau temporaire s'est produit lors de l'accès à la source ou de l'envoi du fichier à Telegram.</b>\nVeuillez réessayer dans un instant.",
                'file_too_large': "⚠️ <b>Le fichier est trop volumineux pour l'envoi ({size:.1f} MB).</b>\nIl dépasse la limite d'envoi actuelle du bot sur Telegram ({limit_mb} MB).",
                'file_too_large_unknown': "⚠️ <b>Le fichier dépasse la limite d'envoi actuelle du bot sur Telegram ({limit_mb} MB).</b>\nEssayez une qualité plus basse ou un lien plus court.",
                'private_or_login': "🔒 <b>Ce contenu est privé ou nécessite une connexion ou le suivi du compte pour y accéder.</b>",
                'video_unavailable': "❌ <b>Cette vidéo n'est pas disponible actuellement.</b>\nElle a peut-être été supprimée, restreinte ou retirée par la plateforme.",
                'session_expired': "⚠️ <b>Cette session a expiré.</b>\nRenvoyez le lien pour démarrer une nouvelle demande.",
                'server_busy': "⚠️ <b>Le serveur est occupé par plusieurs demandes en ce moment.</b>\nVeuillez patienter un peu puis réessayer.",
                'storage_low': "⚠️ <b>Le serveur ne dispose pas actuellement d'un espace de stockage suffisant.</b>\nEspace libre : {free_gb} GB\nVeuillez réessayer plus tard.",
                'no_video_in_post': "⚠️ <b>Ce post ne contient pas de vidéo.</b>\nLe bot prend actuellement en charge les vidéos uniquement.",
                'temporary_source_issue': "⚠️ <b>La plateforme n'a pas pu renvoyer correctement le média pour le moment.</b>\nEssayez d'ouvrir le post et d'envoyer son lien direct, ou réessayez plus tard.",
                'service_blocked': "⚠️ <b>La plateforme refuse temporairement les requêtes provenant du serveur.</b>\nVeuillez réessayer plus tard.",
                'link_expired': "⚠️ Ce bouton a expiré. Renvoyez le lien puis réessayez.",
                'request_processing_failed': "❌ Impossible de démarrer cette demande pour le moment.",
                'operation_failed': "❌ Impossible d'exécuter cette action pour le moment.",
                'link_sent': "✅ Le lien a été envoyé dans un nouveau message.",
                'link_missing': "❌ Impossible de retrouver le lien associé à cette demande.",
                'no_active_download': "❌ Aucun téléchargement actif n'est lié à ce bouton.",
                'subscription_incomplete': "❌ La vérification de votre abonnement n'est pas encore complète.\nAbonnez-vous à toutes les chaînes requises puis réessayez.",
                'subscription_verified': "✅ Abonnement vérifié. Vous pouvez envoyer le lien maintenant.",
                'id_must_be_numeric': "❌ L'identifiant utilisateur doit contenir uniquement des chiffres. Veuillez réessayer.",
                'language_set': "✅ Langue changée en {language}",
                'select_language': "🌍 <b>Choisissez votre langue :</b>",
                'send_link_prompt': "Envoyez le lien vidéo maintenant pour lancer le téléchargement.",
                'audio_success': "✅ Audio téléchargé\n<b>{bot_sig}</b>",
                'mute_success': "✅ Vidéo muette\n<b>{bot_sig}</b>",
                'help_title': "📖 <b>Guide d'utilisation</b>",
                'help_message': """🤖 <b>{bot_name} - Bot de Téléchargement</b>

⚡️ <b>Fonctionnalités :</b>
• Télécharger depuis YouTube, TikTok, Facebook, Instagram
• Qualités multiples
• Extraire l'audio
• Couper le son
• Vidéos longues

📱 <b>Utilisation :</b>
1. Envoyez le lien
2. Choisissez la qualité
3. Attendez la fin du téléchargement
4. Recevez la vidéo

⚙️ <b>Commandes :</b>
• /start - Démarrer
• /help - Aide
• /language - Changer la langue
• /boss - Panel Admin

⚠️ <b>Notes :</b>
• Taille max : {max_size} MB
• Abonnement requis
• Pas de contenu illicite

🔗 <b>Chaînes requises :</b>
{channels}""",
                'admin_panel': "🛠 <b>Panneau d'administration</b>",
                'main_menu_buttons': {
                    'start_download': '📢 Partager le bot',
                    'help': '🆘 Aide',
                    'language': '🌍 Langue',
                    'contact': '👨‍💻 Développeur',
                    'bots_list': '🤖 Nos Bots',
                    'user_stats': '📊 Mes Stats',
                    'admin_panel': '🛠 Admin'
                },
                'bots_list_text': """Voici la liste de nos bots :

1- 🤖 Gestion des Fatwas | Fatwa CMS :
Un projet caritatif visant à archiver et publier les fatwas de savants de confiance.

🎯 Que peut-il faire pour vous ?
• Moteur de recherche rapide.
• Classification thématique.
• Support multimédia.
• Publication automatique.

🔥 Essayez maintenant : @Fatwa_CMS_Bot

2- 🤖 Titan PDF Pro :

🎯 Que peut-il faire pour vous ?

Spécialisé dans le traitement des fichiers PDF, images et textes :
• Conversion d'images en PDF
• Fusionner et diviser des PDF
• Protection et compression
• Filigranes et plus

🔥 Essayez maintenant : @TitanPdfBot

3- 🤖 Titan Downloader :

🎯 Que peut-il faire pour vous ?

Téléchargez vos vidéos préférées en haute qualité et extrayez l'audio facilement. Rapide, gratuit et simple ✅. YouTube, TikTok, Facebook, Instagram.

⛔️ Alerte : Ne l'utilisez pas pour ce qui fâche Allah !

🔥 Essayez maintenant : @TitanSvBot

4- 🤖 Bot Fadhakir :

Votre compagnon quotidien pour les rappels de prières, dhikr et sunnahs... À ajouter à votre canal ou groupe.

🔥 Essayez maintenant : @Fadhakir_bot""",
                'main_menu': "🏠 Menu Principal",
                'broadcast_to_all': '📢 À tous',
                'broadcast_to_user': '👤 Utilisateur spécifique',
                'cancel_broadcast': '❌ Annuler',
                'share_message': """🚀 Découvrez le Bot de Téléchargement Géant !
📥 Téléchargez vos vidéos préférées depuis YouTube, TikTok, Facebook et Instagram en haute qualité.

Essayez-le maintenant : @{bot_username}""",
                'user_stats_msg': """📊 <b>Vos Statistiques :</b>

👤 <b>Nom :</b> {name}
🆔 <b>ID :</b> <code>{uid}</code>
📅 <b>Date d'inscription :</b> {join_date}
📥 <b>Total téléchargements :</b> {download_count} vidéos
🏆 <b>Votre Rang :</b> {rank} sur {total_users} utilisateurs""",
            }
        }
        
        # استرجاع النص مع التنسيق
        data = translations.get(lang, translations['ar'])
        text = data.get(translation_key, translation_key)
        
        # دعم المفاتيح الفرعية إذا كان النص قاموساً
        if isinstance(text, dict) and 'key' in kwargs:
            subkey = kwargs.pop('key')
            text = text.get(subkey, subkey)
            
        if kwargs:
            try:
                return text.format(**kwargs)
            except:
                return text
        return text

# تصدير نسخة واحدة للاستخدام
translation_system = TranslationSystem()
