import re
from html import escape
from src.core.config import Config
from src.services.translation import translation_system

CAPTION_TEXT_LIMIT = 500
TELEGRAM_CAPTION_LIMIT = 1024

_METRIC_SEGMENT_RE = re.compile(
    r"^\s*(?:"
    r"(?:[\d.,]+[KMBkmb]?\s*(?:views?|likes?|reactions?|comments?|shares?|followers?|following|subscribers?|reposts?|retweets?|bookmarks?|saves?))"
    r"|(?:[\d.,]+\s*(?:مشاهدات|مشاهدة|إعجابات|إعجاب|تفاعلات|تفاعل|تعليقات|تعليق|مشاركات|مشاركة|متابعين|متابع|إعادات نشر|حفظ))"
    r"|(?:[\d.,]+\s*(?:vues?|j'aime|réactions?|reactions?|commentaires?|partages?|abonnés?|enregistrements?))"
    r")\s*$",
    re.IGNORECASE,
)

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

def extract_title_and_description(info, platform):
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

def build_video_caption(uid, title, description, platform, duration, size, bot_sig):
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
