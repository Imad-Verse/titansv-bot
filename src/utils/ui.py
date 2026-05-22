from telebot import types
from src.services.translation import translation_system
from src.core.config import Config

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


def _format_size(size_mb):
    """تنسيق الحجم بشكل مقروء"""
    if size_mb <= 0:
        return ""
    if size_mb >= 1024:
        return f"~{size_mb/1024:.1f} GB"
    return f"~{size_mb:.0f} MB"


def _find_tier_size(resolutions, tier):
    """إيجاد الحجم التقريبي لمستوى جودة معين بناءً على الجودات المتوفرة"""
    if not resolutions:
        return 0
    
    high_size = resolutions[0].get('size_mb', 0)
    
    if tier == 'high':
        return high_size
    
    target = 480 if tier == 'medium' else 360
    
    # 1. البحث عن جودة قريبة جداً من الارتفاع المستهدف (±40 بكسل)
    best = None
    for r in resolutions:
        h = r.get('height', 0)
        if abs(h - target) <= 40:
            best = r
            break
            
    if best:
        return best.get('size_mb', 0)
        
    # 2. إذا لم نجد، نبحث عن أقرب جودة عند أو تحت الارتفاع المستهدف
    for r in resolutions:
        h = r.get('height', 0)
        if h <= target:
            best = r
            break
            
    if best:
        return best.get('size_mb', 0)
        
    # 3. إذا لم يتوفر الحجم الفعلي لتلك الجودة، نقوم بتقديره نسبةً للجودة العالية المتاحة
    if high_size > 0:
        high_height = resolutions[0].get('height', 1080)
        if high_height > 0:
            # استخدام نسب البتات التقريبية (H.264 Bitrate ratios) لتقدير الحجم
            if tier == 'medium':
                # حوالي 35% من حجم 1080p، أو 50% من حجم 720p
                factor = 0.35 if high_height >= 1080 else (0.50 if high_height >= 720 else 0.70)
            else:
                # حوالي 18% من حجم 1080p، أو 25% من حجم 720p، أو 50% من حجم 480p
                factor = 0.18 if high_height >= 1080 else (0.25 if high_height >= 720 else (0.50 if high_height >= 480 else 0.80))
            return high_size * factor

    fallback = resolutions[-1] if resolutions else None
    return fallback.get('size_mb', 0) if fallback else 0


def create_quality_keyboard(user_id, sid, info=None):
    """إنشاء لوحة مفاتيح خيارات الجودة ديناميكياً بناءً على الجودات المتوفرة فعلياً في الفيديو"""
    markup = types.InlineKeyboardMarkup()
    
    resolutions = []
    max_height = 0
    
    if info and info.get('resolutions'):
        resolutions = info['resolutions']
        if resolutions:
            max_height = max(r.get('height', 0) for r in resolutions)
    
    if max_height > 0:
        # === بناء الأزرار ديناميكياً بناءً على الجودات الفعلية ===
        
        # 🎬 جودة عالية (HD): تظهر فقط إذا توفرت جودة ≥720p
        if max_height >= 720:
            best_h = resolutions[0].get('height', 720)
            size_mb = _find_tier_size(resolutions, 'high')
            size_txt = f" ({_format_size(size_mb)})" if size_mb > 0 else ""
            markup.row(types.InlineKeyboardButton(
                f"🎬 جودة عالية {best_h}p{size_txt}",
                callback_data=f"dl_high|{sid}"
            ))
        
        # 📺 جودة متوسطة (SD): تظهر فقط إذا توفرت جودة ≥480p
        if max_height >= 480:
            size_mb = _find_tier_size(resolutions, 'medium')
            size_txt = f" ({_format_size(size_mb)})" if size_mb > 0 else ""
            markup.row(types.InlineKeyboardButton(
                f"📺 جودة متوسطة 480p{size_txt}",
                callback_data=f"dl_medium|{sid}"
            ))
        
        # 📱 جودة ضعيفة: تظهر دائماً كخيار احتياطي صغير الحجم
        size_mb = _find_tier_size(resolutions, 'low')
        size_txt = f" ({_format_size(size_mb)})" if size_mb > 0 else ""
        markup.row(types.InlineKeyboardButton(
            f"📱 جودة ضعيفة 360p{size_txt}",
            callback_data=f"dl_low|{sid}"
        ))
    else:
        # لم نتمكن من استخراج بيانات الجودة — نعرض كل الخيارات كاحتياط
        markup.row(types.InlineKeyboardButton("🎬 جودة عالية (HD)", callback_data=f"dl_high|{sid}"))
        markup.row(types.InlineKeyboardButton("📺 جودة متوسطة (SD)", callback_data=f"dl_medium|{sid}"))
        markup.row(types.InlineKeyboardButton("📱 جودة ضعيفة", callback_data=f"dl_low|{sid}"))
    
    # === أزرار ثابتة (تظهر دائماً) ===
    markup.row(types.InlineKeyboardButton("🎵 تحميل صوت فقط (MP3)", callback_data=f"audio_{sid}"))
    markup.row(types.InlineKeyboardButton("🔙 إلغاء والرجوع", callback_data="menu_back_to_main"))
    
    return markup
