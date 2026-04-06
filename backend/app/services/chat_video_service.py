"""Chat video cache service.

Stores uploaded chat videos on disk so chat requests can reference
local/internal video URLs instead of external public links.
"""

from __future__ import annotations

import base64
import logging
import mimetypes
import re
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile

from app.core.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

_VIDEO_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_VIDEO_URL_PATH_PATTERN = re.compile(r"^/api/chat/videos/([a-f0-9]{32})/?$")
_DEFAULT_VIDEO_MIME = "video/mp4"
_EXT_MIME_MAP: dict[str, str] = {
    "mp4": "video/mp4",
    "mov": "video/quicktime",
    "webm": "video/webm",
    "mkv": "video/x-matroska",
    "m4v": "video/x-m4v",
    "avi": "video/x-msvideo",
}
_MIME_EXT_MAP: dict[str, str] = {
    "video/mp4": "mp4",
    "video/quicktime": "mov",
    "video/webm": "webm",
    "video/x-matroska": "mkv",
    "video/x-m4v": "m4v",
    "video/x-msvideo": "avi",
}


def _cache_dir() -> Path:
    """Resolve and ensure chat video cache directory."""
    configured = Path(settings.CHAT_VIDEO_CACHE_DIR)
    if not configured.is_absolute():
        configured = (BASE_DIR / configured).resolve()
    configured.mkdir(parents=True, exist_ok=True)
    return configured


def _allowed_extensions() -> set[str]:
    values: set[str] = set()
    for item in settings.CHAT_VIDEO_ALLOWED_EXTENSIONS.split(","):
        ext = item.strip().lower().lstrip(".")
        if ext:
            values.add(ext)
    return values


def _validate_video_id(video_id: str) -> str:
    normalized = (video_id or "").strip().lower()
    if not _VIDEO_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="invalid video_id")
    return normalized


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        logger.warning("Failed to delete chat video: %s", path, exc_info=True)


def _cleanup_cache() -> None:
    """Drop expired files and enforce cache max file count."""
    cache_dir = _cache_dir()
    now = time.time()
    ttl = settings.CHAT_VIDEO_CACHE_TTL_SECONDS

    files = sorted(
        (path for path in cache_dir.glob("*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    for path in files:
        age = now - path.stat().st_mtime
        if age > ttl:
            _remove_file(path)

    remaining = sorted(
        (path for path in cache_dir.glob("*") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    overflow = len(remaining) - settings.CHAT_VIDEO_CACHE_MAX_FILES
    if overflow > 0:
        for path in remaining[:overflow]:
            _remove_file(path)


def _guess_extension(file_name: str | None, content_type: str | None) -> str:
    """Infer extension from file name / mime type."""
    allowed = _allowed_extensions()

    if file_name:
        ext = Path(file_name).suffix.lower().lstrip(".")
        if ext in allowed:
            return ext

    normalized_mime = (content_type or "").split(";", 1)[0].strip().lower()
    if normalized_mime in _MIME_EXT_MAP and _MIME_EXT_MAP[normalized_mime] in allowed:
        return _MIME_EXT_MAP[normalized_mime]

    guessed_ext = mimetypes.guess_extension(normalized_mime) if normalized_mime else None
    if guessed_ext:
        ext = guessed_ext.lstrip(".").lower()
        if ext in allowed:
            return ext

    if "mp4" in allowed:
        return "mp4"

    raise HTTPException(
        status_code=400,
        detail=f"Unsupported video format. Allowed: {', '.join(sorted(allowed))}",
    )


def _media_type_for_extension(extension: str) -> str:
    extension = extension.lower().lstrip(".")
    if extension in _EXT_MIME_MAP:
        return _EXT_MIME_MAP[extension]
    guessed, _ = mimetypes.guess_type(f"video.{extension}")
    return guessed or _DEFAULT_VIDEO_MIME


def resolve_chat_video_id_from_url(video_url: str) -> str | None:
    """Resolve cached video_id from local chat video URL if matched."""
    raw = (video_url or "").strip()
    if not raw:
        return None

    if raw.startswith("/"):
        path = raw
    else:
        from urllib.parse import urlparse

        parsed = urlparse(raw)
        if parsed.scheme not in {"http", "https"}:
            return None
        path = parsed.path or ""

    matched = _VIDEO_URL_PATH_PATTERN.fullmatch(path)
    if not matched:
        return None
    return matched.group(1)


async def persist_uploaded_chat_video(file: UploadFile) -> dict[str, int | str]:
    """Validate and cache uploaded chat video file."""
    raw_bytes = await file.read()
    file_name = file.filename or ""
    content_type = file.content_type or ""
    await file.close()

    if not raw_bytes:
        raise HTTPException(status_code=400, detail="video file is empty")

    max_bytes = settings.MAX_CHAT_VIDEO_UPLOAD_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"video file too large ({len(raw_bytes) / 1024 / 1024:.2f}MB), "
                f"limit {settings.MAX_CHAT_VIDEO_UPLOAD_MB}MB"
            ),
        )

    extension = _guess_extension(file_name=file_name, content_type=content_type)
    media_type = _media_type_for_extension(extension)
    video_id = uuid.uuid4().hex
    path = _cache_dir() / f"{video_id}.{extension}"
    path.write_bytes(raw_bytes)
    _cleanup_cache()
    return {
        "video_id": video_id,
        "video_format": extension,
        "media_type": media_type,
        "size_bytes": len(raw_bytes),
        "file_name": file_name,
        "expires_in_seconds": settings.CHAT_VIDEO_CACHE_TTL_SECONDS,
    }


def get_chat_video_file(video_id: str) -> tuple[Path, str]:
    """Resolve cached video path by video_id."""
    normalized_id = _validate_video_id(video_id)
    matches = sorted(_cache_dir().glob(f"{normalized_id}.*"))
    if not matches:
        raise HTTPException(status_code=404, detail="video not found or expired")

    path = matches[0]
    age = time.time() - path.stat().st_mtime
    if age > settings.CHAT_VIDEO_CACHE_TTL_SECONDS:
        _remove_file(path)
        raise HTTPException(status_code=404, detail="video not found or expired")

    extension = path.suffix.lstrip(".")
    return path, _media_type_for_extension(extension)


def resolve_chat_video_data_url(video_id: str) -> str:
    """Read cached video and convert to data URL for vLLM video block."""
    video_path, media_type = get_chat_video_file(video_id)
    raw = video_path.read_bytes()
    if len(raw) > settings.MAX_VIDEO_DATA_URL_BYTES:
        raise HTTPException(
            status_code=413,
            detail=(
                f"video payload too large for inline transport ({len(raw)} bytes), "
                f"limit {settings.MAX_VIDEO_DATA_URL_BYTES} bytes"
            ),
        )
    encoded = base64.b64encode(raw).decode("ascii")
    return f"data:{media_type};base64,{encoded}"
