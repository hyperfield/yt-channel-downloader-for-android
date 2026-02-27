from typing import Any, Callable, Dict, Mapping, Optional, Union

from .channel import YTChannel
from .downloader import DownloadTask
from .proxy import build_requests_proxies
from .settings import CoreSettings, coerce_settings


class CoreClient:
    """Facade for core downloader operations."""

    def __init__(
        self,
        settings: Optional[Union[CoreSettings, Mapping[str, Any]]] = None,
        auth_opts: Optional[Dict[str, Any]] = None,
        auth_opts_provider: Optional[Callable[[], Dict[str, Any]]] = None,
        proxy_url: Optional[str] = None,
        requests_proxies: Optional[Dict[str, str]] = None,
    ) -> None:
        self.settings = coerce_settings(settings)
        self.auth_opts = auth_opts
        self.auth_opts_provider = auth_opts_provider
        self.proxy_url = proxy_url or self.settings.build_proxy_url()
        self.requests_proxies = requests_proxies or build_requests_proxies(self.proxy_url)

    def _channel(self, on_error: Optional[Callable[[str], None]] = None) -> YTChannel:
        return YTChannel(
            auth_opts=self.auth_opts,
            auth_opts_provider=self.auth_opts_provider,
            settings=self.settings,
            proxy_url=self.proxy_url,
            requests_proxies=self.requests_proxies,
            on_error=on_error,
        )

    def fetch_video(self, url: str, on_error: Optional[Callable[[str], None]] = None):
        channel = self._channel(on_error=on_error)
        return channel.get_single_video(url)

    def fetch_playlist(
        self,
        playlist_url: str,
        limit: Optional[int] = None,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        channel = self._channel(on_error=on_error)
        return channel.fetch_videos_from_playlist_with_progress(
            playlist_url,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
            limit=limit,
        )

    def fetch_channel(
        self,
        channel_url: str,
        limit: Optional[int] = None,
        batch_size: Optional[int] = None,
        progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
        start_index: int = 1,
        on_error: Optional[Callable[[str], None]] = None,
    ):
        channel = self._channel(on_error=on_error)
        channel_id = channel.get_channel_id(channel_url)
        return channel.fetch_all_videos_in_channel(
            channel_id,
            limit=limit,
            batch_size=batch_size or channel.settings.channel_fetch_batch_size,
            progress_callback=progress_callback,
            is_cancelled=is_cancelled,
            start_index=start_index,
        )

    def create_download_task(
        self,
        url: str,
        index: int,
        title: str,
        settings: Optional[Union[CoreSettings, Mapping[str, Any]]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_complete: Optional[Callable[[int], None]] = None,
        on_error: Optional[Callable[[Dict[str, Any]], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> DownloadTask:
        task_settings = self.settings if settings is None else settings
        return DownloadTask(
            url=url,
            index=index,
            title=title,
            settings=task_settings,
            auth_opts=self.auth_opts,
            auth_opts_provider=self.auth_opts_provider,
            proxy_url=self.proxy_url,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
            is_cancelled=is_cancelled,
        )

    def download(
        self,
        url: str,
        index: int,
        title: str,
        settings: Optional[Union[CoreSettings, Mapping[str, Any]]] = None,
        on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
        on_complete: Optional[Callable[[int], None]] = None,
        on_error: Optional[Callable[[Dict[str, Any]], None]] = None,
        is_cancelled: Optional[Callable[[], bool]] = None,
    ) -> DownloadTask:
        task = self.create_download_task(
            url=url,
            index=index,
            title=title,
            settings=settings,
            on_progress=on_progress,
            on_complete=on_complete,
            on_error=on_error,
            is_cancelled=is_cancelled,
        )
        task.run()
        return task
