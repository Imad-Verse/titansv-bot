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
        self._load_proxies()
        self._initialized = True

    def _load_proxies(self):
        try:
            # إذا كان هناك رابط، نحاول التحديث منه أولاً
            if Config.PROXIES_URL and Config.USE_PROXIES:
                self.fetch_from_url()

            if not Config.PROXIES_FILE.exists():
                Config.PROXIES_FILE.parent.mkdir(parents=True, exist_ok=True)
                Config.PROXIES_FILE.touch()
                return
            
            # تصفية السطور الفارغة والتعليقات
            raw_proxies = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            self.proxies = []
            for p in raw_proxies:
                # معالجة صيغة Webshare: IP:PORT:USER:PASS
                parts = p.split(':')
                if len(parts) == 4:
                    # تحويل إلى: http://user:pass@ip:port
                    formatted = f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
                    self.proxies.append(formatted)
                elif p.startswith('http'):
                    self.proxies.append(p)
                else:
                    self.proxies.append(f"http://{p}")
            
            if self.proxies:
                logger.info(f"✅ ProxyManager: Loaded {len(self.proxies)} proxies.")
            else:
                logger.debug("ProxyManager: No proxies found in proxies.txt.")
        except Exception as e:
            logger.error(f"ProxyManager Load Error: {e}")

    def fetch_from_url(self):
        """جلب قائمة البروكسيات من الرابط وحفظها محلياً"""
        import requests
        try:
            logger.info("📡 ProxyManager: Fetching proxies from URL...")
            response = requests.get(Config.PROXIES_URL, timeout=15)
            if response.status_code == 200:
                content = response.text.strip()
                if content:
                    with open(Config.PROXIES_FILE, 'w', encoding='utf-8') as f:
                        f.write(content)
                    logger.success("✅ ProxyManager: Proxies updated successfully from URL.")
                    return True
            else:
                logger.warning(f"⚠️ ProxyManager: Failed to fetch proxies (Status: {response.status_code})")
        except Exception as e:
            logger.error(f"ProxyManager Fetch Error: {e}")
        return False

    def get_proxy(self, strategy='random'):
        """جلب بروكسي لاستخدامه في الطلب التالي"""
        if not self.proxies or not Config.USE_PROXIES:
            return None
        
        with self._lock:
            if not self.proxies: return None
            
            if strategy == 'round_robin':
                proxy = self.proxies[self.current_index]
                self.current_index = (self.current_index + 1) % len(self.proxies)
                return proxy
            else:
                return random.choice(self.proxies)

    def reload(self):
        """إعادة تحميل قائمة البروكسيات من الملف"""
        with self._lock:
            self._load_proxies()

# إنشاء نسخة وحيدة (Singleton)
proxy_manager = ProxyManager()
