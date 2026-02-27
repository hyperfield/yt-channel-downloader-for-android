"""Compatibility wrapper for legacy imports."""

from ..core.downloader import DownloadTask, DownloadTask as DownloadThread

__all__ = ["DownloadTask", "DownloadThread"]
