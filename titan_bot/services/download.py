import os
import time
import threading
import glob
import re
import yt_dlp
import subprocess
import requests
from urllib.parse import urlparse
from html import escape
from telebot import types
import telebot
from concurrent.futures import ThreadPoolExecutor, as_completed
import sqlite3

from titan_bot.core.config import (
    ADMIN_ID,
    BOT_SIG,
    ADMIN_DIR,
    USERS_DIR,
    DB_FILE,
    MAX_FILE_SIZE,
    TELEGRAM_UPLOAD_LIMIT,
    TELEGRAM_UPLOAD_LIMIT_MB,
    ALLOWED_PLATFORMS,
)
from titan_bot.core.loader import bot
import titan_bot.core.loader as loader
from titan_bot.core.loader import get_error_markup
from titan_bot.core.utils import (
    logger,
    format_seconds,
    delayed_delete,
    detect_platform_from_url,
    get_cookies_file,
    sanitize_filename,
    generate_sid,
    check_ffmpeg_available,
)
from titan_bot.core.database import log_download, update_download_stats, delete_user, get_user_details
from titan_bot.services.translation import translation_system

# دالة إنشاء رسالة التقدم
def create_progress_message(chat_id, text, percent=0, markup=None):
    try:
        bar = "▰" * int(percent / 10) + "▱" * (10 - int(percent / 10))
        msg = bot.send_message(chat_id, f"{text}\n{bar} {percent}%", reply_markup=markup)
        return msg
    except:
        return None

def update_progress_message(msg_id, chat_id, text, percent, markup=None):
    try:
        bar = "▰" * int(percent / 10) + "▱" * (10 - int(percent / 10))
        bot.edit_message_text(f"{text}\n{bar} {percent}%", chat_id, msg_id, reply_markup=markup)
        return True
    except:
        return False

def _acquire_download_slot(uid):
    with loader.state_lock:
        if uid in loader.active_downloads:
            return "already_processing"
        if len(loader.active_downloads) >= 15:
            return "server_busy"
        loader.active_downloads.add(uid)
        return "ok"


def _release_download_slot(uid):
    with loader.state_lock:
        loader.active_downloads.discard(uid)


def _start_progress(uid, message, sid, text):
    cancel_event = threading.Event()
    loader.user_requests[uid] = {'sid': sid, 'cancel_event': cancel_event}
    progress_markup = cancel_markup(sid, uid)
    progress_msg = create_progress_message(message.chat.id, text, 5, markup=progress_markup)
    return cancel_event, progress_msg, progress_markup


def _delete_progress_message(message, progress_msg):
    try:
        if progress_msg:
            bot.delete_message(message.chat.id, progress_msg.message_id)
    except:
        pass


def _contains_any(text, patterns):
    return any(pattern in text for pattern in patterns)


CAPTION_TEXT_LIMIT = 500
TELEGRAM_CAPTION_LIMIT = 1024


def _truncate_caption_text(text, max_length):
    text = (text or "").strip()
    if not text or max_length <= 0:
        return ""
    if len(text) <= max_length:
        return text
    if max_length <= 3:
        return text[:max_length]
    return text[:max_length - 3].rstrip() + "..."


def _fit_caption_title_and_description(title, description, total_limit=CAPTION_TEXT_LIMIT):
    title = (title or "Video").strip()
    description = (description or "").strip()

    if not description:
        return _truncate_caption_text(title, total_limit), ""

    combined_length = len(title) + len(description)
    if combined_length <= total_limit:
        return title, description

    if len(title) >= total_limit:
        return _truncate_caption_text(title, total_limit), ""

    remaining_for_description = total_limit - len(title)
    if remaining_for_description > 0:
        return title, _truncate_caption_text(description, remaining_for_description)

    return _truncate_caption_text(title, total_limit), ""


def _render_video_caption(uid, title, description, platform, duration, size, bot_sig):
    safe_title = escape((title or "Video").strip())
    safe_description = escape((description or "").strip())
    return translation_system.get(
        uid,
        'video_caption',
        title=safe_title,
        description=safe_description,
        platform=platform,
        duration=duration,
        size=size,
        bot_sig=bot_sig
    )


def _build_file_too_large_message(uid, size_mb=0):
    if size_mb and size_mb > 0:
        return translation_system.get(
            uid,
            'file_too_large',
            size=size_mb,
            limit_mb=TELEGRAM_UPLOAD_LIMIT_MB,
        )
    return translation_system.get(uid, 'file_too_large_unknown', limit_mb=TELEGRAM_UPLOAD_LIMIT_MB)


def _exceeds_telegram_upload_limit(size_bytes):
    return bool(size_bytes and TELEGRAM_UPLOAD_LIMIT > 0 and size_bytes > TELEGRAM_UPLOAD_LIMIT)


_METRIC_LINE_RE = re.compile(
    r"^\s*(?:"
    r"(?:[\d.,]+[KMBkmb]?\s*(?:views?|likes?|reactions?|comments?|shares?|followers?|following|subscribers?|reposts?|retweets?|bookmarks?|saves?))"
    r"|(?:[\d.,]+\s*(?:مشاهدات|مشاهدة|إعجابات|إعجاب|تفاعلات|تفاعل|تعليقات|تعليق|مشاركات|مشاركة|متابعين|متابع|إعادات نشر|حفظ))"
    r"|(?:[\d.,]+\s*(?:vues?|j'aime|réactions?|reactions?|commentaires?|partages?|abonnés?|enregistrements?))"
    r")(?:\s*[|,•·-]\s*"
    r"(?:(?:[\d.,]+[KMBkmb]?\s*(?:views?|likes?|reactions?|comments?|shares?|followers?|following|subscribers?|reposts?|retweets?|bookmarks?|saves?))"
    r"|(?:[\d.,]+\s*(?:مشاهدات|مشاهدة|إعجابات|إعجاب|تفاعلات|تفاعل|تعليقات|تعليق|مشاركات|مشاركة|متابعين|متابع|إعادات نشر|حفظ))"
    r"|(?:[\d.,]+\s*(?:vues?|j'aime|réactions?|reactions?|commentaires?|partages?|abonnés?|enregistrements?))))*\s*$",
    re.IGNORECASE,
)

_SEPARATOR_SPLIT_RE = re.compile(r"\s*(?:[|•·]+|\s[-–—]\s)\s*")

_METRIC_SEGMENT_RE = re.compile(
    r"^\s*(?:"
    r"(?:[\d.,]+[KMBkmb]?\s*(?:views?|likes?|reactions?|comments?|shares?|followers?|following|subscribers?|reposts?|retweets?|bookmarks?|saves?))"
    r"|(?:[\d.,]+\s*(?:مشاهدات|مشاهدة|إعجابات|إعجاب|تفاعلات|تفاعل|تعليقات|تعليق|مشاركات|مشاركة|متابعين|متابع|إعادات نشر|حفظ))"
    r"|(?:[\d.,]+\s*(?:vues?|j'aime|réactions?|reactions?|commentaires?|partages?|abonnés?|enregistrements?))"
    r")\s*$",
    re.IGNORECASE,
)

_WRAPPER_WORDS = {
    'by', 'from', 'official', 'account', 'channel', 'page', 'profile', 'profil',
    'compte', 'user', 'creator', 'uploader', 'reel', 'reels', 'video', 'post',
    'watch', 'short', 'shorts', 'story', 'stories', 'sound', 'original',
    'من', 'حساب', 'صاحب', 'الناشر', 'القناة', 'المستخدم', 'بواسطة', 'مقطع',
    'فيديو', 'ريل', 'ريلز', 'منشور', 'ستوري', 'story', 'vidéo', 'publication',
    'par', 'de', 'compte', 'chaine', 'chaîne'
}

_GENERIC_TITLE_PREFIX_RE = re.compile(
    r"^(?:"
    r"(?:video|reel|reels|post|story|stories|watch|short|shorts|clip|sound)"
    r"|(?:فيديو|ريل|ريلز|منشور|ستوري|مقطع|صوت)"
    r"|(?:vidéo|publication|story|clip|son)"
    r")\b",
    re.IGNORECASE,
)


def _collect_metadata_values(info):
    values = set()
    for key in (
        'uploader', 'uploader_id', 'channel', 'channel_id',
        'creator', 'artist', 'album_artist', 'display_id'
    ):
        value = info.get(key)
        if not value:
            continue
        normalized = " ".join(str(value).split()).strip().lower()
        if normalized:
            values.add(normalized)
            values.add(f"@{normalized.lstrip('@')}")
    return values


def _normalize_text_value(text):
    return " ".join(str(text).split()).strip().lower()


def _metadata_variants(metadata_values):
    variants = set()
    for value in metadata_values:
        normalized = _normalize_text_value(value)
        if not normalized:
            continue
        variants.add(normalized)
        variants.add(normalized.lstrip('@'))
        variants.add(f"@{normalized.lstrip('@')}")
    return {v for v in variants if v}


def _is_metric_segment(segment):
    normalized = " ".join(segment.split()).strip()
    return bool(normalized and _METRIC_SEGMENT_RE.match(normalized))


def _is_metadata_segment(segment, metadata_values):
    normalized = _normalize_text_value(segment)
    if not normalized:
        return False

    variants = _metadata_variants(metadata_values)
    if normalized in variants or normalized.lstrip('@') in variants:
        return True

    for value in sorted(variants, key=len, reverse=True):
        plain = value.lstrip('@')
        if not plain:
            continue
        if plain not in normalized:
            continue
        remainder = normalized.replace(f"@{plain}", " ").replace(plain, " ")
        tokens = re.findall(r"[\w\u0600-\u06FF']+", remainder)
        if tokens and all(token in _WRAPPER_WORDS for token in tokens):
            return True
        if not tokens:
            return True

    return False


def _strip_metadata_edges(text, metadata_values):
    line = text.strip()
    variants = sorted(_metadata_variants(metadata_values), key=len, reverse=True)
    for value in variants:
        plain = value.lstrip('@')
        if not plain:
            continue
        prefix_pattern = rf"^(?:@?{re.escape(plain)})(?:\s*(?:[|•·]|[-–—])\s*|\s+)"
        suffix_pattern = rf"(?:\s*(?:[|•·]|[-–—])\s*|\s+)(?:@?{re.escape(plain)})$"
        new_line = re.sub(prefix_pattern, "", line, flags=re.IGNORECASE).strip()
        new_line = re.sub(suffix_pattern, "", new_line, flags=re.IGNORECASE).strip()
        if new_line != line:
            line = new_line
    return line


def _strip_metric_edges(text):
    line = text.strip()
    parts = [part.strip() for part in _SEPARATOR_SPLIT_RE.split(line) if part.strip()]
    if len(parts) >= 2:
        kept_parts = [part for part in parts if not _is_metric_segment(part)]
        if kept_parts:
            line = " - ".join(kept_parts).strip()
    return line


def _is_wrapper_only_text(text, metadata_values):
    normalized = _normalize_text_value(text)
    if not normalized:
        return True

    stripped = _strip_metadata_edges(normalized, metadata_values)
    stripped = _strip_metric_edges(stripped)
    stripped = stripped.replace('@', ' ')

    tokens = re.findall(r"[\w\u0600-\u06FF']+", stripped)
    meaningful = [token for token in tokens if token not in _WRAPPER_WORDS]
    return not meaningful


def _sanitize_caption_line(line, metadata_values):
    normalized = " ".join(line.split()).strip()
    if not normalized:
        return ""

    parts = [part.strip() for part in _SEPARATOR_SPLIT_RE.split(normalized) if part.strip()]
    if len(parts) >= 2:
        kept_parts = [
            part for part in parts
            if not _is_metric_segment(part) and not _is_metadata_segment(part, metadata_values)
        ]
        if kept_parts:
            normalized = " - ".join(kept_parts).strip()
        else:
            normalized = ""

    normalized = _strip_metadata_edges(normalized, metadata_values)
    normalized = _strip_metric_edges(normalized)
    normalized = normalized.strip(" -|•·")

    if normalized and _is_wrapper_only_text(normalized, metadata_values):
        return ""

    return normalized


def _should_drop_caption_line(line, metadata_values):
    normalized = " ".join(line.split()).strip()
    if not normalized:
        return False

    lowered = normalized.lower()
    if lowered in metadata_values:
        return True

    if normalized.startswith("@") and lowered in metadata_values:
        return True

    if _METRIC_LINE_RE.match(normalized):
        return True

    if re.match(r"^(follow|following|suivre|abonnez-vous)\b", lowered) and "@" in normalized:
        return True

    return False


def _clean_media_text(text, info, single_line=False):
    text = (text or "").replace("\r\n", "\n").strip()
    if not text:
        return ""

    metadata_values = _collect_metadata_values(info or {})
    cleaned_lines = []
    for raw_line in text.splitlines():
        line = _sanitize_caption_line(raw_line, metadata_values)
        if not line:
            if cleaned_lines and cleaned_lines[-1] != "" and not single_line:
                cleaned_lines.append("")
            continue
        if _should_drop_caption_line(line, metadata_values):
            continue
        cleaned_lines.append(line)

    while cleaned_lines and cleaned_lines[-1] == "":
        cleaned_lines.pop()

    cleaned_text = "\n".join(cleaned_lines).strip()
    if single_line and cleaned_text:
        cleaned_text = cleaned_text.splitlines()[0].strip()

    return cleaned_text


def _iter_info_variants(info):
    if not isinstance(info, dict):
        return []

    variants = [info]
    for key in ('requested_entries', 'entries'):
        entries = info.get(key)
        if not isinstance(entries, list):
            continue
        for entry in entries:
            if isinstance(entry, dict):
                variants.append(entry)
    return variants


def _collect_all_metadata_values(info_variants):
    metadata_values = set()
    for variant in info_variants:
        metadata_values.update(_collect_metadata_values(variant))
    return metadata_values


def _clean_media_field(raw_text, info_variants, single_line=False):
    if not raw_text:
        return ""

    combined_info = dict(info_variants[0]) if info_variants else {}
    for variant in info_variants[1:]:
        combined_info.update({k: v for k, v in variant.items() if v})

    return _clean_media_text(raw_text, combined_info, single_line=single_line)


def _is_generic_media_title(title, metadata_values):
    normalized = " ".join((title or "").split()).strip()
    if not normalized:
        return True

    lowered = normalized.lower()
    if lowered in metadata_values or lowered.lstrip('@') in _metadata_variants(metadata_values):
        return True

    if _is_metadata_segment(normalized, metadata_values):
        return True

    if _is_wrapper_only_text(normalized, metadata_values):
        return True

    if _GENERIC_TITLE_PREFIX_RE.match(normalized) and _is_metadata_segment(normalized, metadata_values):
        return True

    if _GENERIC_TITLE_PREFIX_RE.match(normalized) and _is_wrapper_only_text(normalized, metadata_values):
        return True

    return False


def _remove_title_from_description(title, description):
    if not title or not description:
        return description

    title_norm = _normalize_text_value(title)
    lines = [line.strip() for line in description.splitlines()]
    while lines and (_normalize_text_value(lines[0]) == title_norm or lines[0].strip(" -|•·") == title.strip(" -|•·")):
        lines.pop(0)

    cleaned = "\n".join(line for line in lines if line).strip()
    return cleaned


def _compact_compare_text(text):
    normalized = _normalize_text_value(text)
    normalized = normalized.replace('@', '')
    return re.sub(r"[^\w\u0600-\u06FF]+", "", normalized)


def _remove_repeated_title_blocks(title, description):
    if not title or not description:
        return description

    title_compact = _compact_compare_text(title)
    if not title_compact:
        return description.strip()

    lines = [line.strip() for line in description.splitlines() if line.strip()]
    if not lines:
        return ""

    # Remove any standalone line that is just the title again.
    lines = [line for line in lines if _compact_compare_text(line) != title_compact]

    # Remove a leading multi-line block when several first lines together equal the title.
    while lines:
        matched_block = 0
        for i in range(1, len(lines) + 1):
            if _compact_compare_text(" ".join(lines[:i])) == title_compact:
                matched_block = i
                break
        if not matched_block:
            break
        lines = lines[matched_block:]

    # Drop consecutive duplicates after normalization.
    deduped_lines = []
    for line in lines:
        if deduped_lines and _compact_compare_text(deduped_lines[-1]) == _compact_compare_text(line):
            continue
        deduped_lines.append(line)

    cleaned = "\n".join(deduped_lines).strip()
    if _compact_compare_text(cleaned) == title_compact:
        return ""
    return cleaned


def _extract_title_and_description(info, platform):
    info_variants = _iter_info_variants(info)
    if not info_variants:
        return "Video", ""

    metadata_values = _collect_all_metadata_values(info_variants)

    title_field_orders = {
        'youtube': ('track', 'fulltitle', 'title', 'alt_title'),
        'tiktok': ('title', 'description', 'fulltitle', 'alt_title', 'track'),
        'instagram': ('title', 'description', 'fulltitle', 'alt_title'),
        'facebook': ('title', 'description', 'fulltitle', 'alt_title'),
        'twitter': ('title', 'description', 'fulltitle', 'alt_title'),
        'threads': ('title', 'description', 'fulltitle', 'alt_title'),
        'pinterest': ('title', 'description', 'fulltitle', 'alt_title'),
        'snapchat': ('title', 'description', 'fulltitle', 'alt_title'),
    }
    description_field_orders = {
        'youtube': ('description', 'full_description', 'synopsis'),
        'tiktok': ('description', 'full_description', 'title', 'fulltitle'),
        'instagram': ('description', 'full_description', 'title', 'fulltitle'),
        'facebook': ('description', 'full_description', 'title', 'fulltitle'),
        'twitter': ('description', 'full_description', 'title', 'fulltitle'),
        'threads': ('description', 'full_description', 'title', 'fulltitle'),
        'pinterest': ('description', 'full_description', 'title', 'fulltitle'),
        'snapchat': ('description', 'full_description', 'title', 'fulltitle'),
    }

    title_candidates = title_field_orders.get(platform, ('title', 'fulltitle', 'alt_title', 'track', 'description'))
    description_candidates = description_field_orders.get(platform, ('description', 'full_description', 'synopsis', 'title'))

    title = ""
    for field in title_candidates:
        for variant in info_variants:
            candidate = _clean_media_field(variant.get(field), info_variants, single_line=True)
            if candidate and not _is_generic_media_title(candidate, metadata_values):
                title = candidate
                break
        if title:
            break

    description = ""
    for field in description_candidates:
        for variant in info_variants:
            candidate = _clean_media_field(variant.get(field), info_variants, single_line=False)
            if candidate:
                description = candidate
                break
        if description:
            break

    if not title and description:
        desc_lines = [line.strip() for line in description.splitlines() if line.strip()]
        if desc_lines:
            title = desc_lines[0]
            description = "\n".join(desc_lines[1:]).strip()

    if title and description:
        description = _remove_title_from_description(title, description)
        description = _remove_repeated_title_blocks(title, description)

    if not title:
        title = "Video"

    return _fit_caption_title_and_description(title, description)


def _build_video_caption(uid, title, description, platform, duration, size, bot_sig):
    title, description = _fit_caption_title_and_description(title, description)
    caption = _render_video_caption(uid, title, description, platform, duration, size, bot_sig)
    if len(caption) <= TELEGRAM_CAPTION_LIMIT:
        return caption

    title = (title or "Video").strip()
    description = (description or "").strip()

    for _ in range(8):
        overflow = len(caption) - TELEGRAM_CAPTION_LIMIT
        if overflow <= 0:
            return caption

        reduced = False
        if description:
            new_description = _truncate_caption_text(description, max(0, len(description) - overflow - 3))
            if new_description != description:
                description = new_description
                reduced = True

        if not reduced:
            new_title = _truncate_caption_text(title, max(1, len(title) - overflow - 3))
            if not new_title:
                new_title = "Video"
            if new_title != title:
                title = new_title
                reduced = True

        caption = _render_video_caption(uid, title, description, platform, duration, size, bot_sig)
        if not reduced:
            break

    if len(caption) > TELEGRAM_CAPTION_LIMIT:
        caption = _render_video_caption(uid, _truncate_caption_text(title or "Video", 80), "", platform, duration, size, bot_sig)

    return caption


def _classify_download_error(uid, error_text, size_mb=0):
    er_msg = (error_text or "").lower()

    if _contains_any(er_msg, [
        "request entity too large",
        "error code: 413",
        "too large",
        "max_filesize",
        "file is too big",
    ]):
        return "file_too_large", _build_file_too_large_message(uid, size_mb)

    if _contains_any(er_msg, [
        "there is no video in this post",
        "no video in this post",
    ]):
        return "no_video_in_post", translation_system.get(uid, 'no_video_in_post')

    if _contains_any(er_msg, [
        "your ip address is blocked",
        "ip address is blocked",
    ]):
        return "service_blocked", translation_system.get(uid, 'service_blocked')

    if _contains_any(er_msg, [
        "unsupported url",
        "does not have a",
        "does not have a ",
    ]):
        return "unsupported_url", translation_system.get(uid, 'unsupported_url')

    if _contains_any(er_msg, [
        "private",
        "sign in",
        "log in",
        "login",
        "registered users",
        "follow this account",
        "authentication",
        "cookies",
        "you need to log in",
        "empty media response",
    ]):
        return "private_or_login", translation_system.get(uid, 'private_or_login')

    if _contains_any(er_msg, [
        "failed to resolve",
        "name resolution",
        "connection aborted",
        "connection reset",
        "timed out",
        "timeout",
        "max retries exceeded",
        "read timed out",
        "connect timeout",
    ]):
        return "network_error", translation_system.get(uid, 'weak_connection')

    if _contains_any(er_msg, [
        "cannot parse data",
        "unable to extract data",
        "no video formats found",
        "file empty or not found",
        "redirect loop detected",
    ]):
        return "temporary_source_issue", translation_system.get(uid, 'temporary_source_issue')

    if _contains_any(er_msg, [
        "this video is not available",
        "video unavailable",
        "no longer available",
        "account associated with this video has been terminated",
        "removed",
        "http error 404",
    ]):
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
                if total:
                    percent = (d.get('downloaded_bytes', 0) / total) * 100
                    if int(percent) - last_progress['value'] >= 10 or percent >= 98:
                        if update_progress_message(progress_msg.message_id, chat_id, text, int(percent), markup=progress_markup):
                            last_progress['value'] = int(percent)
            except:
                pass
        elif d['status'] == 'finished':
            update_progress_message(progress_msg.message_id, chat_id, text, 100, markup=progress_markup)

    return _hook


def _handle_photo_not_supported(message, uid, platform, sid):
    bot.send_message(message.chat.id, translation_system.get(uid, 'photo_not_supported'), parse_mode="HTML", reply_markup=get_error_markup(uid))
    log_download(uid, message.text, "failed", platform=platform, sid=sid, error_reason="photo_not_supported")
    maybe_report_failure(uid, message.text, platform, "photo_not_supported", sid=sid)


def get_bot_username():
    if loader.BOT_USERNAME:
        return loader.BOT_USERNAME
    try:
        loader.BOT_USERNAME = bot.get_me().username
    except Exception:
        loader.BOT_USERNAME = ""
    return loader.BOT_USERNAME

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
        headers = {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': '*/*',
        }
        resp = session.head(url, allow_redirects=True, timeout=10, headers=headers)
        if resp.url:
            return resp.url
        if resp.status_code in (403, 405):
            resp = session.get(url, allow_redirects=True, timeout=10, headers=headers)
            if resp.url:
                return resp.url
    except Exception:
        pass
    return url

def prepare_tiktok_urls(url):
    parsed = urlparse(url)
    if parsed.netloc in ['vm.tiktok.com', 'vt.tiktok.com', 't.tiktok.com', 'm.tiktok.com']:
        url = expand_short_url(url)
    normalized = url
    if '/photo/' in url:
        normalized = url.replace('/photo/', '/video/')
    return url, normalized

def find_downloaded_file(target_dir, sid, preferred_ext=None, prefix="video"):
    if preferred_ext:
        preferred_ext = preferred_ext.lstrip(".")
        preferred = os.path.join(target_dir, f"{prefix}_{sid}.{preferred_ext}")
        if os.path.exists(preferred):
            return preferred

    pattern = os.path.join(target_dir, f"{prefix}_{sid}.*")
    candidates = glob.glob(pattern)
    if not candidates:
        return None
    return max(candidates, key=lambda p: os.path.getmtime(p))

def mute_video_file(input_path):
    base, ext = os.path.splitext(input_path)
    muted_path = f"{base}_muted{ext}"
    try:
        subprocess.run(
            ['ffmpeg', '-y', '-i', input_path, '-c', 'copy', '-an', muted_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        return muted_path
    except Exception as e:
        logger.error(f"Post-download mute error: {e}")
        return None

def _shrink_thumbnail(path):
    if not path or not os.path.exists(path):
        return None
    if os.path.getsize(path) <= 200 * 1024:
        return path
    if not check_ffmpeg_available():
        return None
    try:
        tmp_path = path + ".tmp.jpg"
        subprocess.run(
            ['ffmpeg', '-y', '-i', path, '-vf', 'scale=320:-1', '-q:v', '5', tmp_path],
            check=True,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
        )
        if os.path.exists(tmp_path) and os.path.getsize(tmp_path) <= 200 * 1024:
            try:
                os.replace(tmp_path, path)
            except Exception:
                pass
            return path
        try:
            os.remove(tmp_path)
        except Exception:
            pass
    except Exception:
        pass
    return None

def generate_video_thumbnail(file_path, target_dir, sid):
    if not check_ffmpeg_available():
        return None
    if not file_path or not os.path.exists(file_path):
        return None
    thumb_path = os.path.join(target_dir, f"thumb_{sid}.jpg")
    for ts in ["00:00:01", "00:00:00"]:
        try:
            subprocess.run(
                ['ffmpeg', '-y', '-ss', ts, '-i', file_path, '-frames:v', '1', '-vf', 'scale=320:-1', '-q:v', '5', thumb_path],
                check=True,
                stdout=subprocess.DEVNULL,
                stderr=subprocess.DEVNULL,
            )
            if os.path.exists(thumb_path):
                return _shrink_thumbnail(thumb_path) or thumb_path
        except Exception:
            pass
    return None

def download_thumbnail(url, target_dir, sid):
    if not url:
        return None
    try:
        resp = requests.get(url, timeout=10)
        if resp.status_code != 200 or not resp.content:
            return None
        thumb_path = os.path.join(target_dir, f"thumb_{sid}.jpg")
        with open(thumb_path, 'wb') as f:
            f.write(resp.content)
        return _shrink_thumbnail(thumb_path) or thumb_path
    except Exception:
        return None

IMAGE_EXTS = {"jpg", "jpeg", "png", "webp", "gif"}

def get_ydl_opts_for_platform(url, quality_type='high', output_path=None, cookies_file=None):
    # إعدادات أساسية
    ydl_opts = {
        'outtmpl': output_path,
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'geo_bypass': True,
        'ignoreerrors': False,
        'socket_timeout': 30,
        'source_address': '0.0.0.0',
        'max_filesize': MAX_FILE_SIZE,
        'merge_output_format': 'mp4',
        'http_headers': {
            'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
            'Accept-Language': 'en-us,en;q=0.5',
        }
    }

    if cookies_file:
        ydl_opts['cookiefile'] = cookies_file

    platform = detect_platform_from_url(url)

    # Apply shared defaults
    ydl_opts['noplaylist'] = True
    if platform == 'instagram':
        ydl_opts['extractor_args'] = {'instagram': {'api_request': 'ios'}}

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

    if platform == 'instagram':
        ydl_opts.update({
             'format': 'best'
        })
    elif platform == 'tiktok':
        ydl_opts.update({
            'format': 'best',
            'noplaylist': True
        })
    elif platform == 'facebook':
        if quality_type == 'high':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        elif quality_type == 'medium':
            ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480]/bestvideo+bestaudio/best'
        else:
            ydl_opts['format'] = 'worstvideo+bestaudio/worst'
    elif platform == 'youtube':
        if 'shorts' in url.lower():
            # Shorts specific handling: use 'best' directly to avoid format selector issues
            ydl_opts['format'] = 'best'
        elif quality_type == 'high':
             # Radical Fix: Just ask for the best available video+audio combo
             ydl_opts['format'] = 'bestvideo+bestaudio/best'
        elif quality_type == 'medium':
             # Try 480p, fallback to best if not available
             ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480]/bestvideo+bestaudio/best'
        elif quality_type == 'audio':
             ydl_opts['format'] = 'bestaudio/best'
             ydl_opts['postprocessors'] = [{
                 'key': 'FFmpegExtractAudio',
                 'preferredcodec': 'mp3',
                 'preferredquality': '192',
             }]
        else:
             ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480]'
        ydl_opts['noplaylist'] = True
    else:
        # Generic fallback for other platforms
        if quality_type == 'high':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        elif quality_type == 'medium':
             # Try 480p, fallback to best if not available
            ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480]/bestvideo+bestaudio/best'
        ydl_opts['noplaylist'] = True
    
    return ydl_opts

def youtube_safe_download(url, ydl_opts, max_retries=3):
    """تحميل آمن من يوتيوب مع محاولات متعددة واستراتيجية التراجع"""
    original_format = ydl_opts.get('format')
    
    for i in range(max_retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info
        except Exception as e:
            logger.warning(f"YouTube Try {i+1} failed: {e}")
            time.sleep(1)
            
            # استراتيجية التراجع في الجودة (Nuclear Option)
            if i == 0:
                # المحاولة الثانية: حذف الفلاتر، الكوكيز، واستخدام best
                logger.info("Falling back to 'best' format, clearing filters and cookies")
                ydl_opts['format'] = 'best'
                ydl_opts['match_filter'] = None
                if 'cookiefile' in ydl_opts:
                    del ydl_opts['cookiefile']
            elif i == max_retries - 2:
                # المحاولة قبل الأخيرة: حذف الفلاتر، الكوكيز، واستخدام worst
                logger.info("Falling back to 'worst' format, clearing filters and cookies")
                ydl_opts['format'] = 'worst'
                ydl_opts['match_filter'] = None
                if 'cookiefile' in ydl_opts:
                    del ydl_opts['cookiefile']
            elif i == max_retries - 1:
                # المحاولة الأخيرة: فشل نهائي
                raise e
    raise Exception("Youtube download failed after retries")

def enhanced_download_with_fallback(ydl_opts, url, max_retries=3):
    """تحميل محسن مع fallback"""
    for i in range(max_retries):
        try:
            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info
        except Exception as e:
            logger.warning(f"Download Try {i+1} failed: {e}")
            time.sleep(2)
            if i == max_retries - 1:
                raise e
    return None

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
    """إرسال تقرير للمدير مع تفاصيل المستخدم"""
    try:
        user_info = get_user_details(user_id)
        
        # تنسيق اسم المستخدم بدون تكرار @
        username = "No Username"
        if user_info and user_info['username']:
            u = user_info['username']
            username = f"@{u}" if not u.startswith('@') else u
            
        total_dls = user_info['download_count'] if user_info else 0
        
        # إنشاء رابط قابل للنقر
        short_title = title[:40] + "..." if len(title) > 40 else title
        clean_url = url
        
        msg = (f"📥 <b>تحميل جديد:</b>\n\n"
               f"👤 <b>من:</b> {user_id} | {username}\n"
               f"🔢 <b>عدد التحميلات:</b> {total_dls}\n"
               f"📱 <b>منصة:</b> {platform}\n"
               f"💾 <b>حجم:</b> {size:.2f} MB\n"
               f"🎞 <b>عنوان:</b> {short_title}\n"
               f"🔗 <b>الرابط:</b> <a href='{clean_url}'>اضغط هنا لفتحه</a>")
               
        # زر نسخ الرابط
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("📋 نسخ الرابط", callback_data=f"copy_link|{sid}"))
        
        bot.send_message(ADMIN_ID, msg, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.error(f"Report error: {e}")
        pass

def _failure_reason_text(reason):
    reasons = {
        "invalid_link": "رابط غير صالح",
        "unsupported_platform": "منصة غير مدعومة",
        "unsupported_url": "رابط غير مدعوم",
        "ffmpeg_missing": "FFmpeg غير متوفر",
        "file_too_large": "الملف كبير جداً",
        "processing_error": "خطأ أثناء المعالجة",
        "photo_not_supported": "تحميل الصور غير مدعوم حالياً",
        "no_video_in_post": "المنشور لا يحتوي على فيديو",
        "private_or_login": "الفيديو خاص/يتطلب تسجيل دخول",
        "unavailable": "الفيديو غير متاح أو محذوف",
        "network_error": "مشكلة اتصال مؤقتة",
        "temporary_source_issue": "تعذر قراءة الملف من المنصة",
        "service_blocked": "المنصة رفضت الطلب مؤقتاً",
        "download_error": "خطأ تحميل عام",
    }
    return reasons.get(reason, reason or "غير معروف")

def send_failure_report(user_id, url, platform, reason, sid="", size_mb=0, title=""):
    """إرسال تقرير فشل للمدير"""
    try:
        user_info = get_user_details(user_id)
        username = "No Username"
        if user_info and user_info['username']:
            u = user_info['username']
            username = f"@{u}" if not u.startswith('@') else u

        total_dls = user_info['download_count'] if user_info else 0
        reason_text = _failure_reason_text(reason)
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

        bot.send_message(ADMIN_ID, msg, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.error(f"Failure report error: {e}")
        pass

def maybe_report_failure(user_id, url, platform, reason, sid="", size_mb=0, title=""):
    if loader.REPORT_LOGS and user_id != ADMIN_ID:
        send_failure_report(user_id, url, platform, reason, sid=sid, size_mb=size_mb, title=title)

def process_download(message, quality_type):
    uid = message.from_user.id
    time.sleep(0.5)
    
    slot_status = _acquire_download_slot(uid)
    if slot_status == "already_processing":
        bot.send_message(message.chat.id, translation_system.get(uid, 'already_processing'), parse_mode="HTML")
        return
    if slot_status == "server_busy":
        bot.send_message(message.chat.id, translation_system.get(uid, 'server_busy'), parse_mode="HTML")
        return
    
    progress_msg = None
    upload_event = threading.Event()
    
    try:
        sid = sanitize_filename(generate_sid())
        platform = detect_platform_from_url(message.text)
        source_url = message.text
        download_url = message.text
        video_title = ""
        file_size_mb = 0
        if platform == 'tiktok':
            source_url, download_url = prepare_tiktok_urls(message.text)
            if source_url != message.text:
                logger.info(f"Expanded TikTok URL: {source_url}")
            if download_url != source_url:
                logger.info(f"Fallback TikTok URL: {download_url}")
            if '/photo/' in source_url:
                _handle_photo_not_supported(message, uid, platform, sid)
                return
        if platform not in ALLOWED_PLATFORMS:
            if platform == 'other':
                msg = translation_system.get(uid, 'invalid_link')
                error_reason = "invalid_link"
            else:
                platforms_text = ", ".join([p.title() for p in ALLOWED_PLATFORMS])
                msg = translation_system.get(uid, 'unsupported_platform', platforms=platforms_text)
                error_reason = "unsupported_platform"

            bot.send_message(
                message.chat.id,
                msg,
                parse_mode="HTML",
                reply_markup=get_error_markup(uid)
            )
            log_download(uid, message.text, "failed", platform=platform, sid=sid, error_reason=error_reason)
            if error_reason != "invalid_link":
                maybe_report_failure(uid, message.text, platform, error_reason, sid=sid)
            return

        if quality_type in ['audio', 'mute'] and not check_ffmpeg_available():
            bot.send_message(message.chat.id, translation_system.get(uid, 'ffmpeg_missing'), parse_mode="HTML", reply_markup=get_error_markup(uid))
            log_download(uid, message.text, "failed", platform=platform, sid=sid, error_reason="ffmpeg_missing")
            maybe_report_failure(uid, message.text, platform, "ffmpeg_missing", sid=sid)
            return

        download_started_text = translation_system.get(uid, 'download_started')
        cancel_event, progress_msg, progress_markup = _start_progress(uid, message, sid, download_started_text)
        target_dir = ADMIN_DIR if uid == ADMIN_ID else USERS_DIR
        output_template = os.path.join(target_dir, f"video_{sid}.%(ext)s")
        
        cookies_file = get_cookies_file(message.text)
        
        download_progress_hook = _build_progress_hook(cancel_event, progress_msg, message.chat.id, download_started_text, progress_markup)
        
        ydl_opts = get_ydl_opts_for_platform(source_url, quality_type, output_template, cookies_file)
        ydl_opts['progress_hooks'] = [download_progress_hook]
        
        if cookies_file and platform:
            logger.info(f"Using cookies for {platform}: {os.path.basename(cookies_file)}")

        _pre_info, pre_size = precheck_media_info(source_url, ydl_opts)
        if _exceeds_telegram_upload_limit(pre_size):
            size_mb = pre_size / (1024 * 1024)
            file_too_large_text = _build_file_too_large_message(uid, size_mb)
            try:
                if progress_msg:
                    bot.edit_message_text(
                        file_too_large_text,
                        message.chat.id,
                        progress_msg.message_id,
                        parse_mode="HTML",
                        reply_markup=get_error_markup(uid)
                    )
            except:
                pass
            log_download(uid, message.text, "failed", platform=platform, sid=sid, size_mb=size_mb, error_reason="file_too_large")
            maybe_report_failure(uid, message.text, platform, "file_too_large", sid=sid, size_mb=size_mb)
            return

        if cancel_event.is_set():
            raise Exception("cancelled_by_user")
        try:
        
            if _pre_info is None and platform == 'tiktok' and download_url != source_url:
                ydl_opts = get_ydl_opts_for_platform(download_url, quality_type, output_template, cookies_file)
                _pre_info, pre_size = precheck_media_info(download_url, ydl_opts)
                if _exceeds_telegram_upload_limit(pre_size):
                    size_mb = pre_size / (1024 * 1024)
                    file_too_large_text = _build_file_too_large_message(uid, size_mb)
                    try:
                        if progress_msg:
                            bot.edit_message_text(
                                file_too_large_text,
                                message.chat.id,
                                progress_msg.message_id,
                                parse_mode="HTML",
                                reply_markup=get_error_markup(uid)
                            )
                    except:
                        pass
                    log_download(uid, message.text, "failed", platform=platform, sid=sid, size_mb=size_mb, error_reason="file_too_large")
                    maybe_report_failure(uid, message.text, platform, "file_too_large", sid=sid, size_mb=size_mb)
                    return

            if platform == 'youtube':
                info = youtube_safe_download(download_url, ydl_opts, max_retries=3)
            else:
                info = enhanced_download_with_fallback(ydl_opts, download_url, max_retries=3)
        
            file_path = find_downloaded_file(
                target_dir,
                sid,
                preferred_ext='mp3' if quality_type == 'audio' else None
            )
            if file_path and os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                if platform in ['tiktok', 'instagram'] and ext in IMAGE_EXTS:
                    try:
                        os.remove(file_path)
                    except:
                        pass
                    _delete_progress_message(message, progress_msg)
                    _handle_photo_not_supported(message, uid, platform, sid)
                    return
                if file_path and os.path.exists(file_path):
                    file_size_bytes = os.path.getsize(file_path)
                else:
                    file_size_bytes = info.get('filesize') or info.get('filesize_approx') or 0
                file_size_mb = file_size_bytes / (1024 * 1024) if file_size_bytes else 0

                video_title, video_description = _extract_title_and_description(info, platform)
                if _exceeds_telegram_upload_limit(file_size_bytes):
                    file_too_large_text = _build_file_too_large_message(uid, file_size_mb)
                    bot.edit_message_text(
                        file_too_large_text,
                        message.chat.id,
                        progress_msg.message_id,
                        parse_mode="HTML",
                        reply_markup=get_error_markup(uid)
                    )
                    if file_path and os.path.exists(file_path):
                        try: os.remove(file_path)
                        except: pass
                    log_download(uid, message.text, "failed", platform=platform, sid=sid, size_mb=file_size_mb, error_reason="file_too_large")
                    maybe_report_failure(uid, message.text, platform, "file_too_large", sid=sid, size_mb=file_size_mb, title=video_title)
                    return

                duration = format_seconds(info.get('duration', 0))
                formatted_size = f"{file_size_mb:.2f}"

                if file_path and os.path.exists(file_path) and os.path.getsize(file_path) > 0:
                    download_completed_text = translation_system.get(uid, 'download_completed')
                    update_progress_message(progress_msg.message_id, message.chat.id, download_completed_text, 0)
            
                    caption = _build_video_caption(
                        uid,
                        video_title,
                        video_description,
                        platform,
                        duration,
                        formatted_size,
                        BOT_SIG
                    )

                    def simulate_upload_progress():
                        try:
                            est_time = max(0.2, min(1.5, file_size_mb / 100))
                            for i in range(10, 101, 10):
                                if upload_event.wait(est_time): break
                                update_progress_message(progress_msg.message_id, message.chat.id, download_completed_text, i)
                            time.sleep(0.5)
                            try: bot.delete_message(message.chat.id, progress_msg.message_id)
                            except: pass
                        except: pass

                    upload_thread = threading.Thread(target=simulate_upload_progress, daemon=True)
                    upload_thread.start()

                    thumb_path = None
                    if quality_type != 'audio':
                        thumb_path = generate_video_thumbnail(file_path, target_dir, sid)
                        if not thumb_path:
                            thumb_path = download_thumbnail(info.get('thumbnail'), target_dir, sid)

                    if quality_type == 'audio':
                        with open(file_path, 'rb') as a:
                            bot.send_audio(
                                message.chat.id, a,
                                caption=f"🎵 <b>{video_title}</b>\n\n{BOT_SIG}",
                                parse_mode="HTML"
                            )
                    elif quality_type == 'mute':
                        mute_path = mute_video_file(file_path)
                        if not mute_path or not os.path.exists(mute_path):
                            upload_event.set()
                            _delete_progress_message(message, progress_msg)
                            bot.send_message(
                                message.chat.id,
                                translation_system.get(uid, 'processing_error'),
                                parse_mode="HTML",
                                reply_markup=get_error_markup(uid)
                            )
                            log_download(uid, message.text, "failed", platform=platform, sid=sid, error_reason="processing_error")
                            maybe_report_failure(uid, message.text, platform, "processing_error", sid=sid, title=video_title)
                            return

                        try:
                            if os.path.exists(file_path):
                                os.remove(file_path)
                        except: pass
                        file_path = mute_path

                        with open(file_path, 'rb') as v:
                            t = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None
                            bot.send_video(
                                message.chat.id, v, 
                                caption=caption, parse_mode="HTML",
                                # No buttons for mute video
                                timeout=500, supports_streaming=True,
                                thumb=t
                            )
                            if t:
                                t.close()
                    else:
                        with open(file_path, 'rb') as v:
                            t = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None
                            bot.send_video(
                                message.chat.id, v, 
                                caption=caption, parse_mode="HTML", 
                                reply_markup=video_markup(sid, uid), 
                                timeout=500, supports_streaming=True,
                                thumb=t
                            )
                            if t:
                                t.close()
            
                    upload_event.set()
                    upload_thread.join(timeout=2)
            
                    delayed_delete(file_path, delay=600)
                    if thumb_path:
                        delayed_delete(thumb_path, delay=600)
                    updated_downloads = update_download_stats()
                    if updated_downloads:
                         # نحتاج طريقة لتحديث المتغير العام في loader إذا لزم الأمر
                         pass
            
                    if loader.REPORT_LOGS and uid != ADMIN_ID: 
                        send_download_report(uid, message.text, file_size_mb, video_title, platform, sid)
            
                    # تسجيل في قاعدة البيانات
                    log_download(uid, message.text, "success", size_mb=file_size_mb, platform=platform, title=video_title, sid=sid, error_reason="")

            else:
                raise Exception("File empty or not found")

        except Exception as e:
            logger.error(f"DL Error {uid} ({platform}): {e}")
            upload_event.set()
            _delete_progress_message(message, progress_msg)
            
            er_msg = str(e).lower()
            if "cancelled_by_user" in er_msg or cancel_event.is_set():
                try:
                    file_path = find_downloaded_file(target_dir, sid)
                    if file_path and os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass
                log_download(uid, message.text, "cancelled", platform=platform, sid=sid, error_reason="user_cancelled")
                bot.send_message(message.chat.id, translation_system.get(uid, 'download_cancelled'))
                return

            error_reason, msg = _classify_download_error(uid, er_msg, file_size_mb)

            log_download(
                uid,
                message.text,
                "failed",
                platform=platform,
                sid=sid,
                size_mb=file_size_mb,
                title=video_title,
                error_reason=error_reason
            )
            maybe_report_failure(
                uid,
                message.text,
                platform,
                error_reason,
                sid=sid,
                size_mb=file_size_mb,
                title=video_title
            )
            
            bot.send_message(
                message.chat.id,
                msg,
                parse_mode="HTML",
                reply_markup=get_error_markup(uid)
            )
    
    except Exception as e:
        logger.error(f"Download processing error for user {uid}: {e}")
        try:
            bot.send_message(
                message.chat.id,
                translation_system.get(uid, 'request_processing_failed'),
                reply_markup=get_error_markup(uid)
            )
        except: pass
    finally:
        _release_download_slot(uid)
        try:
            loader.user_requests.pop(uid, None)
        except:
            pass

def process_local_conversion(message, sid, conversion_type):
    """
    Process local conversion (extract audio or mute) for an existing file.
    conversion_type: 'audio' or 'mute'
    """
    uid = message.from_user.id

    if not check_ffmpeg_available():
        bot.send_message(message.chat.id, translation_system.get(uid, 'ffmpeg_missing'), parse_mode="HTML")
        return
    
    # Try to find the original video file
    target_dir = ADMIN_DIR if uid == ADMIN_ID else USERS_DIR
    input_file = find_downloaded_file(target_dir, sid)
    
    if not input_file or not os.path.exists(input_file):
        # File expired or deleted, fallback to full download
        if conversion_type == 'audio':
            process_download(message, 'audio')
        else: # mute
            process_download(message, 'mute')
        return

    # File exists, perform local conversion
    input_ext = os.path.splitext(input_file)[1].lower() or ".mp4"
    if conversion_type == 'audio':
        output_file = os.path.join(target_dir, f"converted_{sid}.mp3")
    else:
        output_file = os.path.join(target_dir, f"converted_{sid}{input_ext}")
    
    msg = bot.send_message(message.chat.id, translation_system.get(uid, "processing"))
    
    try:
        cmd = []
        if conversion_type == 'audio':
            # Extract audio: ffmpeg -i input.mp4 -vn -acodec libmp3lame -q:a 2 output.mp3
            cmd = ['ffmpeg', '-y', '-i', input_file, '-vn', '-acodec', 'libmp3lame', '-q:a', '2', output_file]
        else:
            # Mute video: ffmpeg -i input.mp4 -c copy -an output.mp4
            cmd = ['ffmpeg', '-y', '-i', input_file, '-c', 'copy', '-an', output_file]
            
        start_time = time.time()
        process = subprocess.Popen(cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE)
        stdout, stderr = process.communicate()
        
        if process.returncode != 0:
            logger.error(f"FFmpeg error: {stderr.decode()}")
            raise Exception("Conversion failed")

        output_size = os.path.getsize(output_file) if os.path.exists(output_file) else 0
        if _exceeds_telegram_upload_limit(output_size):
            try:
                bot.delete_message(message.chat.id, msg.message_id)
            except:
                pass
            bot.send_message(
                message.chat.id,
                _build_file_too_large_message(uid, output_size / (1024 * 1024)),
                parse_mode="HTML",
                reply_markup=get_error_markup(uid)
            )
            delayed_delete(output_file)
            return
            
        if conversion_type == 'audio':
            with open(output_file, 'rb') as a:
                bot.send_audio(
                    message.chat.id, a,
                    caption=f"🎵 {translation_system.get(uid, 'audio_success', bot_sig=BOT_SIG)}",
                    parse_mode="HTML"
                )
        else:
            with open(output_file, 'rb') as v:
                bot.send_video(
                    message.chat.id, v,
                    caption=f"🔇 {translation_system.get(uid, 'mute_success', bot_sig=BOT_SIG)}",
                    parse_mode="HTML"
                )
        
        delayed_delete(output_file)
        try: bot.delete_message(message.chat.id, msg.message_id)
        except: pass
            
    except Exception as e:
        logger.error(f"Local conversion error: {e}")
        try: bot.delete_message(message.chat.id, msg.message_id)
        except: pass
        # Fallback to download if local conversion fails
        if conversion_type == 'audio':
            process_download(message, 'audio')
        else:
            process_download(message, 'mute')

def perform_all_broadcast(message):
    uid = message.from_user.id
    stats = {'suc': 0, 'fail': 0, 'processed': 0}

    with loader.state_lock:
        if loader.broadcast_active:
            bot.reply_to(message, "⚠️ هناك إذاعة نشطة بالفعل! يرجى الانتظار حتى تنتهي.")
            return
        loader.broadcast_active = True
    
    st = None
    try:
        st = bot.send_message(message.chat.id, "🚀 جاري بدء الإذاعة...")
        
        markup = types.InlineKeyboardMarkup()
        markup.row(
            types.InlineKeyboardButton("👨‍💻 راسل المطور", url="https://t.me/abulharith_imad"),
            types.InlineKeyboardButton("📢 شارك البوت", url=f"https://t.me/share/url?url=https://t.me/{get_bot_username()}")
        )
        
        header_msg = "📢 <b>إعلان من الإدارة:</b>"
        content_type = message.content_type
        content_data = None
        caption = ""
        
        if content_type == 'text':
            content_data = message.text
        elif content_type in ['photo', 'video', 'document', 'audio']:
            content_data = getattr(message, content_type)[-1].file_id if content_type == 'photo' else getattr(message, content_type).file_id
            caption = message.caption or ''
        else:
            bot.edit_message_text("❌ نوع الوسائط غير مدعوم.", message.chat.id, st.message_id)
            with loader.state_lock: loader.broadcast_active = False
            return

        def send_wrapper(user_id):
            if not loader.broadcast_active: return
            try:
                time.sleep(0.15)
                if content_type == 'text':
                    full_text = f"{header_msg}\n\n\"{content_data}\"\n\n{BOT_SIG}"
                    bot.send_message(int(user_id), full_text, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'photo':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{BOT_SIG}" if caption else f"{header_msg}\n\n{BOT_SIG}"
                    bot.send_photo(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'video':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{BOT_SIG}" if caption else f"{header_msg}\n\n{BOT_SIG}"
                    bot.send_video(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'document':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{BOT_SIG}" if caption else f"{header_msg}\n\n{BOT_SIG}"
                    bot.send_document(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'audio':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{BOT_SIG}" if caption else f"{header_msg}\n\n{BOT_SIG}"
                    bot.send_audio(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                stats['suc'] += 1
            except telebot.apihelper.ApiTelegramException as e:
                stats['fail'] += 1
                if e.error_code in [403, 400]:
                    try: delete_user(user_id)
                    except: pass
            except Exception:
                stats['fail'] += 1
            stats['processed'] += 1

        def user_generator():
            with sqlite3.connect(DB_FILE, timeout=30) as conn:
                try:
                    conn.execute("PRAGMA busy_timeout = 30000;")
                except Exception:
                    pass
                cursor = conn.cursor()
                cursor.execute('SELECT user_id FROM users WHERE is_banned=0')
                while True:
                    batch = cursor.fetchmany(1000)
                    if not batch: break
                    for row in batch:
                        yield row[0]

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            total_estimate = 0
            try:
                with sqlite3.connect(DB_FILE, timeout=30) as conn:
                    try:
                        conn.execute("PRAGMA busy_timeout = 30000;")
                    except Exception:
                        pass
                    total_estimate = conn.execute('SELECT COUNT(*) FROM users WHERE is_banned=0').fetchone()[0]
            except:
                pass

            start_time = time.time()
            last_update_time = start_time

            for user_id in user_generator():
                if not loader.broadcast_active: 
                    break
                
                future = executor.submit(send_wrapper, user_id)
                futures.append(future)
                
                # Limit pending futures
                if len(futures) > 50:
                    done = [f for f in futures if f.done()]
                    for f in done: futures.remove(f)
                
                # تحديث التقدم كل ثانيتين أو كل 20 مستخدم
                current_time = time.time()
                if (current_time - last_update_time >= 2) or (stats['processed'] > 0 and stats['processed'] % 20 == 0):
                    try:
                        perc = (stats['processed'] / total_estimate * 100) if total_estimate > 0 else 0
                        bar = "▰" * int(perc / 10) + "▱" * (10 - int(perc / 10))
                        
                        # حساب الوقت المتبقي
                        elapsed = current_time - start_time
                        if stats['processed'] > 0:
                            avg_time = elapsed / stats['processed']
                            remaining = (total_estimate - stats['processed']) * avg_time
                            rem_text = f"⏳ المتبقي: {int(remaining)} ثانية"
                        else:
                            rem_text = "⏳ جاري الحساب..."

                        markup_cancel = types.InlineKeyboardMarkup()
                        markup_cancel.add(types.InlineKeyboardButton("❌ إلغاء البث فوراً", callback_data="cancel_broadcast"))

                        bot.edit_message_text(
                            f"🚀 <b>جاري النشر الجماعي...</b>\n\n"
                            f"{bar} {perc:.1f}%\n"
                            f"✅ ناجح: {stats['suc']}\n"
                            f"❌ فاشل: {stats['fail']}\n"
                            f"📊 المعالجة: {stats['processed']}/{total_estimate}\n"
                            f"{rem_text}",
                            message.chat.id, st.message_id, parse_mode="HTML", reply_markup=markup_cancel
                        )
                        last_update_time = current_time
                    except: pass
            
            for f in as_completed(futures): pass
    
    except Exception as e:
        logger.error(f"Broadcast Error: {e}")
        try: bot.send_message(message.chat.id, f"❌ تعذر إكمال الإذاعة بسبب خطأ: {e}")
        except: pass
    
    finally:
        is_cancelled = not loader.broadcast_active
        with loader.state_lock: loader.broadcast_active = False
        
        status_text = "✅ <b>تم الانتهاء!</b>" if not is_cancelled else "⚠️ <b>تم إلغاء البث يدوياً!</b>"
        final_msg = (f"{status_text}\n\n"
                     f"✅ ناجح: {stats['suc']}\n"
                     f"❌ فاشل: {stats['fail']}\n"
                     f"📊 الإجمالي: {stats['processed']}/{total_estimate}")
        
        if st:
            try: bot.edit_message_text(final_msg, message.chat.id, st.message_id, parse_mode="HTML")
            except: bot.send_message(message.chat.id, final_msg, parse_mode="HTML")
        else:
            try: bot.send_message(message.chat.id, final_msg, parse_mode="HTML")
            except: pass

def perform_specific_broadcast(message, target_user_id):
    """تنفيذ إذاعة لمستخدم محدد"""
    if message.text == '/cancel':
        bot.send_message(message.chat.id, "❌ تم الإلغاء")
        return
        
    # التحقق من وجود المستخدم
    from titan_bot.core.database import check_user_exists
    if not check_user_exists(target_user_id):
        bot.reply_to(message, f"❌ المستخدم <code>{target_user_id}</code> غير موجود في قاعدة البيانات.", parse_mode="HTML")
        return

    try:
        content_type = message.content_type
        content_data = None
        caption = message.caption
        
        if content_type == 'text':
            full_text = f"🔔 <b>رسالة من الإدارة:</b>\n\n{message.text}\n\n{BOT_SIG}"
        elif content_type == 'photo':
            content_data = message.photo[-1].file_id
        elif content_type == 'video':
            content_data = message.video.file_id
        elif content_type == 'document':
            content_data = message.document.file_id
        elif content_type == 'audio':
            content_data = message.audio.file_id
            
        markup = types.InlineKeyboardMarkup()
        markup.add(types.InlineKeyboardButton("🗑 إخفاء", callback_data="delete_me"))
        
        header_msg = "🔔 <b>رسالة من الإدارة:</b>"
        
        try:
            if content_type == 'text':
                bot.send_message(int(target_user_id), full_text, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'photo':
                full_caption = f"{header_msg}\n\n{caption}\n\n{BOT_SIG}" if caption else f"{header_msg}\n\n{BOT_SIG}"
                bot.send_photo(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'video':
                full_caption = f"{header_msg}\n\n{caption}\n\n{BOT_SIG}" if caption else f"{header_msg}\n\n{BOT_SIG}"
                bot.send_video(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'document':
                full_caption = f"{header_msg}\n\n{caption}\n\n{BOT_SIG}" if caption else f"{header_msg}\n\n{BOT_SIG}"
                bot.send_document(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'audio':
                full_caption = f"{header_msg}\n\n{caption}\n\n{BOT_SIG}" if caption else f"{header_msg}\n\n{BOT_SIG}"
                bot.send_audio(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                
            bot.reply_to(message, f"✅ تم الإرسال بنجاح للمستخدم: <code>{target_user_id}</code>", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Specific Broadcast Send Error to {target_user_id}: {e}")
            bot.reply_to(message, "❌ تعذر إرسال الرسالة إلى هذا المستخدم. قد يكون المستخدم حظر البوت أو لا يسمح تيليجرام بهذا النوع من الرسائل لهذا الحساب.")
            
    except Exception as e:
        logger.error(f"Specific Broadcast Error: {e}")
        bot.reply_to(message, "❌ تعذر تجهيز رسالة الإذاعة لهذا المستخدم.")
