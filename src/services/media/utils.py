import os
import glob
import subprocess
import requests
from src.core.utils import logger, check_ffmpeg_available

def find_downloaded_file(target_dir, sid, preferred_ext=None, prefix="video"):
    if preferred_ext:
        preferred_ext = preferred_ext.lstrip(".")
        preferred = os.path.join(target_dir, f"{prefix}_{sid}.{preferred_ext}")
        if os.path.exists(preferred):
            return preferred

    pattern = os.path.join(target_dir, f"{prefix}_{sid}.*")
    candidates = glob.glob(pattern)
    if not candidates:
        pattern_multi = os.path.join(target_dir, f"{prefix}_{sid}_*.*")
        candidates = glob.glob(pattern_multi)
        if not candidates:
            return None
    return max(candidates, key=lambda p: os.path.getmtime(p))

def find_all_downloaded_files(target_dir, sid, prefix="video"):
    pattern_single = os.path.join(target_dir, f"{prefix}_{sid}.*")
    pattern_multi = os.path.join(target_dir, f"{prefix}_{sid}_*.*")
    candidates = glob.glob(pattern_single) + glob.glob(pattern_multi)
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

def split_large_file(file_path, max_size_mb=1900):
    """تقسيم ملف كبير إلى أجزاء لا تتعدى الحجم المسموح به"""
    if not check_ffmpeg_available():
        return [file_path]
    
    file_size_mb = os.path.getsize(file_path) / (1024 * 1024)
    if file_size_mb <= max_size_mb:
        return [file_path]
    
    logger.info(f"✂️ Splitting large file: {file_path} ({file_size_mb:.2f} MB)")
    
    # الحصول على مدة الفيديو
    try:
        result = subprocess.run(
            ['ffprobe', '-v', 'error', '-show_entries', 'format=duration', '-of', 'default=noprint_wrappers=1:nokey=1', file_path],
            capture_output=True, text=True, check=True
        )
        duration = float(result.stdout.strip())
    except:
        return [file_path]
    
    # حساب عدد الأجزاء
    num_parts = int(file_size_mb / max_size_mb) + 1
    part_duration = duration / num_parts
    
    base, ext = os.path.splitext(file_path)
    parts = []
    
    for i in range(num_parts):
        part_path = f"{base}_part{i+1}{ext}"
        start_time = i * part_duration
        try:
            subprocess.run([
                'ffmpeg', '-y', '-ss', str(start_time), '-t', str(part_duration),
                '-i', file_path, '-c', 'copy', '-map', '0', part_path
            ], check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
            if os.path.exists(part_path):
                parts.append(part_path)
        except Exception as e:
            logger.error(f"Error splitting part {i+1}: {e}")
            
    return parts if parts else [file_path]
