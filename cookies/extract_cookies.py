from browser_cookie3 import chrome, firefox, edge
import os

# مسار مجلد الكوكيز
COOKIES_DIR = os.path.dirname(os.path.abspath(__file__))

# قائمة المنصات
platforms = {
    'youtube': ['youtube.com', 'youtu.be'],
    'facebook': ['facebook.com', 'fb.watch'],
    'tiktok': ['tiktok.com'],
    'instagram': ['instagram.com'],
    'twitter': ['twitter.com', 'x.com']
}

def extract_cookies():
    try:
        # محاولة الحصول على الكوكيز من Chrome
        cookies = chrome(domain_name='')
        print(f"تم العثور على {len(list(cookies))} كوكي")
        
        for platform, domains in platforms.items():
            platform_cookies = []
            for cookie in cookies:
                for domain in domains:
                    if domain in cookie.domain:
                        platform_cookies.append(cookie)
            
            if platform_cookies:
                # حفظ الكوكيز في ملف
                file_path = os.path.join(COOKIES_DIR, f"{domains[0]}_cookies.txt")
                with open(file_path, 'w', encoding='utf-8') as f:
                    for cookie in platform_cookies:
                        f.write(f"{cookie.domain}\tTRUE\t{cookie.path}\t{str(cookie.secure).upper()}\t{cookie.expires or 0}\t{cookie.name}\t{cookie.value}\n")
                
                print(f"تم حفظ {len(platform_cookies)} كوكي لـ {platform}")
                
    except Exception as e:
        print(f"خطأ: {e}")

if __name__ == "__main__":
    extract_cookies()
