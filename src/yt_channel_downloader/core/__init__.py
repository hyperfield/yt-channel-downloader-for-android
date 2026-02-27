"""Qt-free core utilities for yt-channel-downloader."""

from .api import CoreClient
from .channel import YTChannel
from .downloader import DownloadTask
from .logger import configure_logging, get_logger, set_logger_factory
from .proxy import build_proxy_url, build_requests_proxies
from .settings import CoreSettings, coerce_settings
from .support_prompt import (
    DEFAULT_SUPPORT_PROMPT_INITIAL_THRESHOLD,
    DEFAULT_SUPPORT_PROMPT_LONG_SNOOZE,
    DEFAULT_SUPPORT_PROMPT_MEDIUM_SNOOZE,
    DEFAULT_SUPPORT_PROMPT_SHORT_SNOOZE,
    SUPPORT_PROMPT_CHOICE_CANNOT_DONATE,
    SUPPORT_PROMPT_CHOICE_NOT_SURE,
    SUPPORT_PROMPT_CHOICE_SUPPORT,
    SupportPrompt,
)
from .validators import (
    YouTubeURLValidator,
    extract_single_media,
    is_supported_media_url,
)

__all__ = [
    "CoreClient",
    "CoreSettings",
    "DownloadTask",
    "YTChannel",
    "build_proxy_url",
    "build_requests_proxies",
    "coerce_settings",
    "configure_logging",
    "DEFAULT_SUPPORT_PROMPT_INITIAL_THRESHOLD",
    "DEFAULT_SUPPORT_PROMPT_LONG_SNOOZE",
    "DEFAULT_SUPPORT_PROMPT_MEDIUM_SNOOZE",
    "DEFAULT_SUPPORT_PROMPT_SHORT_SNOOZE",
    "get_logger",
    "SUPPORT_PROMPT_CHOICE_CANNOT_DONATE",
    "SUPPORT_PROMPT_CHOICE_NOT_SURE",
    "SUPPORT_PROMPT_CHOICE_SUPPORT",
    "set_logger_factory",
    "SupportPrompt",
    "YouTubeURLValidator",
    "extract_single_media",
    "is_supported_media_url",
]
