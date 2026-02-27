from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, Mapping, Optional, Union

from ..config.constants import (
    CHANNEL_FETCH_BATCH_SIZE,
    DEFAULT_AUDIO_FORMAT,
    DEFAULT_AUDIO_QUALITY,
    DEFAULT_CHANNEL_FETCH_LIMIT,
    DEFAULT_PLAYLIST_FETCH_LIMIT,
    DEFAULT_VIDEO_FORMAT,
    DEFAULT_VIDEO_QUALITY,
)
from .proxy import build_proxy_url
from .support_prompt import DEFAULT_SUPPORT_PROMPT_INITIAL_THRESHOLD


def _default_download_directory() -> str:
    return str(Path.home() / "Downloads")


@dataclass(frozen=True)
class CoreSettings:
    download_directory: str = field(default_factory=_default_download_directory)
    preferred_video_format: str = DEFAULT_VIDEO_FORMAT
    preferred_audio_format: str = DEFAULT_AUDIO_FORMAT
    preferred_video_quality: str = DEFAULT_VIDEO_QUALITY
    preferred_audio_quality: str = DEFAULT_AUDIO_QUALITY
    proxy_server_type: str = "None"
    proxy_server_addr: str = ""
    proxy_server_port: str = ""
    download_thumbnail: bool = False
    audio_only: bool = False
    show_thumbnails: bool = True
    downloads_completed: int = 0
    support_prompt_next_at: int = DEFAULT_SUPPORT_PROMPT_INITIAL_THRESHOLD
    support_prompt_last_shown_at: int = 0
    channel_fetch_limit: int = DEFAULT_CHANNEL_FETCH_LIMIT
    playlist_fetch_limit: int = DEFAULT_PLAYLIST_FETCH_LIMIT
    channel_fetch_batch_size: int = CHANNEL_FETCH_BATCH_SIZE

    @classmethod
    def from_dict(
        cls,
        data: Optional[Mapping[str, Any]] = None,
        download_directory: Optional[str] = None,
    ) -> "CoreSettings":
        base_directory = download_directory or _default_download_directory()
        base = cls(download_directory=base_directory)
        if not data:
            return base
        values = base.to_dict()
        for key in values:
            if key in data:
                values[key] = data[key]
        return cls(**values)

    def to_dict(self) -> Dict[str, Any]:
        return {
            "download_directory": self.download_directory,
            "preferred_video_format": self.preferred_video_format,
            "preferred_audio_format": self.preferred_audio_format,
            "preferred_video_quality": self.preferred_video_quality,
            "preferred_audio_quality": self.preferred_audio_quality,
            "proxy_server_type": self.proxy_server_type,
            "proxy_server_addr": self.proxy_server_addr,
            "proxy_server_port": self.proxy_server_port,
            "download_thumbnail": self.download_thumbnail,
            "audio_only": self.audio_only,
            "show_thumbnails": self.show_thumbnails,
            "downloads_completed": self.downloads_completed,
            "support_prompt_next_at": self.support_prompt_next_at,
            "support_prompt_last_shown_at": self.support_prompt_last_shown_at,
            "channel_fetch_limit": self.channel_fetch_limit,
            "playlist_fetch_limit": self.playlist_fetch_limit,
            "channel_fetch_batch_size": self.channel_fetch_batch_size,
        }

    def build_proxy_url(self) -> Optional[str]:
        return build_proxy_url({
            "proxy_server_type": self.proxy_server_type,
            "proxy_server_addr": self.proxy_server_addr,
            "proxy_server_port": self.proxy_server_port,
        })


def coerce_settings(settings: Optional[Union[CoreSettings, Mapping[str, Any]]]) -> CoreSettings:
    if isinstance(settings, CoreSettings):
        return settings
    return CoreSettings.from_dict(settings)
