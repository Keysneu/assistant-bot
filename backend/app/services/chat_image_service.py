"""Chat image cache service.

Stores normalized chat images on disk so stream requests can pass lightweight
`image_id` references instead of large inline base64 payloads.
"""

from __future__ import annotations

import base64
import io
import logging
import re
import time
import uuid
from pathlib import Path

from fastapi import HTTPException, UploadFile
from PIL import Image, ImageOps

from app.core.config import BASE_DIR, settings

logger = logging.getLogger(__name__)

_IMAGE_ID_PATTERN = re.compile(r"^[a-f0-9]{32}$")
_JPEG_EXT = "jpg"
_JPEG_MIME = "image/jpeg"


def _cache_dir() -> Path:
    """Resolve and ensure chat image cache directory."""
    configured = Path(settings.CHAT_IMAGE_CACHE_DIR)
    if not configured.is_absolute():
        configured = (BASE_DIR / configured).resolve()
    configured.mkdir(parents=True, exist_ok=True)
    return configured


def _path_for_id(image_id: str) -> Path:
    return _cache_dir() / f"{image_id}.{_JPEG_EXT}"


def _validate_image_id(image_id: str) -> str:
    normalized = (image_id or "").strip().lower()
    if not _IMAGE_ID_PATTERN.fullmatch(normalized):
        raise HTTPException(status_code=400, detail="invalid image_id")
    return normalized


def _remove_file(path: Path) -> None:
    try:
        path.unlink(missing_ok=True)
    except Exception:
        logger.warning("Failed to delete chat image: %s", path, exc_info=True)


def _cleanup_cache() -> None:
    """Drop expired files and enforce cache max file count."""
    cache_dir = _cache_dir()
    now = time.time()
    ttl = settings.CHAT_IMAGE_CACHE_TTL_SECONDS

    files = sorted(
        (path for path in cache_dir.glob(f"*.{_JPEG_EXT}") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    for path in files:
        age = now - path.stat().st_mtime
        if age > ttl:
            _remove_file(path)

    remaining = sorted(
        (path for path in cache_dir.glob(f"*.{_JPEG_EXT}") if path.is_file()),
        key=lambda path: path.stat().st_mtime,
    )
    overflow = len(remaining) - settings.CHAT_IMAGE_CACHE_MAX_FILES
    if overflow > 0:
        for path in remaining[:overflow]:
            _remove_file(path)


def _encode_jpeg_with_budget(image: Image.Image) -> bytes:
    """Encode image as JPEG while trying to stay under target byte budget."""
    target_bytes = settings.CHAT_IMAGE_TARGET_MAX_BYTES
    quality_steps = [
        settings.CHAT_IMAGE_TARGET_QUALITY,
        76,
        68,
        60,
    ]
    quality_steps = [max(35, min(quality, 95)) for quality in quality_steps]

    working = image
    best = b""
    for _ in range(4):
        for quality in quality_steps:
            buffer = io.BytesIO()
            working.save(buffer, format="JPEG", quality=quality, optimize=True)
            encoded = buffer.getvalue()
            if not best or len(encoded) < len(best):
                best = encoded
            if len(encoded) <= target_bytes:
                return encoded

        longest_edge = max(working.width, working.height)
        if longest_edge <= 640:
            break
        scale = 0.85
        resized = (
            max(1, int(round(working.width * scale))),
            max(1, int(round(working.height * scale))),
        )
        working = working.resize(resized, Image.Resampling.LANCZOS)

    return best


def _normalize_image(raw_bytes: bytes) -> tuple[bytes, int, int]:
    """Decode, rotate, resize, and re-encode image to compact JPEG."""
    try:
        with Image.open(io.BytesIO(raw_bytes)) as source:
            image = ImageOps.exif_transpose(source)
            if image.mode != "RGB":
                image = image.convert("RGB")

            max_edge = settings.CHAT_IMAGE_TARGET_MAX_EDGE
            longest_edge = max(image.width, image.height)
            if longest_edge > max_edge:
                scale = max_edge / float(longest_edge)
                resized = (
                    max(1, int(round(image.width * scale))),
                    max(1, int(round(image.height * scale))),
                )
                image = image.resize(resized, Image.Resampling.LANCZOS)

            encoded = _encode_jpeg_with_budget(image)
            return encoded, image.width, image.height
    except HTTPException:
        raise
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid image payload: {exc}") from exc


def _store_image_bytes(raw_bytes: bytes) -> dict[str, int | str]:
    """Persist normalized bytes and return metadata."""
    normalized_bytes, width, height = _normalize_image(raw_bytes)
    image_id = uuid.uuid4().hex
    path = _path_for_id(image_id)
    path.write_bytes(normalized_bytes)
    _cleanup_cache()
    return {
        "image_id": image_id,
        "image_format": "jpeg",
        "size_bytes": len(normalized_bytes),
        "width": width,
        "height": height,
        "expires_in_seconds": settings.CHAT_IMAGE_CACHE_TTL_SECONDS,
    }


async def persist_uploaded_chat_image(file: UploadFile) -> dict[str, int | str]:
    """Validate and cache uploaded chat image file."""
    raw_bytes = await file.read()
    await file.close()

    if not raw_bytes:
        raise HTTPException(status_code=400, detail="image file is empty")

    max_bytes = settings.MAX_CHAT_IMAGE_UPLOAD_MB * 1024 * 1024
    if len(raw_bytes) > max_bytes:
        raise HTTPException(
            status_code=413,
            detail=(
                f"image file too large ({len(raw_bytes) / 1024 / 1024:.2f}MB), "
                f"limit {settings.MAX_CHAT_IMAGE_UPLOAD_MB}MB"
            ),
        )

    return _store_image_bytes(raw_bytes)


def persist_chat_image_from_base64(image_data: str) -> dict[str, int | str]:
    """Cache legacy inline base64 image and return generated image_id."""
    payload = image_data
    if image_data.startswith("data:image/") and "," in image_data:
        payload = image_data.split(",", 1)[1]
    try:
        raw_bytes = base64.b64decode(payload)
    except Exception as exc:
        raise HTTPException(status_code=400, detail=f"invalid image base64: {exc}") from exc
    return _store_image_bytes(raw_bytes)


def get_chat_image_file(image_id: str) -> tuple[Path, str]:
    """Resolve cached image path by image_id."""
    normalized_id = _validate_image_id(image_id)
    path = _path_for_id(normalized_id)
    if not path.exists():
        raise HTTPException(status_code=404, detail="image not found or expired")

    age = time.time() - path.stat().st_mtime
    if age > settings.CHAT_IMAGE_CACHE_TTL_SECONDS:
        _remove_file(path)
        raise HTTPException(status_code=404, detail="image not found or expired")

    return path, _JPEG_MIME


def resolve_chat_image_payload(
    image_data: str | None,
    image_id: str | None,
) -> tuple[str | None, str | None]:
    """Resolve final image payload for model requests."""
    if image_data:
        return image_data, None

    if image_id:
        image_path, _ = get_chat_image_file(image_id)
        payload = base64.b64encode(image_path.read_bytes()).decode("utf-8")
        return payload, "jpeg"

    return None, None
