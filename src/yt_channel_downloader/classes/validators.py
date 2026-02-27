"""Compatibility wrapper for legacy imports."""

from ..core.validators import (
    YouTubeURLValidator,
    extract_single_media,
    is_supported_media_url,
)

__all__ = [
    "YouTubeURLValidator",
    "extract_single_media",
    "is_supported_media_url",
]
