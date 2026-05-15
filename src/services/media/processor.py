import time
import random
import yt_dlp
from src.core.config import Config
from src.core.utils import logger, detect_platform_from_url, check_ffmpeg_available

def get_ydl_opts_for_platform(url, quality_type='high', output_path=None, cookies_file=None):
    # إعدادات أساسية
    ydl_opts = {
        'outtmpl': str(output_path),
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'ignoreerrors': False,
        'socket_timeout': 30,
        'source_address': '0.0.0.0',
        'max_filesize': Config.MAX_FILE_SIZE,
        'merge_output_format': 'mp4',
    }

    if cookies_file:
        ydl_opts['cookiefile'] = str(cookies_file)

    platform = detect_platform_from_url(url)
    from src.core.proxy_manager import proxy_manager
    proxy = proxy_manager.get_proxy(platform=platform)
    if proxy:
        ydl_opts['proxy'] = proxy

    ffmpeg_available = check_ffmpeg_available()

    # Apply shared defaults
    ydl_opts['noplaylist'] = True
    if platform in ['instagram', 'tiktok']:
        ydl_opts['noplaylist'] = False # السماح بتحميل الألبومات
        
    if platform == 'instagram':
        ydl_opts['extractor_args'] = {
            'instagram': {
                'include_reels': True,
                'include_stories': True,
                'check_formats': True
            }
        }
        ydl_opts['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'

    # معالجة الجودات الرقمية (Dynamic Quality)
    if str(quality_type).isdigit():
        h = quality_type
        if ffmpeg_available:
            ydl_opts['format'] = f'bestvideo[height<={h}]+bestaudio/best[height<={h}][vcodec!=none][acodec!=none]/best[height<={h}]/best'
        else:
            ydl_opts['format'] = f'best[height<={h}]/best'
        return ydl_opts

    if quality_type == 'audio':
        ydl_opts['format'] = 'bestaudio/best'
        ydl_opts['postprocessors'] = [{
            'key': 'FFmpegExtractAudio',
            'preferredcodec': 'mp3',
            'preferredquality': '192',
        }]
        return ydl_opts

    if quality_type == 'mute':
        ydl_opts['format'] = 'bestvideo[ext=mp4]/bestvideo/best'
        return ydl_opts

    # Default format strategy
    if ffmpeg_available:
        default_video_format = 'bestvideo+bestaudio/best[vcodec!=none][acodec!=none]/best'
    else:
        default_video_format = 'best[vcodec!=none][acodec!=none]/best'

    if platform == 'instagram':
        ydl_opts['format'] = default_video_format if ffmpeg_available else 'best'
    elif platform == 'tiktok':
        ydl_opts['noplaylist'] = False
    elif platform == 'facebook':
        if quality_type == 'high':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        elif quality_type == 'medium':
            ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
        elif quality_type == 'low':
            ydl_opts['format'] = 'bestvideo[height<=360]+bestaudio/best[height<=360]/best'
        else:
            ydl_opts['format'] = 'best'
    elif platform == 'youtube':
        ydl_opts['referer'] = 'https://www.youtube.com/'
        ydl_opts['noplaylist'] = True
        ydl_opts['extract_flat'] = False
        ydl_opts['extractor_args'] = {
            'youtube': {
                'player_client': ['android', 'ios', 'web', 'mweb'],
                'skip': ['dash', 'hls']
            }
        }
        
        # Check if curl-cffi is available for impersonation
        # We try to use it but we'll fallback in retries if it fails
        try:
            import curl_cffi
            ydl_opts['impersonate'] = 'chrome'
        except ImportError:
            pass
        
        if 'shorts' in url.lower():
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        elif quality_type == 'high':
             ydl_opts['format'] = 'bestvideo+bestaudio/best'
        elif quality_type == 'medium':
             ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
        elif quality_type == 'low':
             ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480]/best'
        else:
             ydl_opts['format'] = 'best'
             
        ydl_opts['quiet'] = False
        ydl_opts['no_warnings'] = False
    else:
        if quality_type == 'high':
            ydl_opts['format'] = default_video_format
        elif quality_type == 'medium':
            ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480][vcodec!=none][acodec!=none]/bestvideo+bestaudio/best'
        elif quality_type == 'low':
            ydl_opts['format'] = 'bestvideo[height<=360]+bestaudio/best[height<=360][vcodec!=none][acodec!=none]/bestvideo+bestaudio/best'
        ydl_opts['noplaylist'] = True
    
    return ydl_opts

def youtube_safe_download(url, ydl_opts, max_retries=3):
    from src.core.proxy_manager import proxy_manager
    
    ydl_opts['sleep_interval'] = random.randint(2, 5)
    ydl_opts['max_sleep_interval'] = random.randint(6, 10)
    
    for i in range(max_retries):
        try:
            if i > 0:
                old_proxy = ydl_opts.get('proxy')
                if old_proxy:
                    proxy_manager.report_failure(old_proxy, platform='youtube')
                
                new_proxy = proxy_manager.get_proxy(platform='youtube')
                if new_proxy:
                    logger.info(f"🔄 YouTube Retry {i+1} with new proxy: {new_proxy}")
                    ydl_opts['proxy'] = new_proxy

            if 'extractor_args' not in ydl_opts: ydl_opts['extractor_args'] = {'youtube': {}}
            
            if i == 0:
                ydl_opts['extractor_args']['youtube']['player_client'] = ['android', 'web']
                if 'impersonate' in ydl_opts: del ydl_opts['impersonate']
            elif i == 1:
                ydl_opts['extractor_args']['youtube']['player_client'] = ['ios', 'mweb', 'android']
                ydl_opts['referer'] = 'https://www.google.com/'
                if 'cookiefile' in ydl_opts: 
                    logger.info("🔄 Retrying YouTube WITHOUT cookies...")
                    del ydl_opts['cookiefile'] # Try without cookies if they might be flagged
            elif i == 2:
                ydl_opts['format'] = 'best'
                ydl_opts['extractor_args']['youtube']['player_client'] = ['tv', 'android']
                try:
                    import curl_cffi
                    ydl_opts['impersonate'] = 'chrome'
                except ImportError: pass

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info
        except Exception as e:
            logger.warning(f"YouTube Try {i+1} failed: {e}")
            if i < max_retries - 1:
                time.sleep(i * 5 + 5)
            else:
                raise e
    raise Exception("Youtube download failed after retries")

def enhanced_download_with_fallback(ydl_opts, url, max_retries=3):
    from src.core.proxy_manager import proxy_manager
    from src.core.utils import detect_platform_from_url
    platform = detect_platform_from_url(url)
    
    for i in range(max_retries):
        try:
            if i > 0:
                new_proxy = proxy_manager.get_proxy(platform=platform)
                if new_proxy:
                    logger.info(f"🔄 Retrying with new proxy: {new_proxy}")
                    ydl_opts['proxy'] = new_proxy
                if i == 2:
                    ydl_opts['format'] = 'best[vcodec!=none][acodec!=none]/best'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info
        except Exception as e:
            logger.warning(f"Download Try {i+1} failed: {e}")
            current_proxy = ydl_opts.get('proxy')
            if current_proxy:
                proxy_manager.report_failure(current_proxy, platform=platform)
                
            if i == 0 and 'cookiefile' in ydl_opts:
                del ydl_opts['cookiefile']
            
            # For Instagram/YouTube, if it keeps failing, try WITHOUT proxy early
            if i == 0 and platform in ['instagram', 'youtube']:
                if 'proxy' in ydl_opts:
                    logger.info(f"🔄 Try {i+1} WITHOUT proxy for {platform}")
                    del ydl_opts['proxy']

            time.sleep(2)
            if i == max_retries - 1:
                raise e
    return None
