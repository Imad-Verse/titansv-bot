import random
import threading
from src.core.config import Config
from src.core.utils import logger

class ProxyManager:
    _instance = None
    _lock = threading.Lock()

    def __new__(cls):
        with cls._lock:
            if cls._instance is None:
                cls._instance = super(ProxyManager, cls).__new__(cls)
                cls._instance._initialized = False
            return cls._instance

    def __init__(self):
        if self._initialized: return
        self.proxies = []
        self.current_index = 0
        self._initialized = True
        # بدء عملية التحميل في الخلفية لتجنب تجميد البوت (Background initialization)
        import time
        threading.Thread(target=self._initial_load, daemon=True).start()

    def _initial_load(self):
        """تحميل أولي للبروكسيات (يتم تشغيله في ثريد منفصل)"""
        try:
            # 1. تحميل الموجود محلياً أولاً للبدء بسرعة
            self._load_from_file()
            
            # 2. إذا لم يوجد بروكسيات أو كان الملف قديماً، نحدث من الرابط
            if Config.USE_PROXIES and Config.PROXIES_URL:
                # إذا كانت القائمة فارغة، نحدث فوراً، وإلا ننتظر قليلاً لبدء البوت بسلاسة
                if not self.proxies:
                    self.fetch_from_url()
                else:
                    # تحديث هادئ بعد 30 ثانية من التشغيل
                    import time
                    time.sleep(30)
                    self.fetch_from_url()
        except Exception as e:
            logger.error(f"ProxyManager Initial Load Error: {e}")

    def _load_from_file(self):
        """تحميل البروكسيات من الملف المحلي فقط"""
        try:
            if not Config.PROXIES_FILE.exists():
                return False
            
            with open(Config.PROXIES_FILE, 'r', encoding='utf-8') as f:
                raw_proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            new_proxies = []
            for p in raw_proxies:
                parts = p.split(':')
                if len(parts) == 4:
                    formatted = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                    new_proxies.append(formatted)
                elif p.startswith('http'):
                    new_proxies.append(p)
                else:
                    new_proxies.append(f"http://{p}")
            
            with self._lock:
                self.proxies = new_proxies
                if self.proxies:
                    logger.info(f"✅ ProxyManager: Loaded {len(self.proxies)} proxies from cache.")
            return True
        except Exception as e:
            logger.error(f"ProxyManager File Load Error: {e}")
            return False

    def fetch_from_url(self):
        """جلب قائمة البروكسيات من الرابط وحفظها محلياً"""
        import requests
        if not Config.PROXIES_URL or not Config.USE_PROXIES:
            return False
            
        try:
            logger.info("📡 ProxyManager: Fetching proxies from URL in background...")
            response = requests.get(Config.PROXIES_URL, timeout=20)
            if response.status_code == 200:
                content = response.text.strip()
                if content:
                    # حفظ في الملف للتخزين المؤقت
                    with open(Config.PROXIES_FILE, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    # إعادة التحميل من الملف المحفوظ
                    self._load_from_file()
                    logger.success("✅ ProxyManager: Proxies updated and cached from URL.")
                    return True
            else:
                logger.warning(f"⚠️ ProxyManager: URL fetch failed (Status: {response.status_code})")
        except Exception as e:
            logger.error(f"ProxyManager Fetch Error: {e}")
        return False

    def get_proxy(self, strategy='random'):
        """جلب بروكسي لاستخدامه في الطلب التالي"""
        if not Config.USE_PROXIES:
            return None
        
        with self._lock:
            if not self.proxies: 
                return None
            
            if strategy == 'round_robin':
                proxy = self.proxies[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.proxies)
                return proxy
            else:
                return random.choice(self.proxies)

    def reload(self):
        """إعادة تحميل قائمة البروكسيات (في الخلفية)"""
        import threading
        threading.Thread(target=self._initial_load, daemon=True).start()

# إنشاء نسخة وحيدة (Singleton)
proxy_manager = ProxyManager()
