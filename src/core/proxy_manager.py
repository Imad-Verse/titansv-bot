import random
import threading
import time
import requests
from datetime import datetime
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
        if self._initialized:
            return
        
        self.proxies = []  # List of dicts: {'url': str, 'healthy': bool, 'failures': int, 'platform_blocks': set()}
        self.current_index = 0
        self.last_fetch_time = None
        self._initialized = True
        
        # Start background threads
        threading.Thread(target=self._initial_load, daemon=True).start()
        threading.Thread(target=self._health_check_loop, daemon=True).start()
        threading.Thread(target=self._auto_refresh_loop, daemon=True).start()

    def _initial_load(self):
        """Initial load of proxies from file and URL."""
        try:
            # 1. Load from local cache first
            self._load_from_file()
            
            # 2. Fetch from URL if enabled
            if Config.USE_PROXIES and Config.PROXIES_URL:
                if not self.proxies:
                    self.fetch_from_url()
                else:
                    # Delayed refresh to allow bot to start quickly
                    time.sleep(10)
                    self.fetch_from_url()
        except Exception as e:
            logger.error(f"ProxyManager Initial Load Error: {e}")

    def _parse_proxy_string(self, p):
        """Parses various proxy string formats into a standard http/socks5 URL."""
        p = p.strip()
        if not p or p.startswith('#'):
            return None
        
        # Already formatted
        if p.startswith(('http', 'socks')):
            return p
            
        parts = p.split(':')
        # Format: ip:port:user:pass
        if len(parts) == 4:
            return f"http://{parts[2]}:{parts[3]}@{parts[0]}:{parts[1]}"
        # Format: user:pass@ip:port
        elif '@' in p:
            return f"http://{p}"
        # Format: ip:port
        elif len(parts) == 2:
            return f"http://{p}"
            
        return f"http://{p}"

    def _load_from_file(self):
        """Loads proxies from local file."""
        try:
            if not Config.PROXIES_FILE.exists():
                return False
            
            with open(Config.PROXIES_FILE, 'r', encoding='utf-8') as f:
                raw_lines = [line.strip() for line in f if line.strip() and not line.startswith('#')]
            
            new_proxies = []
            for line in raw_lines:
                url = self._parse_proxy_string(line)
                if url:
                    # Preserve existing state if proxy is already in list
                    existing = next((p for p in self.proxies if p['url'] == url), None)
                    if existing:
                        new_proxies.append(existing)
                    else:
                        new_proxies.append({
                            'url': url,
                            'healthy': True,
                            'failures': 0,
                            'platform_blocks': set(),
                            'last_checked': None
                        })
            
            with self._lock:
                self.proxies = new_proxies
                if self.proxies:
                    logger.info(f"✅ ProxyManager: Loaded {len(self.proxies)} proxies from file.")
            return True
        except Exception as e:
            logger.error(f"ProxyManager File Load Error: {e}")
            return False

    def fetch_from_url(self):
        """Fetches proxy list from URL and caches locally."""
        if not Config.PROXIES_URL or not Config.USE_PROXIES:
            return False
            
        try:
            logger.info("📡 ProxyManager: Fetching proxies from URL...")
            response = requests.get(Config.PROXIES_URL, timeout=30)
            if response.status_code == 200:
                content = response.text.strip()
                if content:
                    with open(Config.PROXIES_FILE, 'w', encoding='utf-8') as f:
                        f.write(content)
                    
                    self._load_from_file()
                    self.last_fetch_time = datetime.now()
                    logger.success("✅ ProxyManager: Proxies updated from URL.")
                    return True
            else:
                logger.warning(f"⚠️ ProxyManager: URL fetch failed (Status: {response.status_code})")
        except Exception as e:
            logger.error(f"ProxyManager Fetch Error: {e}")
        return False

    def _health_check_loop(self):
        """Periodic background health check for proxies."""
        while True:
            if not Config.USE_PROXIES or not self.proxies:
                time.sleep(60)
                continue
                
            # Check a small batch of proxies every minute
            with self._lock:
                to_check = sorted(self.proxies, key=lambda x: x['last_checked'] or datetime.min)[:5]
            
            for p in to_check:
                self._check_proxy_health(p)
                
            time.sleep(30)

    def _check_proxy_health(self, proxy_obj):
        """Pings a reliable server through the proxy to verify connectivity."""
        test_url = "http://www.google.com"
        try:
            proxy_dict = {"http": proxy_obj['url'], "https": proxy_obj['url']}
            start = time.time()
            resp = requests.get(test_url, proxies=proxy_dict, timeout=10)
            latency = time.time() - start
            
            proxy_obj['healthy'] = resp.status_code == 200
            proxy_obj['last_checked'] = datetime.now()
            if not proxy_obj['healthy']:
                proxy_obj['failures'] += 1
            else:
                # Reset failures on success if it was unhealthy
                if proxy_obj['failures'] > 0:
                    proxy_obj['failures'] = 0
                    
        except Exception:
            proxy_obj['healthy'] = False
            proxy_obj['failures'] += 1
            proxy_obj['last_checked'] = datetime.now()

    def _auto_refresh_loop(self):
        """Automatically refreshes proxies from URL every hour."""
        while True:
            time.sleep(3600) # Every 1 hour
            if Config.USE_PROXIES and Config.PROXIES_URL:
                self.fetch_from_url()

    def report_failure(self, proxy_url, platform=None):
        """Reports a failure for a specific proxy, optionally for a specific platform."""
        with self._lock:
            proxy = next((p for p in self.proxies if p['url'] == proxy_url), None)
            if proxy:
                proxy['failures'] += 1
                if platform:
                    proxy['platform_blocks'].add(platform)
                
                if proxy['failures'] > 5:
                    proxy['healthy'] = False
                
                logger.warning(f"🚩 ProxyManager: Reported failure for {proxy_url} (Platform: {platform})")

    def get_proxy(self, platform=None, strategy='random'):
        """Gets a healthy proxy, optionally filtered by platform compatibility."""
        if not Config.USE_PROXIES:
            return None
        
        with self._lock:
            # Filter healthy proxies that aren't blocked for this platform
            candidates = [
                p for p in self.proxies 
                if p['healthy'] and (not platform or platform not in p['platform_blocks'])
            ]
            
            # Fallback to any healthy proxy if all are blocked for this platform
            if not candidates and platform:
                candidates = [p for p in self.proxies if p['healthy']]
                
            if not candidates:
                # Last resort: try any proxy but prefer those with fewer failures
                candidates = sorted(self.proxies, key=lambda x: x['failures'])[:10]
            
            if not candidates:
                return None
            
            if strategy == 'round_robin':
                self.current_index = (self.current_index + 1) % len(candidates)
                proxy = candidates[self.current_index]
            else:
                proxy = random.choice(candidates)
                
            return proxy['url']

    def reload(self):
        """Manually trigger a reload."""
        self._initial_load()

# Singleton instance
proxy_manager = ProxyManager()
