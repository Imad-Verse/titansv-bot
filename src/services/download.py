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

from src.core.config import Config
from src.core.loader import bot, BotState
from src.utils.ui import get_error_markup
from src.core.utils import (
    logger,
    format_seconds,
    delayed_delete,
    detect_platform_from_url,
    get_cookies_file,
    sanitize_filename,
    generate_sid,
    check_ffmpeg_available,
)
from src.core.database import (
    log_download, 
    update_download_stats, 
    delete_user, 
    get_user_details, 
    log_broadcast_messages_batch, 
    get_broadcast_messages, 
    delete_broadcast_messages_db,
    get_url_by_sid,
    get_total_users_count,
    get_active_user_ids,
    get_cached_media,
    save_to_cache
)
from src.services.translation import translation_system

# --- كلاس تتبع تقدم الرفع (Real Upload Progress Tracker) ---
class ProgressFileReader:
    def __init__(self, filename, callback, *args, **kwargs):
        self.filename = filename
        self.callback = callback
        self.args = args
        self.kwargs = kwargs
        self.size = os.path.getsize(filename)
        self.file = open(filename, 'rb')
        self.read_bytes = 0

    def read(self, size=-1):
        data = self.file.read(size)
        self.read_bytes += len(data)
        if self.callback:
            percent = int((self.read_bytes / self.size) * 100)
            self.callback(percent, *self.args, **self.kwargs)
        return data

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc_val, exc_tb):
        self.close()

    def close(self):
        self.file.close()

    def __getattr__(self, attr):
        return getattr(self.file, attr)

    def __iter__(self):
        return self

    def __next__(self):
        data = self.file.readline()
        if not data:
            raise StopIteration
        self.read_bytes += len(data)
        if self.callback:
            percent = int((self.read_bytes / self.size) * 100)
            self.callback(percent, *self.args, **self.kwargs)
        return data

    def __len__(self):
        return self.size

def upload_progress_callback(percent, msg_id, chat_id, text, last_percent_dict):
    """تحديث شريط التقدم الفعلي أثناء الرفع"""
    if percent - last_percent_dict['value'] >= 10 or percent >= 100:
        if update_progress_message(msg_id, chat_id, text, percent):
            last_percent_dict['value'] = percent

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

# --- removed old queue functions ---


def _start_progress(uid, message, sid, text):
    cancel_event = threading.Event()
    BotState.user_requests[uid] = {'sid': sid, 'cancel_event': cancel_event}
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
            limit_mb=Config.TELEGRAM_UPLOAD_LIMIT_MB,
        )
    return translation_system.get(uid, 'file_too_large_unknown', limit_mb=Config.TELEGRAM_UPLOAD_LIMIT_MB)


def _exceeds_telegram_upload_limit(size_bytes):
    return bool(size_bytes and Config.TELEGRAM_UPLOAD_LIMIT > 0 and size_bytes > Config.TELEGRAM_UPLOAD_LIMIT)


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
    if BotState.username:
        return BotState.username
    try:
        BotState.username = bot.get_me().username
    except Exception:
        BotState.username = ""
    return BotState.username

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
        # Also check for playlist files (video_sid_001.ext)
        pattern_multi = os.path.join(target_dir, f"{prefix}_{sid}_*.*")
        candidates = glob.glob(pattern_multi)
        if not candidates:
            return None
    return max(candidates, key=lambda p: os.path.getmtime(p))

def find_all_downloaded_files(target_dir, sid, prefix="video"):
    """البحث عن جميع الملفات المحملة التابعة لنفس الجلسة (للألبومات)"""
    pattern_single = os.path.join(target_dir, f"{prefix}_{sid}.*")
    pattern_multi = os.path.join(target_dir, f"{prefix}_{sid}_*.*")
    candidates = glob.glob(pattern_single) + glob.glob(pattern_multi)
    # Filter out temp files
    candidates = [c for c in candidates if not c.endswith('.part') and not c.endswith('.ytdl')]
    return sorted(list(set(candidates)))

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

    from src.core.proxy_manager import proxy_manager
    proxy = proxy_manager.get_proxy()
    if proxy:
        ydl_opts['proxy'] = proxy

    platform = detect_platform_from_url(url)
    ffmpeg_available = check_ffmpeg_available()

    # Apply shared defaults
    ydl_opts['noplaylist'] = True
    if platform in ['instagram', 'tiktok']:
        ydl_opts['noplaylist'] = False # السماح بتحميل الألبومات
        
    if platform == 'instagram':
        ydl_opts['extractor_args'] = {
            'instagram': {
                'api_request': 'ios',
                'include_reels': True,
                'include_stories': True
            }
        }
        # Instagram works better with a desktop-like user agent sometimes, but yt-dlp defaults are usually okay.
        # Adding a common user agent to be safe.
        ydl_opts['user_agent'] = 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36'

    # معالجة الجودات الرقمية (Dynamic Quality)
    if str(quality_type).isdigit():
        h = quality_type
        if ffmpeg_available:
            # نحاول دمج أفضل فيديو بهذه الجودة مع أفضل صوت، أو نأخذ ملف واحد بهذه الجودة
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

    # Default format strategy: prefer video + audio merger if ffmpeg is available
    if ffmpeg_available:
        # We prefer high quality merging, but ensure we don't accidentally pick a video-only format if merger fails
        # Format: (Best video + Best audio) OR (Best single file with both) OR (Best single file)
        default_video_format = 'bestvideo+bestaudio/best[vcodec!=none][acodec!=none]/best'
    else:
        # Without ffmpeg, we MUST use a single file format (usually 'best')
        default_video_format = 'best[vcodec!=none][acodec!=none]/best'

    if platform == 'instagram':
        # Instagram often works better with 'best' to get a single mp4 with audio
        # But if ffmpeg is available, we can try to get higher quality if it exists
        ydl_opts['format'] = default_video_format if ffmpeg_available else 'best'
    elif platform == 'tiktok':
        ydl_opts['noplaylist'] = False
    elif platform == 'facebook':
        # Facebook often needs simpler format strings to avoid 'Cannot parse data'
        if quality_type == 'high':
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        elif quality_type == 'medium':
            ydl_opts['format'] = 'bestvideo[height<=720]+bestaudio/best[height<=720]/best'
        elif quality_type == 'low':
            ydl_opts['format'] = 'bestvideo[height<=360]+bestaudio/best[height<=360]/best'
        else:
            ydl_opts['format'] = 'best'
    elif platform == 'youtube':
        # YouTube specific optimizations
        ydl_opts['referer'] = 'https://www.youtube.com/'
        
        if 'shorts' in url.lower():
            # For Shorts, we try to get the best combined format first
            ydl_opts['format'] = 'bestvideo+bestaudio/best'
        elif quality_type == 'high':
             ydl_opts['format'] = default_video_format
        elif quality_type == 'medium':
             ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480][vcodec!=none][acodec!=none]/bestvideo+bestaudio/best'
        elif quality_type == 'low':
             ydl_opts['format'] = 'bestvideo[height<=360]+bestaudio/best[height<=360][vcodec!=none][acodec!=none]/bestvideo+bestaudio/best'
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
            ydl_opts['format'] = default_video_format
        elif quality_type == 'medium':
            ydl_opts['format'] = 'bestvideo[height<=480]+bestaudio/best[height<=480][vcodec!=none][acodec!=none]/bestvideo+bestaudio/best'
        elif quality_type == 'low':
            ydl_opts['format'] = 'bestvideo[height<=360]+bestaudio/best[height<=360][vcodec!=none][acodec!=none]/bestvideo+bestaudio/best'
        ydl_opts['noplaylist'] = True
    
    return ydl_opts

def youtube_safe_download(url, ydl_opts, max_retries=3):
    """تحميل آمن من يوتيوب مع محاولات متعددة واستراتيجية التراجع والبروكسي"""
    from src.core.proxy_manager import proxy_manager
    original_format = ydl_opts.get('format')
    
    for i in range(max_retries):
        try:
            # تدوير البروكسي في كل محاولة (الأولى قد تكون بالبروكسي الحالي أو بدونه)
            if i > 0:
                new_proxy = proxy_manager.get_proxy()
                if new_proxy:
                    logger.info(f"🔄 YouTube Retry {i+1} with new proxy: {new_proxy}")
                    ydl_opts['proxy'] = new_proxy

            # محاولات مع استراتيجيات مختلفة
            if i == 1:
                # المحاولة الثانية: تغيير الصيغة إلى صيغة مدمجة أكثر استقراراً
                logger.info("YouTube Retry 2: Trying stable 'best' format")
                ydl_opts['format'] = 'bestvideo[ext=mp4]+bestaudio[ext=m4a]/best[ext=mp4]/best'
            elif i == 2:
                # المحاولة الثالثة: الخيار النووي - بدون كوكيز وبأقل جودة (أحياناً الكوكيز المحظورة تسبب مشكلة)
                logger.info("YouTube Retry 3: Clearing cookies as last resort")
                if 'cookiefile' in ydl_opts:
                    del ydl_opts['cookiefile']
                ydl_opts['format'] = 'best'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info
        except Exception as e:
            er_msg = str(e).lower()
            logger.warning(f"YouTube Try {i+1} failed: {e}")
            
            if "sign in to confirm" in er_msg or "confirm you're not a bot" in er_msg:
                logger.error("🛑 YouTube bot detection triggered! Cookies might be expired or blocked.")
            
            if i < max_retries - 1:
                time.sleep(i * 3 + 2)
            else:
                raise e
    raise Exception("Youtube download failed after retries")

def enhanced_download_with_fallback(ydl_opts, url, max_retries=3):
    """تحميل محسن مع fallback ومحاولة ببروكسي مختلف أو جودة أقل عند الفشل"""
    from src.core.proxy_manager import proxy_manager
    original_format = ydl_opts.get('format')
    
    for i in range(max_retries):
        try:
            # تدوير البروكسي في المحاولات اللاحقة
            if i > 0:
                new_proxy = proxy_manager.get_proxy()
                if new_proxy:
                    logger.info(f"🔄 Retrying with new proxy: {new_proxy}")
                    ydl_opts['proxy'] = new_proxy
                
                # في المحاولة الثالثة، نجرب جودة "best" المدمجة (أكثر استقراراً أحياناً في بعض المنصات)
                if i == 2:
                    logger.info("Retrying with stable 'best' format fallback")
                    ydl_opts['format'] = 'best[vcodec!=none][acodec!=none]/best'

            with yt_dlp.YoutubeDL(ydl_opts) as ydl:
                info = ydl.extract_info(url, download=True)
                return info
        except Exception as e:
            logger.warning(f"Download Try {i+1} failed: {e}")
            
            # في المحاولة الثانية، نحاول حذف الكوكيز كخيار إضافي
            if i == 0 and 'cookiefile' in ydl_opts:
                logger.info("Retrying without cookies...")
                del ydl_opts['cookiefile']
            
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
        
        bot.send_message(Config.ADMIN_ID, msg, parse_mode="HTML", reply_markup=markup)
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

        bot.send_message(Config.ADMIN_ID, msg, parse_mode="HTML", reply_markup=markup)
    except Exception as e:
        logger.error(f"Failure report error: {e}")
        pass

def extract_media_info(url, cookies_file=None):
    """استخراج معلومات الفيديو والجودات المتوفرة دون تحميل"""
    from src.core.proxy_manager import proxy_manager
    proxy = proxy_manager.get_proxy()
    
    ydl_opts = {
        'quiet': True,
        'no_warnings': True,
        'nocheckcertificate': True,
        'skip_download': True,
        'ignoreerrors': True,
        'proxy': proxy
    }
    if cookies_file:
        ydl_opts['cookiefile'] = str(cookies_file)
    
    try:
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            if not info:
                return None
            
            # استخراج الجودات (للـ YouTube بشكل أساسي)
            formats = info.get('formats', [])
            resolutions = set()
            for f in formats:
                height = f.get('height')
                if height and height >= 144:
                    resolutions.add(height)
            
            # ترتيب الجودات تنازلياً
            sorted_res = sorted(list(resolutions), reverse=True)
            
            # تقليل عدد الخيارات لعدم إرباك المستخدم
            filtered_res = []
            seen_standard = set()
            standards = [2160, 1440, 1080, 720, 480, 360, 240, 144]
            
            for res in sorted_res:
                for std in standards:
                    if res >= std and std not in seen_standard:
                        filtered_res.append(res)
                        seen_standard.add(std)
                        break
            
            return {
                'title': info.get('title'),
                'duration': info.get('duration'),
                'thumbnail': info.get('thumbnail'),
                'resolutions': sorted(filtered_res, reverse=True),
                'is_playlist': 'entries' in info or 'list=' in url or 'playlist' in url,
                'platform': detect_platform_from_url(url),
                'info': info # نمرر الـ info بالكامل لاستخدامه لاحقاً إذا لزم الأمر
            }
    except Exception as e:
        logger.error(f"Info Extraction Error: {e}")
        return None

def maybe_report_failure(user_id, url, platform, reason, sid="", size_mb=0, title=""):
    if BotState.report_logs and user_id != Config.ADMIN_ID:
        send_failure_report(user_id, url, platform, reason, sid=sid, size_mb=size_mb, title=title)

def process_download(message, quality_type, url=None):
    uid = message.from_user.id
    time.sleep(0.5)
    
    # Old slot management removed - QueueManager handles it
    
    progress_msg = None
    
    try:
        sid = sanitize_filename(generate_sid())
        source_url = url if url else message.text
        download_url = source_url
        platform = detect_platform_from_url(source_url)
        
        # --- توحيد الروابط (Normalization) قبل فحص الكاش ---
        if platform == 'tiktok':
            source_url, download_url = prepare_tiktok_urls(source_url)
            if source_url != (url if url else message.text):
                logger.info(f"Expanded TikTok URL: {source_url}")
        
        # --- نظام التخزين المؤقت (Caching) ---
        cached_media = get_cached_media(source_url, quality_type)
        if cached_media:
            try:
                # تجهيز النص المرفق
                caption = _build_video_caption(
                    uid,
                    cached_media['title'],
                    cached_media['description'],
                    cached_media['platform'],
                    cached_media['duration'],
                    f"{cached_media['size_mb']:.2f}",
                    Config.BOT_SIG
                )
                
                # اختيار طريقة الإرسال بناءً على النوع والحجم
                if quality_type == 'audio':
                    bot.send_audio(message.chat.id, cached_media['file_id'], caption=caption, parse_mode="HTML")
                else:
                    # إذا كان النوع فيديو، نتحقق من الحجم لإرساله كفيديو أو ملف
                    if cached_media['size_mb'] > Config.DOCUMENT_THRESHOLD_MB:
                        bot.send_document(message.chat.id, cached_media['file_id'], caption=caption, parse_mode="HTML", reply_markup=video_markup(sid, uid))
                    else:
                        bot.send_video(message.chat.id, cached_media['file_id'], caption=caption, parse_mode="HTML", reply_markup=video_markup(sid, uid), supports_streaming=True)
                
                # تسجيل العملية
                log_download(uid, source_url, "cached_success", size_mb=cached_media['size_mb'], platform=platform, title=cached_media['title'], sid=sid)
                update_download_stats()
                return
            except Exception as e:
                logger.warning(f"Failed to send cached media: {e}")
                # في حال فشل الكاش، نكمل عملية التحميل العادية
        video_title = ""
        file_size_mb = 0
        if platform == 'tiktok':
            if download_url != source_url:
                logger.info(f"Fallback TikTok URL: {download_url}")
        if platform not in Config.ALLOWED_PLATFORMS:
            if platform == 'other':
                msg = translation_system.get(uid, 'invalid_link')
                error_reason = "invalid_link"
            else:
                platforms_text = ", ".join([p.title() for p in Config.ALLOWED_PLATFORMS])
                msg = translation_system.get(uid, 'unsupported_platform', platforms=platforms_text)
                error_reason = "unsupported_platform"

            bot.send_message(
                message.chat.id,
                msg,
                parse_mode="HTML",
                reply_markup=get_error_markup(uid)
            )
            log_download(uid, source_url, "failed", platform=platform, sid=sid, error_reason=error_reason)
            if error_reason != "invalid_link":
                maybe_report_failure(uid, source_url, platform, error_reason, sid=sid)
            return

        if quality_type in ['audio', 'mute'] and not check_ffmpeg_available():
            bot.send_message(message.chat.id, translation_system.get(uid, 'ffmpeg_missing'), parse_mode="HTML", reply_markup=get_error_markup(uid))
            log_download(uid, source_url, "failed", platform=platform, sid=sid, error_reason="ffmpeg_missing")
            maybe_report_failure(uid, source_url, platform, "ffmpeg_missing", sid=sid)
            return

        download_started_text = translation_system.get(uid, 'download_started')
        cancel_event, progress_msg, progress_markup = _start_progress(uid, message, sid, download_started_text)
        target_dir = str(Config.ADMIN_DOWNLOADS if uid == Config.ADMIN_ID else Config.USERS_DOWNLOADS)
        
        if platform in ['instagram', 'tiktok']:
            output_template = os.path.join(target_dir, f"video_{sid}_%(autonumber)03d.%(ext)s")
        else:
            output_template = os.path.join(target_dir, f"video_{sid}.%(ext)s")

        
        cookies_file = get_cookies_file(source_url)
        if cookies_file: cookies_file = str(cookies_file)
        else: cookies_file = None
        
        # --- محاولة الرفع المباشر عبر الرابط (Direct URL Upload) ---
        # توفر هذه الميزة سرعة كبيرة للملفات الصغيرة (أقل من 20MB) لبعض المنصات
        if platform in ['tiktok', 'instagram'] and quality_type not in ['audio', 'mute']:
            try:
                from src.core.proxy_manager import proxy_manager
                proxy = proxy_manager.get_proxy()
                
                # نستخدم إعدادات بسيطة وسريعة للفحص
                with yt_dlp.YoutubeDL({'quiet': True, 'no_warnings': True, 'cookiefile': cookies_file, 'format': 'best', 'proxy': proxy}) as ydl:
                    info = ydl.extract_info(source_url, download=False)
                    direct_url = info.get('url')
                    size = info.get('filesize') or info.get('filesize_approx') or 0
                    
                    if direct_url and 0 < size < (20 * 1024 * 1024):
                        logger.info(f"🚀 Direct URL Upload: {platform} ({size/(1024*1024):.2f}MB)")
                        update_progress_message(progress_msg.message_id, message.chat.id, translation_system.get(uid, 'upload_started'), 50)
                        
                        sent_msg = bot.send_video(
                            message.chat.id, direct_url, 
                            caption=_build_video_caption(uid, info.get('title', ''), "", platform, format_seconds(info.get('duration', 0)), f"{size/(1024*1024):.2f}", Config.BOT_SIG),
                            parse_mode="HTML"
                        )
                        if sent_msg:
                            save_to_cache(source_url, quality_type, sent_msg.video.file_id, title=info.get('title', ''), platform=platform, size_mb=size/(1024*1024))
                            log_download(uid, source_url, "url_upload_success", size_mb=size/(1024*1024), platform=platform, title=info.get('title', ''), sid=sid)
                            _delete_progress_message(message, progress_msg)
                            return
            except Exception as e:
                logger.debug(f"Direct URL Upload skipped: {e}")
                # إذا فشل، نكمل للتحميل العادي دون إزعاج المستخدم
        if not cookies_file: cookies_file = None
        
        download_progress_hook = _build_progress_hook(cancel_event, progress_msg, message.chat.id, download_started_text, progress_markup)
        
        ydl_opts = get_ydl_opts_for_platform(source_url, quality_type, output_template, cookies_file)
        logger.info(f"Download strategy for {platform}: format='{ydl_opts.get('format')}', ffmpeg={'available' if check_ffmpeg_available() else 'missing'}")
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
            log_download(uid, source_url, "failed", platform=platform, sid=sid, size_mb=size_mb, error_reason="file_too_large")
            maybe_report_failure(uid, source_url, platform, "file_too_large", sid=sid, size_mb=size_mb)
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
        
            downloaded_files = find_all_downloaded_files(target_dir, sid)
            
            if not downloaded_files:
                raise Exception("No files downloaded")
                
            # إذا كان هناك أكثر من ملف (ألبوم/منشور متعدد)
            if len(downloaded_files) > 1:
                video_title, video_description = _extract_title_and_description(info, platform)
                duration = format_seconds(info.get('duration', 0))
                total_size_bytes = sum(os.path.getsize(f) for f in downloaded_files)
                total_size_mb = total_size_bytes / (1024 * 1024)
                
                if total_size_bytes > Config.MAX_FILE_SIZE:
                    bot.edit_message_text(
                        _build_file_too_large_message(uid, total_size_mb),
                        message.chat.id, progress_msg.message_id, parse_mode="HTML", reply_markup=get_error_markup(uid)
                    )
                    for f in downloaded_files: delayed_delete(f)
                    return
                
                caption = _build_video_caption(uid, video_title, video_description, platform, duration, f"{total_size_mb:.2f}", Config.BOT_SIG)
                
                update_progress_message(progress_msg.message_id, message.chat.id, translation_system.get(uid, 'upload_started'), 0)
                
                # تقسيم الألبوم إلى مجموعات من 10 (الحد الأقصى لتيليجرام)
                for i in range(0, len(downloaded_files), 10):
                    chunk_files = downloaded_files[i:i+10]
                    media_group = []
                    opened_files = []
                    
                    try:
                        for j, file_path in enumerate(chunk_files):
                            ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                            is_photo = ext in IMAGE_EXTS
                            
                            f = open(file_path, 'rb')
                            opened_files.append(f)
                            
                            # الكابشن يظهر فقط في أول صورة/فيديو في الألبوم الكلي
                            is_first = (i == 0 and j == 0)
                            current_caption = caption if is_first else None
                            
                            if is_photo:
                                media = types.InputMediaPhoto(f, caption=current_caption, parse_mode="HTML")
                            else:
                                media = types.InputMediaVideo(f, caption=current_caption, parse_mode="HTML", supports_streaming=True)
                            media_group.append(media)
                        
                        # محاولة إرسال مجموعة الوسائط مع إعادة المحاولة عند الفشل
                        for retry in range(3):
                            try:
                                # إعادة مؤشر الملف للبداية في كل محاولة إرسال
                                for f in opened_files:
                                    try: f.seek(0)
                                    except: pass
                                    
                                bot.send_media_group(message.chat.id, media_group, timeout=600)
                                break
                            except Exception as e:
                                if retry == 2: raise e
                                logger.warning(f"Media group send retry {retry+1}: {e}")
                                time.sleep(3)
                    finally:
                        # إغلاق الملفات فور الانتهاء من إرسال المجموعة
                        for f in opened_files:
                            try: f.close()
                            except: pass
                    
                    time.sleep(1)
                    
                log_download(uid, source_url, "success", size_mb=total_size_mb, platform=platform, title=video_title, sid=sid)
                update_download_stats()
                
                for f in downloaded_files: delayed_delete(f)
                _delete_progress_message(message, progress_msg)
                return
            
            # معالجة الملف الفردي
            file_path = downloaded_files[0]
            if file_path and os.path.exists(file_path):
                ext = os.path.splitext(file_path)[1].lower().lstrip('.')
                if file_path and os.path.exists(file_path):
                    file_size_bytes = os.path.getsize(file_path)
                else:
                    file_size_bytes = info.get('filesize') or info.get('filesize_approx') or 0
                file_size_mb = file_size_bytes / (1024 * 1024) if file_size_bytes else 0

                video_title, video_description = _extract_title_and_description(info, platform)

                if file_size_bytes > Config.MAX_FILE_SIZE:
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
                        Config.BOT_SIG
                    )

                    last_percent_dict = {'value': 0}
                    upload_text = translation_system.get(uid, 'upload_started', default="🚀 جاري الرفع إلى تيليجرام...")

                    thumb_path = None
                    if quality_type != 'audio':
                        thumb_path = generate_video_thumbnail(file_path, target_dir, sid)
                        if not thumb_path:
                            thumb_path = download_thumbnail(info.get('thumbnail'), target_dir, sid)

                    if ext in IMAGE_EXTS:
                        with ProgressFileReader(file_path, upload_progress_callback, progress_msg.message_id, message.chat.id, upload_text, last_percent_dict) as f:
                            sent_msg = bot.send_photo(
                                message.chat.id, f,
                                caption=caption,
                                parse_mode="HTML"
                            )
                            if sent_msg and sent_msg.photo:
                                save_to_cache(
                                    source_url, quality_type, sent_msg.photo[-1].file_id,
                                    title=video_title, platform=platform, size_mb=file_size_mb,
                                    duration=duration
                                )
                    elif quality_type == 'audio':
                        with ProgressFileReader(file_path, upload_progress_callback, progress_msg.message_id, message.chat.id, upload_text, last_percent_dict) as a:
                            sent_msg = bot.send_audio(
                                message.chat.id, a,
                                caption=f"🎵 <b>{video_title}</b>\n\n{Config.BOT_SIG}",
                                parse_mode="HTML",
                                timeout=500
                            )
                            if sent_msg and sent_msg.audio:
                                save_to_cache(
                                    source_url, quality_type, sent_msg.audio.file_id,
                                    title=video_title, platform=platform, size_mb=file_size_mb,
                                    duration=duration
                                )
                    elif quality_type == 'mute':
                        mute_path = mute_video_file(file_path)
                        if not mute_path or not os.path.exists(mute_path):
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

                        with ProgressFileReader(file_path, upload_progress_callback, progress_msg.message_id, message.chat.id, upload_text, last_percent_dict) as v:
                            t = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None
                            sent_msg = None
                            if file_size_mb > Config.DOCUMENT_THRESHOLD_MB:
                                sent_msg = bot.send_document(
                                    message.chat.id, v,
                                    caption=caption, parse_mode="HTML",
                                    thumb=t, timeout=600
                                )
                                if sent_msg and sent_msg.document:
                                    save_to_cache(
                                        source_url, quality_type, sent_msg.document.file_id,
                                        title=video_title, description=video_description,
                                        platform=platform, size_mb=file_size_mb, duration=duration
                                    )
                            else:
                                sent_msg = bot.send_video(
                                    message.chat.id, v, 
                                    caption=caption, parse_mode="HTML",
                                    timeout=500, supports_streaming=True,
                                    thumb=t
                                )
                                if sent_msg and sent_msg.video:
                                    save_to_cache(
                                        source_url, quality_type, sent_msg.video.file_id,
                                        title=video_title, description=video_description,
                                        platform=platform, size_mb=file_size_mb, duration=duration
                                    )
                            if t:
                                t.close()
                    else:
                        with ProgressFileReader(file_path, upload_progress_callback, progress_msg.message_id, message.chat.id, upload_text, last_percent_dict) as v:
                            t = open(thumb_path, 'rb') if thumb_path and os.path.exists(thumb_path) else None
                            sent_msg = None
                            if file_size_mb > Config.DOCUMENT_THRESHOLD_MB:
                                sent_msg = bot.send_document(
                                    message.chat.id, v,
                                    caption=caption, parse_mode="HTML",
                                    reply_markup=video_markup(sid, uid),
                                    thumb=t, timeout=600
                                )
                                if sent_msg and sent_msg.document:
                                    save_to_cache(
                                        source_url, quality_type, sent_msg.document.file_id,
                                        title=video_title, description=video_description,
                                        platform=platform, size_mb=file_size_mb, duration=duration
                                    )
                            else:
                                sent_msg = bot.send_video(
                                    message.chat.id, v, 
                                    caption=caption, parse_mode="HTML", 
                                    reply_markup=video_markup(sid, uid), 
                                    timeout=500, supports_streaming=True,
                                    thumb=t
                                )
                                if sent_msg and sent_msg.video:
                                    save_to_cache(
                                        source_url, quality_type, sent_msg.video.file_id,
                                        title=video_title, description=video_description,
                                        platform=platform, size_mb=file_size_mb, duration=duration
                                    )
                            if t:
                                t.close()
            
                    _delete_progress_message(message, progress_msg)
            
                    delayed_delete(file_path, delay=600)
                    if thumb_path:
                        delayed_delete(thumb_path, delay=600)
                    updated_downloads = update_download_stats()
                    if updated_downloads:
                         # نحتاج طريقة لتحديث المتغير العام في loader إذا لزم الأمر
                         pass
            
                    if BotState.report_logs and uid != Config.ADMIN_ID: 
                        send_download_report(uid, message.text, file_size_mb, video_title, platform, sid)
            
                    # تسجيل في قاعدة البيانات
                    log_download(uid, source_url, "success", size_mb=file_size_mb, platform=platform, title=video_title, sid=sid, error_reason="")

            else:
                raise Exception("File empty or not found")

        except Exception as e:
            logger.error(f"DL Error {uid} ({platform}): {e}")
            _delete_progress_message(message, progress_msg)
            
            er_msg = str(e).lower()
            if "cancelled_by_user" in er_msg or cancel_event.is_set():
                try:
                    file_path = find_downloaded_file(target_dir, sid)
                    if file_path and os.path.exists(file_path):
                        os.remove(file_path)
                except:
                    pass
                log_download(uid, source_url, "cancelled", platform=platform, sid=sid, error_reason="user_cancelled")
                bot.send_message(message.chat.id, translation_system.get(uid, 'download_cancelled'))
                return

            error_reason, msg = _classify_download_error(uid, er_msg, file_size_mb)

            log_download(
                uid,
                source_url,
                "failed",
                platform=platform,
                sid=sid,
                size_mb=file_size_mb,
                title=video_title,
                error_reason=error_reason
            )
            maybe_report_failure(
                uid,
                source_url,
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
        try:
            BotState.user_requests.pop(uid, None)
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
    target_dir = Config.ADMIN_DOWNLOADS if uid == Config.ADMIN_ID else Config.USERS_DOWNLOADS
    input_file = find_downloaded_file(target_dir, sid)
    
    if not input_file or not os.path.exists(input_file):
        # File expired or deleted, fallback to full download
        original_url = get_url_by_sid(sid)
        if original_url:
            if conversion_type == 'audio':
                process_download(message, 'audio', url=original_url)
            else: # mute
                process_download(message, 'mute', url=original_url)
        else:
            bot.send_message(message.chat.id, translation_system.get(uid, 'session_expired'), parse_mode="HTML")
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
        if output_size > Config.MAX_FILE_SIZE:
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
            
        output_size_mb = output_size / (1024 * 1024)
        
        # محاولة جلب معلومات الفيديو من الكاش لإضافتها كبيانات للملف الصوتي
        original_url = get_url_by_sid(sid)
        title = "Audio"
        performer = f"@{get_bot_username()}"
        if original_url:
            # يمكن التحقق من أي جودة لأن العنوان غالبا ثابت
            cached = get_cached_media(original_url, 'dl_high') or get_cached_media(original_url, 'dl_medium') or get_cached_media(original_url, 'dl_low')
            if cached and cached.get('title'):
                title = cached.get('title')[:60] # حد أقصى للتيليجرام
                performer = cached.get('platform', performer).title()

        if conversion_type == 'audio':
            with open(output_file, 'rb') as a:
                bot.send_audio(
                    message.chat.id, a,
                    caption=f"🎵 {translation_system.get(uid, 'audio_success', bot_sig=Config.BOT_SIG)}",
                    parse_mode="HTML",
                    title=title,
                    performer=performer,
                    timeout=500
                )
        else:
            with open(output_file, 'rb') as v:
                if output_size_mb > Config.DOCUMENT_THRESHOLD_MB:
                    bot.send_document(
                        message.chat.id, v,
                        caption=f"🔇 {translation_system.get(uid, 'mute_success', bot_sig=Config.BOT_SIG)}",
                        parse_mode="HTML",
                        timeout=500
                    )
                else:
                    bot.send_video(
                        message.chat.id, v,
                        caption=f"🔇 {translation_system.get(uid, 'mute_success', bot_sig=Config.BOT_SIG)}",
                        parse_mode="HTML",
                        timeout=500
                    )
        
        delayed_delete(output_file)
        try: bot.delete_message(message.chat.id, msg.message_id)
        except: pass
            
    except Exception as e:
        logger.error(f"Local conversion error: {e}")
        try: bot.delete_message(message.chat.id, msg.message_id)
        except: pass
        # Fallback to download if local conversion fails
        original_url = get_url_by_sid(sid)
        if conversion_type == 'audio':
            process_download(message, 'audio', url=original_url)
        else:
            process_download(message, 'mute', url=original_url)

def perform_all_broadcast(message):
    uid = message.from_user.id
    stats = {'suc': 0, 'fail': 0, 'processed': 0}

    with BotState.lock:
        if BotState.is_broadcast_active:
            bot.reply_to(message, "⚠️ هناك إذاعة نشطة بالفعل! يرجى الانتظار حتى تنتهي.")
            return
        BotState.is_broadcast_active = True
    
    st = None
    try:
        broadcast_id = str(int(time.time() * 1000))
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
            with BotState.lock: BotState.is_broadcast_active = False
            return

        def send_wrapper(user_id):
            if not BotState.is_broadcast_active: return
            try:
                time.sleep(0.15)
                msg_obj = None
                if content_type == 'text':
                    full_text = f"{header_msg}\n\n\"{content_data}\"\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_message(int(user_id), full_text, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'photo':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_photo(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'video':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_video(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'document':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_document(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                elif content_type == 'audio':
                    full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                    msg_obj = bot.send_audio(int(user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                stats['suc'] += 1
                return (str(user_id), str(msg_obj.message_id)) if msg_obj else None
            except telebot.apihelper.ApiTelegramException as e:
                stats['fail'] += 1
                if e.error_code in [403, 400]:
                    try: delete_user(user_id)
                    except: pass
            except Exception:
                stats['fail'] += 1
            stats['processed'] += 1

        def user_generator():
            user_ids = get_active_user_ids()
            for user_id in user_ids:
                yield user_id

        with ThreadPoolExecutor(max_workers=4) as executor:
            futures = []
            total_estimate = get_total_users_count()

            start_time = time.time()
            last_update_time = start_time
            batch_data = []

            for user_id in user_generator():
                if not BotState.is_broadcast_active: 
                    break
                
                future = executor.submit(send_wrapper, user_id)
                futures.append(future)
                
                # Limit pending futures and collect results
                if len(futures) > 50:
                    done = [f for f in futures if f.done()]
                    for f in done:
                        try:
                            res = f.result()
                            if res:
                                batch_data.append((broadcast_id, res[0], res[1]))
                        except: pass
                        futures.remove(f)
                    
                    if len(batch_data) >= 200:
                        log_broadcast_messages_batch(batch_data)
                        batch_data.clear()
                
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
            
            for f in as_completed(futures):
                try:
                    res = f.result()
                    if res:
                        batch_data.append((broadcast_id, res[0], res[1]))
                except: pass
                
            if batch_data:
                log_broadcast_messages_batch(batch_data)
    
    except Exception as e:
        logger.error(f"Broadcast Error: {e}")
        try: bot.send_message(message.chat.id, f"❌ تعذر إكمال الإذاعة بسبب خطأ: {e}")
        except: pass
    
    finally:
        is_cancelled = not BotState.is_broadcast_active
        with BotState.lock:
            BotState.is_broadcast_active = False

        markup_final = types.InlineKeyboardMarkup()
        markup_final.row(
            types.InlineKeyboardButton("✏️ تعديل الإذاعة", callback_data=f"edit_broadcast_start|{broadcast_id}"),
            types.InlineKeyboardButton("🗑 حذف الإذاعة", callback_data=f"delete_broadcast|{broadcast_id}")
        )
        
        status_text = "✅ <b>تم الانتهاء!</b>" if not is_cancelled else "⚠️ <b>تم إلغاء البث يدوياً!</b>"
        final_msg = (f"{status_text}\n\n"
                     f"✅ ناجح: {stats['suc']}\n"
                     f"❌ فاشل: {stats['fail']}\n"
                     f"📊 الإجمالي: {stats['processed']}/{total_estimate}")
        
        if st:
            try: bot.edit_message_text(final_msg, message.chat.id, st.message_id, parse_mode="HTML", reply_markup=markup_final)
            except: bot.send_message(message.chat.id, final_msg, parse_mode="HTML", reply_markup=markup_final)
        else:
            try: bot.send_message(message.chat.id, final_msg, parse_mode="HTML", reply_markup=markup_final)
            except: pass

def perform_specific_broadcast(message, target_user_id):
    """تنفيذ إذاعة لمستخدم محدد"""
    if message.text == '/cancel':
        bot.send_message(message.chat.id, "❌ تم الإلغاء")
        return
        
    # التحقق من وجود المستخدم
    from src.core.database import check_user_exists
    if not check_user_exists(target_user_id):
        bot.reply_to(message, f"❌ المستخدم <code>{target_user_id}</code> غير موجود في قاعدة البيانات.", parse_mode="HTML")
        return

    try:
        content_type = message.content_type
        content_data = None
        caption = message.caption
        
        if content_type == 'text':
            full_text = f"🔔 <b>رسالة من الإدارة:</b>\n\n{message.text}\n\n{Config.BOT_SIG}"
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
                full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                bot.send_photo(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'video':
                full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                bot.send_video(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'document':
                full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                bot.send_document(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
            elif content_type == 'audio':
                full_caption = f"{header_msg}\n\n{caption}\n\n{Config.BOT_SIG}" if caption else f"{header_msg}\n\n{Config.BOT_SIG}"
                bot.send_audio(int(target_user_id), content_data, caption=full_caption, parse_mode="HTML", reply_markup=markup)
                
            bot.reply_to(message, f"✅ تم الإرسال بنجاح للمستخدم: <code>{target_user_id}</code>", parse_mode="HTML")
        except Exception as e:
            logger.error(f"Specific Broadcast Send Error to {target_user_id}: {e}")
            bot.reply_to(message, "❌ تعذر إرسال الرسالة إلى هذا المستخدم. قد يكون المستخدم حظر البوت أو لا يسمح تيليجرام بهذا النوع من الرسائل لهذا الحساب.")
            
    except Exception as e:
        logger.error(f"Specific Broadcast Error: {e}")
        bot.reply_to(message, "❌ تعذر تجهيز رسالة الإذاعة لهذا المستخدم.")

def process_playlist(message, sid):
    """استخراج عناصر قائمة التشغيل وإضافتها إلى طابور التحميل بشكل منفصل"""
    from src.core.loader import download_queue, bot
    uid = message.from_user.id
    url = get_url_by_sid(sid)
    if not url:
        bot.send_message(message.chat.id, translation_system.get(uid, 'invalid_link'))
        return

    # إعلام المستخدم ببدء المعالجة
    msg = bot.send_message(message.chat.id, "🔄 جاري جلب بيانات القائمة، يرجى الانتظار...", parse_mode="HTML")
    
    # استخدام yt-dlp لاستخراج القائمة بدون تحميل
    ydl_opts = {
        'quiet': True,
        'extract_flat': True,
        'no_warnings': True,
        'nocheckcertificate': True
    }
    
    try:
        import yt_dlp
        with yt_dlp.YoutubeDL(ydl_opts) as ydl:
            info = ydl.extract_info(url, download=False)
            
        if 'entries' not in info:
            bot.edit_message_text("❌ لم يتم العثور على قائمة تشغيل في هذا الرابط.", message.chat.id, msg.message_id)
            return
            
        entries = list(info['entries'])
        valid_entries = [e for e in entries if e.get('url') or e.get('id')]
        
        if not valid_entries:
            bot.edit_message_text("❌ القائمة فارغة أو غير متاحة.", message.chat.id, msg.message_id)
            return
            
        bot.edit_message_text(f"✅ تم العثور على <b>{len(valid_entries)}</b> فيديو في القائمة.\n⏳ جاري إضافتها إلى طابور التحميل الخاص بك...", message.chat.id, msg.message_id, parse_mode="HTML")
        
        added_count = 0
        for entry in valid_entries:
            video_url = entry.get('url')
            if not video_url and entry.get('id'):
                # Fallback for YouTube if URL is missing
                video_url = f"https://www.youtube.com/watch?v={entry.get('id')}"
            
            if not video_url:
                continue
            
            # محاكاة رسالة جديدة لكل فيديو
            dummy_message = type('DummyMessage', (), {'chat': message.chat, 'from_user': message.from_user, 'message_id': message.message_id, 'text': video_url})()
            
            # إرسال للطابور بجودة افتراضية
            download_queue.submit(uid, message.chat.id, message.message_id, process_download, dummy_message, 'high', url=video_url)
            added_count += 1
            
        bot.send_message(message.chat.id, f"🎉 تم إضافة <b>{added_count}</b> فيديو بنجاح إلى طابور التحميل.\nسيتم إرسالها لك تباعاً.", parse_mode="HTML")
        
    except Exception as e:
        logger.error(f"Playlist Error: {e}")
        bot.edit_message_text(translation_system.get(uid, 'request_processing_failed'), message.chat.id, msg.message_id)
