import os
import time
import threading
import subprocess
import yt_dlp
import requests
from urllib.parse import urlparse
from telebot import types

from src.core.config import Config
from src.core.loader import bot, BotState
from src.utils.ui import get_error_markup
from src.core.utils import (
    logger, format_seconds, delayed_delete, detect_platform_from_url,
    get_cookies_file, sanitize_filename, generate_sid, check_ffmpeg_available,
    get_bot_username
)
from src.core.database import (
    log_download, update_download_stats, get_user_details, 
    get_url_by_sid, get_cached_media, save_to_cache
)
from src.services.translation import translation_system

# Import refactored modules
from src.services.media.uploader import (
    ProgressFileReader, upload_progress_callback, update_progress_message,
    _delete_progress_message, create_progress_message
)
from src.services.media.caption import (
    build_video_caption, extract_title_and_description
)
from src.services.media.processor import (
    get_ydl_opts_for_platform, youtube_safe_download, enhanced_download_with_fallback
)
from src.services.media.utils import (
    find_downloaded_file, find_all_downloaded_files, mute_video_file,
    generate_video_thumbnail, download_thumbnail, split_large_file
)

# Constants
IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}


def _start_progress(uid, message, sid, text):
    cancel_event = threading.Event()
    BotState.user_requests[uid] = {'sid': sid, 'cancel_event': cancel_event}
    progress_markup = cancel_markup(sid, uid)
    progress_msg = create_progress_message(message.chat.id, text, 5, markup=progress_markup)
    return cancel_event, progress_msg, progress_markup

def _contains_any(text, patterns):
    return any(pattern in text for pattern in patterns)

def _build_file_too_large_message(uid, size_mb=0):
    if size_mb and size_mb > 0:
        return translation_system.get(
            uid, 'file_too_large',
            size=size_mb, limit_mb=Config.TELEGRAM_UPLOAD_LIMIT_MB,
        )
    return translation_system.get(uid, 'file_too_large_unknown', limit_mb=Config.TELEGRAM_UPLOAD_LIMIT_MB)

def _exceeds_telegram_upload_limit(size_bytes):
    return bool(size_bytes and Config.TELEGRAM_UPLOAD_LIMIT > 0 and size_bytes > Config.TELEGRAM_UPLOAD_LIMIT)

_QUALITY_CASCADE = {'high': 'medium', 'medium': 'low'}

def _get_next_lower_quality(quality_type):
    """الحصول على المستوى الأقل التالي في سلسلة الجودات (high→medium→low)"""
    return _QUALITY_CASCADE.get(quality_type)

def _classify_download_error(uid, error_text, size_mb=0):
    er_msg = (error_text or "").lower()

    if _contains_any(er_msg, ["request entity too large", "error code: 413", "too large", "max_filesize", "file is too big"]):
        return "file_too_large", _build_file_too_large_message(uid, size_mb)

    if _contains_any(er_msg, ["there is no video in this post", "no video in this post"]):
        return "no_video_in_post", translation_system.get(uid, 'no_video_in_post')

    if _contains_any(er_msg, ["your ip address is blocked", "ip address is blocked"]):
        return "service_blocked", translation_system.get(uid, 'service_blocked')

    if _contains_any(er_msg, ["unsupported url", "does not have a"]):
        return "unsupported_url", translation_system.get(uid, 'unsupported_url')

    if _contains_any(er_msg, ["private", "sign in", "log in", "login", "registered users", "follow this account", "authentication", "cookies", "you need to log in", "empty media response"]):
        return "private_or_login", translation_system.get(uid, 'private_or_login')

    if _contains_any(er_msg, ["failed to resolve", "name resolution", "connection aborted", "connection reset", "timed out", "timeout", "max retries exceeded", "read timed out", "connect timeout"]):
        return "network_error", translation_system.get(uid, 'weak_connection')

    if _contains_any(er_msg, ["cannot parse data", "unable to extract data", "no video formats found", "file empty or not found", "redirect loop detected"]):
        return "temporary_source_issue", translation_system.get(uid, 'temporary_source_issue')

    if _contains_any(er_msg, ["this video is not available", "video unavailable", "no longer available", "account associated with this video has been terminated", "removed", "http error 404"]):
        return "unavailable", translation_system.get(uid, 'video_unavailable')

    return "download_error", translation_system.get(uid, 'download_error')

def _build_progress_hook(cancel_event, progress_msg, chat_id, text, progress_markup):
    last_progress = {'value': 0}
    def _hook(d):
        if cancel_event.is_set():
            raise Exception("cancelled_by_user")
        if d['status'] == 'downloading':
            try:
                total = d.get('total_bytes') or d.get('total_bytes_estimate')
                if total and total > 0:
                    percent = (d.get('downloaded_bytes', 0) / total) * 100
                    if int(percent) - last_progress['value'] >= 10 or percent >= 98:
                        if update_progress_message(progress_msg.message_id, chat_id, text, int(percent), markup=progress_markup):
                            last_progress['value'] = int(percent)
            except: pass
        elif d['status'] == 'finished':
            update_progress_message(progress_msg.message_id, chat_id, text, 100, markup=progress_markup)
    return _hook

def precheck_media_info(url, ydl_opts):
    try:
        opts = dict(ydl_opts)
        opts.pop('progress_hooks', None)
        opts['skip_download'] = True
        with yt_dlp.YoutubeDL(opts) as ydl:
            info = ydl.extract_info(url, download=False)
        size = info.get('filesize') or info.get('filesize_approx') or 0
        return info, size
    except Exception as e:
        logger.warning(f"Precheck error: {e}")
        return None, 0

def expand_short_url(url):
    try:
        session = requests.Session()
        headers = {'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36', 'Accept': '*/*'}
        resp = session.head(url, allow_redirects=True, timeout=10, headers=headers)
        if resp.url: return resp.url
        if resp.status_code in (403, 405):
            resp = session.get(url, allow_redirects=True, timeout=10, headers=headers)
            if resp.url: return resp.url
    except Exception: pass
    return url

def prepare_tiktok_urls(url):
    parsed = urlparse(url)
    if parsed.netloc in ['vm.tiktok.com', 'vt.tiktok.com', 't.tiktok.com', 'm.tiktok.com']:
        url = expand_short_url(url)
    normalized = url
    if '/photo/' in url: normalized = url.replace('/photo/', '/video/')
    return url, normalized

def video_markup(sid, uid):
    markup = types.InlineKeyboardMarkup()
    markup.row(
        types.InlineKeyboardButton(translation_system.get(uid, "extract_audio"), callback_data=f"audio_{sid}"),
        types.InlineKeyboardButton(translation_system.get(uid, "mute_video"), callback_data=f"mute_{sid}")
    )
    markup.row(
        types.InlineKeyboardButton(translation_system.get(uid, "share_bot"), url=f"https://t.me/share/url?url=https://t.me/{get_bot_username()}"),
        types.InlineKeyboardButton(translation_system.get(uid, "contact_dev"), url="https://t.me/abulharith_imad")
    )
    return markup

def cancel_markup(sid, uid):
    markup = types.InlineKeyboardMarkup()
    markup.add(types.InlineKeyboardButton(translation_system.get(uid, "cancel_download"), callback_data=f"cancel_dl|{sid}"))
    return markup

def send_download_report(user_id, url, size, title, platform, sid):
    try:
        user_info = get_user_details(user_id)
        username = "No Username"
        if user_info and user_info['username']:
            u = user_info['username']
            username = f"@{u}" if not u.startswith('@') else u
        total_dls = user_info['download_count'] if user_info else 0
        short_title = title[:40] + "..." if len(title) > 40 else title
        msg = (f"📥 <b>تحميل جديد:</b>\n\n"
               f"👤 <b>من:</b> {user_id} | {username}\n"
               f"🔢 <b>عدد التحميلات:</b> {total_dls}\n"
               f"📱 <b>منصة:</b> {platform}\n"
               f"💾 <b>حجم:</b> {size:.2f} MB\n"
               f"🎞 <b>عنوان:</b> {short_title}\n"
               f"🔗 <b>الرابط:</b> <a href='{url}'>اضغط هنا لفتحه</a>")
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📋 نسخ الرابط", callback_data=f"copy_link|{sid}"))
        bot.send_message(Config.ADMIN_ID, msg, parse_mode="HTML", reply_markup=markup)
    except Exception as e: logger.error(f"Report error: {e}")

def send_failure_report(user_id, url, platform, reason, sid="", size_mb=0, title=""):
    try:
        user_info = get_user_details(user_id)
        username = "No Username"
        if user_info and user_info['username']:
            u = user_info['username']
            username = f"@{u}" if not u.startswith('@') else u
        total_dls = user_info['download_count'] if user_info else 0
        reasons = {"invalid_link": "رابط غير صالح", "unsupported_platform": "منصة غير مدعومة", "unsupported_url": "رابط غير مدعوم", "ffmpeg_missing": "FFmpeg غير متوفر", "file_too_large": "الملف كبير جداً", "processing_error": "خطأ أثناء المعالجة", "photo_not_supported": "تحميل الصور غير مدعوم حالياً", "no_video_in_post": "المنشور لا يحتوي على فيديو", "private_or_login": "الفيديو خاص/يتطلب تسجيل دخول", "unavailable": "الفيديو غير متاح أو محذوف", "network_error": "مشكلة اتصال مؤقتة", "temporary_source_issue": "تعذر قراءة الملف من المنصة", "service_blocked": "المنصة رفضت الطلب مؤقتاً", "download_error": "خطأ تحميل عام"}
        reason_text = reasons.get(reason, reason or "غير معروف")
        short_title = title[:40] + "..." if title and len(title) > 40 else (title or "غير متوفر")
        size_text = f"{size_mb:.2f} MB" if size_mb else "غير معروف"
        msg = (f"❌ <b>فشل تحميل:</b>\n\n"
               f"👤 <b>من:</b> {user_id} | {username}\n"
               f"🔢 <b>عدد التحميلات:</b> {total_dls}\n"
               f"📱 <b>منصة:</b> {platform}\n"
               f"💾 <b>حجم:</b> {size_text}\n"
               f"🎞 <b>عنوان:</b> {short_title}\n"
               f"⚠️ <b>السبب:</b> {reason_text}\n"
               f"🔗 <b>الرابط:</b> <a href='{url}'>اضغط هنا لفتحه</a>")
        markup = None
        if sid:
            markup = types.InlineKeyboardMarkup()
            markup.add(types.InlineKeyboardButton("📋 نسخ الرابط", callback_data=f"copy_link|{sid}"))
        bot.send_message(Config.ADMIN_ID, msg, parse_mode="HTML", reply_markup=markup)
    except Exception as e: logger.error(f"Failure report error: {e}")

def maybe_report_failure(user_id, url, platform, reason, sid="", size_mb=0, title=""):
    if BotState.report_logs and user_id != Config.ADMIN_ID:
        send_failure_report(user_id, url, platform, reason, sid=sid, size_mb=size_mb, title=title)

def extract_media_info(url, cookies_file=None):
    from src.core.proxy_manager import proxy_manager
    platform = detect_platform_from_url(url)
    info = None
    
    # Try up to 3 times with different proxy/cookie/extractor configurations
    for attempt in range(3):
        proxy = proxy_manager.get_proxy(platform=platform) if attempt < 2 else None
        
        ydl_opts = {
            'quiet': True,
            'no_warnings': True,
            'nocheckcertificate': True,
            'skip_download': True,
            'ignoreerrors': True,
            'socket_timeout': 15,
        }
        
        if proxy:
            ydl_opts['proxy'] = proxy
            
        # Failover configuration adjustments
        if attempt == 0:
            if cookies_file:
                ydl_opts['cookiefile'] = str(cookies_file)
        elif attempt == 1:
            ydl_opts.pop('proxy', None)  # Fallback to local IP
            if cookies_file:
                ydl_opts['cookiefile'] = str(cookies_file)
        elif attempt == 2:
            ydl_opts.pop('proxy', None)
            if cookies_file and platform != 'instagram':
                # Try without cookies as a last resort
                ydl_opts.pop('cookiefile', None)
            elif cookies_file:
                ydl_opts['cookiefile'] = str(cookies_file)

        # Platform specific tweaks
        if platform == 'instagram':
            ydl_opts['extractor_args'] = {
                'instagram': {
                    'include_reels': True,
                    'include_stories': True,
                    'check_formats': True
                }
            }
            ydl_opts['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/123.0.0.0 Safari/537.36'

        try:
            logger.info(f"🔍 Extracting info for {url} (Attempt {attempt+1}, Platform: {platform}, Proxy: {proxy is not None})")
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=False)
                if info:
                    break
        except Exception as e:
            logger.warning(f"⚠️ Info extraction attempt {attempt+1} failed: {e}")
            if proxy:
                proxy_manager.report_failure(proxy, platform=platform)
            if attempt == 2:
                return None
    else:
        return None

    try:
        formats = info.get('formats', [])
        duration = info.get('duration') or 0
        
        # 1. Find the best audio format size to estimate merged adaptive format size
        best_audio_size = 0
        for f in formats:
            if f.get('vcodec') == 'none' and f.get('acodec') != 'none':
                size = f.get('filesize') or f.get('filesize_approx') or 0
                if not size and f.get('tbr') and duration > 0:
                    size = (f['tbr'] * 1000 / 8) * duration
                if size > best_audio_size:
                    best_audio_size = size
        
        # 2. Extract, calculate size and map resolutions
        resolutions_map = {}
        standards = [2160, 1440, 1080, 720, 480, 360, 240, 144]
        
        def get_format_resolution(fmt):
            width = fmt.get('width')
            height = fmt.get('height')
            if width and height:
                return min(width, height)
            return height or 0
            
        def get_nearest_standard(h):
            for std in standards:
                if abs(h - std) <= 30:
                    return std
            for std in standards:
                if h >= std:
                    return std
            return 144

        for f in formats:
            if f.get('vcodec') == 'none':
                continue
                
            res = get_format_resolution(f)
            if res and res >= 144:
                size = f.get('filesize') or f.get('filesize_approx') or 0
                if not size and f.get('tbr') and duration > 0:
                    size = (f['tbr'] * 1000 / 8) * duration
                    
                # Add audio size if it's a video-only adaptive format
                if f.get('acodec') == 'none':
                    size += best_audio_size
                    
                if res not in resolutions_map or size > resolutions_map[res]:
                    resolutions_map[res] = size

        # 3. Standardize resolutions and remove duplicates
        seen_standards = {}
        for res in sorted(resolutions_map.keys(), reverse=True):
            std_res = get_nearest_standard(res)
            size_mb = resolutions_map[res] / (1024 * 1024)
            
            if std_res not in seen_standards:
                seen_standards[std_res] = {
                    'height': std_res,
                    'size_mb': size_mb
                }
            else:
                if size_mb > seen_standards[std_res]['size_mb']:
                    seen_standards[std_res]['size_mb'] = size_mb

        # 4. Prepare final sorted list of resolution dictionaries
        sorted_resolutions = [seen_standards[k] for k in sorted(seen_standards.keys(), reverse=True)]
        
        return {
            'title': info.get('title'),
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'resolutions': sorted_resolutions,
            'platform': platform,
            'info': info
        }
    except Exception as ex:
        logger.error(f"Error processing formats: {ex}")
        return {
            'title': info.get('title'),
            'duration': info.get('duration'),
            'thumbnail': info.get('thumbnail'),
            'resolutions': [],
            'platform': platform,
            'info': info
        }

def process_download(message, quality_type, url=None):
    uid = message.from_user.id
    time.sleep(0.5)
    progress_msg = None
    platform = 'other' # Initialize to avoid UnboundLocalError
    try:
        sid = sanitize_filename(generate_sid())
        source_url = url if url else message.text
        download_url = source_url
        platform = detect_platform_from_url(source_url)
        if platform == 'tiktok':
            source_url, download_url = prepare_tiktok_urls(source_url)
        
        cached_media = get_cached_media(source_url, quality_type)
        if cached_media:
            try:
                caption = build_video_caption(uid, cached_media['title'], cached_media['description'], cached_media['platform'], cached_media['duration'], f"{cached_media['size_mb']:.2f}", Config.BOT_SIG)
                if quality_type == 'audio':
                    bot.send_audio(message.chat.id, cached_media['file_id'], caption=caption, parse_mode="HTML")
                else:
                    if cached_media['size_mb'] > Config.DOCUMENT_THRESHOLD_MB:
                        bot.send_document(message.chat.id, cached_media['file_id'], caption=caption, parse_mode="HTML", reply_markup=video_markup(sid, uid))
                    else:
                        bot.send_video(message.chat.id, cached_media['file_id'], caption=caption, parse_mode="HTML", reply_markup=video_markup(sid, uid), supports_streaming=True)
                log_download(uid, source_url, "cached_success", size_mb=cached_media['size_mb'], platform=platform, title=cached_media['title'], sid=sid)
                update_download_stats()
                return
            except Exception: pass
        
        video_title = ""
        file_size_mb = 0
        if platform not in Config.ALLOWED_PLATFORMS:
            error_reason = "invalid_link" if platform == 'other' else "unsupported_platform"
            msg = translation_system.get(uid, error_reason, platforms=", ".join([p.title() for p in Config.ALLOWED_PLATFORMS]))
            bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=get_error_markup(uid))
            log_download(uid, source_url, "failed", platform=platform, sid=sid, error_reason=error_reason)
            if error_reason != "invalid_link": maybe_report_failure(uid, source_url, platform, error_reason, sid=sid)
            return

        if quality_type in ['audio', 'mute'] and not check_ffmpeg_available():
            bot.send_message(message.chat.id, translation_system.get(uid, 'ffmpeg_missing'), parse_mode="HTML", reply_markup=get_error_markup(uid))
            log_download(uid, source_url, "failed", platform=platform, sid=sid, error_reason="ffmpeg_missing")
            maybe_report_failure(uid, source_url, platform, "ffmpeg_missing", sid=sid)
            return

        download_started_text = translation_system.get(uid, 'download_started')
        cancel_event, progress_msg, progress_markup = _start_progress(uid, message, sid, download_started_text)
        target_dir = str(Config.ADMIN_DOWNLOADS if uid == Config.ADMIN_ID else Config.USERS_DOWNLOADS)
        output_template = os.path.join(target_dir, f"video_{sid}_%(autonumber)03d.%(ext)s" if platform in ['instagram', 'tiktok'] else f"video_{sid}.%(ext)s")
        
        cookies_file = get_cookies_file(source_url)
        if cookies_file: cookies_file = str(cookies_file)
        
        # Direct URL Upload Strategy
        if platform in ['tiktok', 'instagram'] and quality_type not in ['audio', 'mute']:
            try:
                direct_opts = get_ydl_opts_for_platform(source_url, quality_type, cookies_file=cookies_file)
                direct_opts['skip_download'] = True
                with yt_dlp.YoutubeDL(direct_opts) as ydl:
                    info = ydl.extract_info(source_url, download=False)
                    direct_url, size = info.get('url'), info.get('filesize') or info.get('filesize_approx') or 0
                    if direct_url and 0 < size < (20 * 1024 * 1024):
                        update_progress_message(progress_msg.message_id, message.chat.id, translation_system.get(uid, 'upload_started'), 50)
                        sent_msg = bot.send_video(message.chat.id, direct_url, caption=build_video_caption(uid, info.get('title', ''), "", platform, format_seconds(info.get('duration', 0)), f"{size/(1024*1024):.2f}", Config.BOT_SIG), parse_mode="HTML")
                        if sent_msg:
                            save_to_cache(source_url, quality_type, sent_msg.video.file_id, title=info.get('title', ''), platform=platform, size_mb=size/(1024*1024))
                            log_download(uid, source_url, "url_upload_success", size_mb=size/(1024*1024), platform=platform, title=info.get('title', ''), sid=sid)
                            _delete_progress_message(message.chat.id, progress_msg)
                            return
            except Exception: pass
        
        download_progress_hook = _build_progress_hook(cancel_event, progress_msg, message.chat.id, download_started_text, progress_markup)
        ydl_opts = get_ydl_opts_for_platform(source_url, quality_type, output_template, cookies_file)
        ydl_opts['progress_hooks'] = [download_progress_hook]
        
        _pre_info, pre_size = precheck_media_info(source_url, ydl_opts)
        while _exceeds_telegram_upload_limit(pre_size):
            next_q = _get_next_lower_quality(quality_type)
            if next_q:
                quality_type = next_q
                downgraded_text = translation_system.get(uid, 'downgraded_due_to_size')
                update_progress_message(progress_msg.message_id, message.chat.id, downgraded_text, 10)
                
                ydl_opts = get_ydl_opts_for_platform(source_url, quality_type, output_template, cookies_file)
                ydl_opts['progress_hooks'] = [download_progress_hook]
                _pre_info, pre_size = precheck_media_info(source_url, ydl_opts)
            else:
                size_mb = pre_size / (1024 * 1024)
                bot.edit_message_text(_build_file_too_large_message(uid, size_mb), message.chat.id, progress_msg.message_id, parse_mode="HTML", reply_markup=get_error_markup(uid))
                log_download(uid, source_url, "failed", platform=platform, sid=sid, size_mb=size_mb, error_reason="file_too_large")
                maybe_report_failure(uid, source_url, platform, "file_too_large", sid=sid, size_mb=size_mb)
                return

        if cancel_event.is_set(): raise Exception("cancelled_by_user")
        
        if _pre_info is None and platform == 'tiktok' and download_url != source_url:
            ydl_opts = get_ydl_opts_for_platform(download_url, quality_type, output_template, cookies_file)
            ydl_opts['progress_hooks'] = [download_progress_hook]
            _pre_info, pre_size = precheck_media_info(download_url, ydl_opts)
            while _exceeds_telegram_upload_limit(pre_size):
                next_q = _get_next_lower_quality(quality_type)
                if next_q:
                    quality_type = next_q
                    downgraded_text = translation_system.get(uid, 'downgraded_due_to_size')
                    update_progress_message(progress_msg.message_id, message.chat.id, downgraded_text, 10)
                    
                    ydl_opts = get_ydl_opts_for_platform(download_url, quality_type, output_template, cookies_file)
                    ydl_opts['progress_hooks'] = [download_progress_hook]
                    _pre_info, pre_size = precheck_media_info(download_url, ydl_opts)
                else:
                    size_mb = pre_size / (1024 * 1024)
                    bot.edit_message_text(_build_file_too_large_message(uid, size_mb), message.chat.id, progress_msg.message_id, parse_mode="HTML", reply_markup=get_error_markup(uid))
                    log_download(uid, source_url, "failed", platform=platform, sid=sid, size_mb=size_mb, error_reason="file_too_large")
                    maybe_report_failure(uid, source_url, platform, "file_too_large", sid=sid, size_mb=size_mb)
                    return

        info = youtube_safe_download(download_url, ydl_opts, max_retries=3) if platform == 'youtube' else enhanced_download_with_fallback(ydl_opts, download_url, max_retries=3)
        downloaded_files = find_all_downloaded_files(target_dir, sid)
        if not downloaded_files: raise Exception("No files downloaded")
            
        if len(downloaded_files) > 1:
            video_title, video_description = extract_title_and_description(info, platform)
            total_size_mb = sum(os.path.getsize(f) for f in downloaded_files) / (1024 * 1024)
            if total_size_mb * 1024 * 1024 > Config.MAX_FILE_SIZE:
                bot.edit_message_text(_build_file_too_large_message(uid, total_size_mb), message.chat.id, progress_msg.message_id, parse_mode="HTML", reply_markup=get_error_markup(uid))
                for f in downloaded_files: delayed_delete(f)
                return
            
            caption = build_video_caption(uid, video_title, video_description, platform, format_seconds(info.get('duration', 0)), f"{total_size_mb:.2f}", Config.BOT_SIG)
            update_progress_message(progress_msg.message_id, message.chat.id, translation_system.get(uid, 'upload_started'), 0)
            
            for i in range(0, len(downloaded_files), 10):
                chunk_files = downloaded_files[i:i+10]
                media_group, opened_files = [], []
                try:
                    for j, file_path in enumerate(chunk_files):
                        f = open(file_path, 'rb')
                        opened_files.append(f)
                        is_photo = os.path.splitext(file_path)[1].lower().lstrip('.') in IMAGE_EXTS
                        current_caption = caption if (i == 0 and j == 0) else None
                        media_group.append(types.InputMediaPhoto(f, caption=current_caption, parse_mode="HTML") if is_photo else types.InputMediaVideo(f, caption=current_caption, parse_mode="HTML", supports_streaming=True))
                    for retry in range(3):
                        try:
                            for f in opened_files: f.seek(0)
                            bot.send_media_group(message.chat.id, media_group, timeout=600)
                            break
                        except Exception as e:
                            if retry == 2: raise e
                            time.sleep(3)
                finally:
                    for f in opened_files: f.close()
                time.sleep(1)
            log_download(uid, source_url, "success", size_mb=total_size_mb, platform=platform, title=video_title, sid=sid)
            update_download_stats()
            for f in downloaded_files: delayed_delete(f)
            _delete_progress_message(message.chat.id, progress_msg)
            return
        
        file_path = downloaded_files[0]
        file_size_bytes = os.path.getsize(file_path) if os.path.exists(file_path) else (info.get('filesize') or info.get('filesize_approx') or 0)
        file_size_mb = file_size_bytes / (1024 * 1024)
        video_title, video_description = extract_title_and_description(info, platform)

        # فحص الحجم بعد التحميل مع تخفيض متدرج (high→medium→low)
        effective_limit = int(Config.TELEGRAM_UPLOAD_LIMIT * 0.95)
        while file_size_bytes > effective_limit:
            next_q = _get_next_lower_quality(quality_type)
            if not next_q:
                bot.edit_message_text(_build_file_too_large_message(uid, file_size_mb), message.chat.id, progress_msg.message_id, parse_mode="HTML", reply_markup=get_error_markup(uid))
                if os.path.exists(file_path): os.remove(file_path)
                log_download(uid, source_url, "failed", platform=platform, sid=sid, size_mb=file_size_mb, error_reason="file_too_large")
                maybe_report_failure(uid, source_url, platform, "file_too_large", sid=sid, size_mb=file_size_mb, title=video_title)
                return
            
            if os.path.exists(file_path): os.remove(file_path)
            quality_type = next_q
            downgraded_text = translation_system.get(uid, 'downgraded_due_to_size')
            update_progress_message(progress_msg.message_id, message.chat.id, downgraded_text, 10)
            
            ydl_opts = get_ydl_opts_for_platform(download_url, quality_type, output_template, cookies_file)
            ydl_opts['progress_hooks'] = [download_progress_hook]
            
            info = youtube_safe_download(download_url, ydl_opts, max_retries=3) if platform == 'youtube' else enhanced_download_with_fallback(ydl_opts, download_url, max_retries=3)
            downloaded_files = find_all_downloaded_files(target_dir, sid)
            if not downloaded_files: raise Exception("No files downloaded on fallback")
            
            file_path = downloaded_files[0]
            file_size_bytes = os.path.getsize(file_path)
            file_size_mb = file_size_bytes / (1024 * 1024)
            video_title, video_description = extract_title_and_description(info, platform)

        duration = format_seconds(info.get('duration', 0))
        update_progress_message(progress_msg.message_id, message.chat.id, translation_system.get(uid, 'download_completed'), 0)
        caption = build_video_caption(uid, video_title, video_description, platform, duration, f"{file_size_mb:.2f}", Config.BOT_SIG)
        
        thumb_path = (generate_video_thumbnail(file_path, target_dir, sid) or download_thumbnail(info.get('thumbnail'), target_dir, sid)) if quality_type != 'audio' else None
        last_percent_dict = {'value': 0}
        upload_text = translation_system.get(uid, 'upload_started', default="🚀 جاري الرفع إلى تيليجرام...")
        
        ext = os.path.splitext(file_path)[1].lower().lstrip('.')
        if ext in IMAGE_EXTS:
            with ProgressFileReader(file_path, upload_progress_callback, progress_msg.message_id, message.chat.id, upload_text, last_percent_dict) as f:
                sent_msg = bot.send_photo(message.chat.id, f, caption=caption, parse_mode="HTML")
                if sent_msg and sent_msg.photo: save_to_cache(source_url, quality_type, sent_msg.photo[-1].file_id, title=video_title, platform=platform, size_mb=file_size_mb, duration=duration)
        elif quality_type == 'audio':
            with ProgressFileReader(file_path, upload_progress_callback, progress_msg.message_id, message.chat.id, upload_text, last_percent_dict) as a:
                sent_msg = bot.send_audio(message.chat.id, a, caption=f"🎵 <b>{video_title}</b>\n\n{Config.BOT_SIG}", parse_mode="HTML", timeout=500)
                if sent_msg and sent_msg.audio: save_to_cache(source_url, quality_type, sent_msg.audio.file_id, title=video_title, platform=platform, size_mb=file_size_mb, duration=duration)
        else:
            if quality_type == 'mute':
                mute_path = mute_video_file(file_path)
                if not mute_path:
                    _delete_progress_message(message.chat.id, progress_msg)
                    bot.send_message(message.chat.id, translation_system.get(uid, 'processing_error'), parse_mode="HTML", reply_markup=get_error_markup(uid))
                    log_download(uid, message.text, "failed", platform=platform, sid=sid, error_reason="processing_error")
                    return
                if os.path.exists(file_path): os.remove(file_path)
                file_path = mute_path
            
            # Check if splitting is needed
            limit_mb = Config.TELEGRAM_UPLOAD_LIMIT_MB
            safety_margin = 50 if limit_mb > 100 else 2
            max_chunk_size = max(5, limit_mb - safety_margin)
            files_to_upload = split_large_file(file_path, max_size_mb=max_chunk_size)
            
            for i, fp in enumerate(files_to_upload):
                part_caption = caption
                if len(files_to_upload) > 1:
                    part_caption = f"📦 <b>Part {i+1}/{len(files_to_upload)}</b>\n\n{caption}"
                
                with ProgressFileReader(fp, upload_progress_callback, progress_msg.message_id, message.chat.id, f"{upload_text} (Part {i+1})" if len(files_to_upload) > 1 else upload_text, last_percent_dict) as v:
                    t = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None
                    try:
                        markup = video_markup(sid, uid) if (quality_type != 'mute' and i == 0) else None
                        current_size_mb = os.path.getsize(fp) / (1024 * 1024)
                        if current_size_mb > Config.DOCUMENT_THRESHOLD_MB:
                            sent_msg = bot.send_document(message.chat.id, v, caption=part_caption, parse_mode="HTML", thumb=t, timeout=600, reply_markup=markup)
                        else:
                            sent_msg = bot.send_video(message.chat.id, v, caption=part_caption, parse_mode="HTML", timeout=500, supports_streaming=True, thumb=t, reply_markup=markup)
                    finally:
                        if t: t.close()
                if len(files_to_upload) > 1: delayed_delete(fp, delay=600)
            
            # Cache successfully sent single video
            if len(files_to_upload) == 1 and sent_msg:
                file_id = None
                if hasattr(sent_msg, 'video') and sent_msg.video:
                    file_id = sent_msg.video.file_id
                elif hasattr(sent_msg, 'document') and sent_msg.document:
                    file_id = sent_msg.document.file_id
                if file_id:
                    save_to_cache(source_url, quality_type, file_id, title=video_title, description=video_description, duration=duration, size_mb=file_size_mb, platform=platform)
        
        _delete_progress_message(message.chat.id, progress_msg)
        delayed_delete(file_path, delay=600)
        if thumb_path: delayed_delete(thumb_path, delay=600)
        update_download_stats()
        if BotState.report_logs and uid != Config.ADMIN_ID: send_download_report(uid, message.text, file_size_mb, video_title, platform, sid)
        log_download(uid, source_url, "success", size_mb=file_size_mb, platform=platform, title=video_title, sid=sid)

    except Exception as e:
        logger.error(f"DL Error {uid}: {e}")
        _delete_progress_message(message.chat.id, progress_msg)
        if "cancelled_by_user" in str(e).lower() or cancel_event.is_set():
            try:
                fp = find_downloaded_file(target_dir, sid)
                if fp: os.remove(fp)
            except: pass
            log_download(uid, source_url, "cancelled", platform=platform, sid=sid, error_reason="user_cancelled")
            bot.send_message(message.chat.id, translation_system.get(uid, 'download_cancelled'))
        else:
            error_reason, msg = _classify_download_error(uid, str(e), file_size_mb)
            log_download(uid, source_url, "failed", platform=platform, sid=sid, size_mb=file_size_mb, title=video_title, error_reason=error_reason)
            maybe_report_failure(uid, source_url, platform, error_reason, sid=sid, size_mb=file_size_mb, title=video_title)
            bot.send_message(message.chat.id, msg, parse_mode="HTML", reply_markup=get_error_markup(uid))
    finally:
        BotState.user_requests.pop(uid, None)

def process_local_conversion(message, sid, conversion_type):
    uid = message.from_user.id
    if not check_ffmpeg_available():
        bot.send_message(message.chat.id, translation_system.get(uid, 'ffmpeg_missing'), parse_mode="HTML")
        return
    target_dir = Config.ADMIN_DOWNLOADS if uid == Config.ADMIN_ID else Config.USERS_DOWNLOADS
    input_file = find_downloaded_file(target_dir, sid)
    if not input_file or not os.path.exists(input_file):
        original_url = get_url_by_sid(sid)
        if original_url: process_download(message, conversion_type, url=original_url)
        else: bot.send_message(message.chat.id, translation_system.get(uid, 'session_expired'), parse_mode="HTML")
        return
    
    input_ext = os.path.splitext(input_file)[1].lower() or ".mp4"
    output_file = os.path.join(target_dir, f"converted_{sid}.mp3" if conversion_type == 'audio' else f"converted_{sid}{input_ext}")
    msg = bot.send_message(message.chat.id, translation_system.get(uid, "processing"))
    try:
        cmd = ['ffmpeg', '-y', '-i', input_file, '-vn', '-acodec', 'libmp3lame', '-q:a', '2', output_file] if conversion_type == 'audio' else ['ffmpeg', '-y', '-i', input_file, '-c', 'copy', '-an', output_file]
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        if process.returncode != 0: raise Exception("Conversion failed")
        
        output_size = os.path.getsize(output_file)
        if output_size > Config.MAX_FILE_SIZE:
            bot.send_message(message.chat.id, _build_file_too_large_message(uid, output_size / (1024 * 1024)), parse_mode="HTML", reply_markup=get_error_markup(uid))
            delayed_delete(output_file)
            return
            
        original_url, title, performer = get_url_by_sid(sid), "Audio", f"@{get_bot_username()}"
        if original_url:
            cached = get_cached_media(original_url, 'dl_high') or get_cached_media(original_url, 'dl_medium') or get_cached_media(original_url, 'dl_low')
            if cached: title, performer = (cached.get('title') or "Audio")[:60], cached.get('platform', performer).title()
            
        with open(output_file, 'rb') as f:
            if conversion_type == 'audio':
                bot.send_audio(message.chat.id, f, caption=f"🎵 {translation_system.get(uid, 'audio_success', bot_sig=Config.BOT_SIG)}", parse_mode="HTML", title=title, performer=performer, timeout=500)
            else:
                if output_size / (1024 * 1024) > Config.DOCUMENT_THRESHOLD_MB:
                    bot.send_document(message.chat.id, f, caption=f"🔇 {translation_system.get(uid, 'mute_success', bot_sig=Config.BOT_SIG)}", parse_mode="HTML", timeout=500)
                else:
                    bot.send_video(message.chat.id, f, caption=f"🔇 {translation_system.get(uid, 'mute_success', bot_sig=Config.BOT_SIG)}", parse_mode="HTML", timeout=500)
        delayed_delete(output_file)
        try: bot.delete_message(message.chat.id, msg.message_id)
        except: pass
    except Exception:
        try: bot.delete_message(message.chat.id, msg.message_id)
        except: pass
        process_download(message, conversion_type, url=get_url_by_sid(sid))
