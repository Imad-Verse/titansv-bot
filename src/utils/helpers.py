import re
import secrets
from urllib.parse import urlparse, urlunparse, parse_qs, urlencode

def format_seconds(seconds):
    """تنسيق الوقت من ثواني إلى (HH:MM:SS) أو (MM:SS)"""
    if not seconds: return "00:00"
    try:
        seconds = int(float(seconds))
        m, s = divmod(seconds, 60)
        h, m = divmod(m, 60)
        if h > 0:
            return f"{h:02d}:{m:02d}:{s:02d}"
        return f"{m:02d}:{s:02d}"
    except:
        return "00:00"

def format_size(size_bytes):
    """تحويل الحجم من بايت إلى صيغة مقروءة (MB, GB, etc.)"""
    if size_bytes == 0: return "0 B"
    size_name = ("B", "KB", "MB", "GB", "TB")
    import math
    i = int(math.floor(math.log(size_bytes, 1024)))
    p = math.pow(1024, i)
    s = round(size_bytes / p, 2)
    return f"{s} {size_name[i]}"

def detect_platform_from_url(url):
    """اكتشاف المنصة المدعومة من خلال الرابط"""
    if not url: return 'other'
    try:
        domain = urlparse(url).netloc.lower()
        if not domain: # قد يكون الرابط بدون http
            domain = urlparse(f"http://{url}").netloc.lower()
            
        if any(x in domain for x in ['instagram.com', 'instagr.am']): return 'instagram'
        if any(x in domain for x in ['facebook.com', 'fb.watch', 'fb.com', 'fb.me']): return 'facebook'
        if 'tiktok.com' in domain: return 'tiktok'
        if any(x in domain for x in ['twitter.com', 'x.com', 't.co']): return 'twitter'
        if any(x in domain for x in ['youtube.com', 'youtu.be']): return 'youtube'
        if any(x in domain for x in ['pinterest.com', 'pin.it']): return 'pinterest'
        if 'threads.net' in domain: return 'threads'
        if 'snapchat.com' in domain: return 'snapchat'
        if any(x in domain for x in ['soundcloud.com', 'snd.sc']): return 'soundcloud'
        if 'vimeo.com' in domain: return 'vimeo'
        if any(x in domain for x in ['dailymotion.com', 'dai.ly']): return 'dailymotion'
        if any(x in domain for x in ['reddit.com', 'redd.it']): return 'reddit'
        if any(x in domain for x in ['kwai.com', 'kwaishow.com']): return 'kwai'
        if any(x in domain for x in ['likee.video', 'like.video']): return 'likee'
        if 'twitch.tv' in domain: return 'twitch'
    except: pass
    return 'other'

def clean_url(url):
    """إزالة معلمات التتبع (Tracking Parameters) من الرابط"""
    if not url: return url
    try:
        parsed = urlparse(url)
        # المعلمات التي نريد الإبقاء عليها لكل منصة
        keep_params = {
            'youtube.com': ['v', 't'],
            'youtu.be': ['t'],
        }
        
        domain = parsed.netloc.lower()
        query = parse_qs(parsed.query)
        
        # قائمة المعلمات المسموحة لهذا الدومين
        allowed = []
        for d, params in keep_params.items():
            if d in domain:
                allowed = params
                break
        
        # تصفية المعلمات
        new_query = {k: v for k, v in query.items() if k in allowed}
        
        # إعادة بناء الرابط بدون المعلمات الزائدة
        new_url = urlunparse(parsed._replace(query=urlencode(new_query, doseq=True)))
        return new_url
    except:
        return url

def truncate_text(text, max_length=100):
    """تقصير النص الطويل مع إضافة نقاط في النهاية بشكل ذكي"""
    if not text: return ""
    if len(text) <= max_length: return text
    return text[:max_length-3].strip() + "..."

def sanitize_filename(name):
    """تنظيف اسم الملف من الأحرف غير المسموحة مع دعم اليونيكود"""
    if not name: return "unnamed_file"
    # حذف الرموز الصفرية
    name = name.replace('\0', '')
    # الإبقاء على الأحرف (بما فيها العربية)، الأرقام، والرموز الآمنة
    name = re.sub(r'[^\w\s.-]', '', name, flags=re.UNICODE)
    # تقليل المسافات المتكررة واستبدالها بمسافة واحدة أو شرطة
    name = re.sub(r'\s+', ' ', name).strip()
    return name[:150] or "unnamed_file"

def generate_sid(prefix=""):
    """توليد معرف فريد قصير لاستخدامه في callback_data وأسماء الملفات"""
    return f"{prefix}{secrets.token_hex(6)}"

def get_media_unique_id(url):
    """استخراج معرف فريد للمحتوى (مثل ID الفيديو) لاستخدامه في الكاش"""
    if not url: return None
    try:
        platform = detect_platform_from_url(url)
        parsed = urlparse(url)
        
        if platform == 'youtube':
            if 'youtu.be' in parsed.netloc:
                return parsed.path.lstrip('/')
            query = parse_qs(parsed.query)
            if 'v' in query:
                return query['v'][0]
                
        elif platform == 'tiktok':
            # الروابط غالباً تكون tiktok.com/@user/video/ID
            parts = parsed.path.strip('/').split('/')
            if 'video' in parts:
                return parts[parts.index('video') + 1].split('?')[0]
            elif parts and parts[-1].isdigit():
                return parts[-1].split('?')[0]
                
        elif platform == 'instagram':
            # الروابط غالباً تكون instagram.com/reels/ID/ أو instagram.com/p/ID/
            parts = parsed.path.strip('/').split('/')
            if parts and parts[0] in ['reels', 'reel', 'p', 'tv']:
                return parts[1].split('?')[0]
                
        elif platform == 'facebook':
            query = parse_qs(parsed.query)
            if 'v' in query: return query['v'][0]
            if 'videos' in parsed.path:
                parts = parsed.path.strip('/').split('/')
                return parts[-1].split('?')[0]
                
        # إذا لم نجد معرفاً خاصاً، نستخدم الرابط المنظف (Clean URL) كمعرف
        return clean_url(url)
    except:
        return url
