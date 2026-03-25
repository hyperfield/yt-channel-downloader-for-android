import glob
import os
import re
import shutil
import time
import unicodedata
from typing import Any, Callable, Dict, List, Optional, Union

import yt_dlp

from .logger import get_logger
from .quiet_ydl_logger import QuietYDLLogger
from .settings import CoreSettings, coerce_settings
from .utils import get_format_candidates
from ..config.constants import settings_map


logger = get_logger("DownloadTask")
ANSI_ESCAPE_RE = re.compile(r'\x1B(?:[@-Z\\-_]|\[[0-?]*[ -/]*[@-~])')

ProgressCallback = Callable[[Dict[str, Any]], None]
CompletionCallback = Callable[[int], None]
ErrorCallback = Callable[[Dict[str, Any]], None]
CancelCallback = Callable[[], bool]
AuthProvider = Callable[[], Dict[str, Any]]


class DownloadTask:
    """
    Qt-free download worker that emits progress via callbacks.

    Args:
        url (str): The URL of the media to download.
        index (int): Identifier for the download.
        title (str): Title used to name the file.
        settings (CoreSettings | dict | None): Download preferences and proxy config.
        auth_opts (dict | None): Static yt-dlp auth options.
        auth_opts_provider (callable | None): Callback returning auth options.
        proxy_url (str | None): Proxy URL to apply to yt-dlp.
        on_progress (callable | None): Callback receiving progress dicts.
        on_complete (callable | None): Callback receiving index when done.
        on_error (callable | None): Callback receiving error dicts.
        is_cancelled (callable | None): Callback to check for cancellation.
    """

    def __init__(
        self,
        url: str,
        index: int,
        title: str,
        settings: Optional[Union[CoreSettings, Dict[str, Any]]] = None,
        auth_opts: Optional[Dict[str, Any]] = None,
        auth_opts_provider: Optional[AuthProvider] = None,
        proxy_url: Optional[str] = None,
        on_progress: Optional[ProgressCallback] = None,
        on_complete: Optional[CompletionCallback] = None,
        on_error: Optional[ErrorCallback] = None,
        is_cancelled: Optional[CancelCallback] = None,
    ) -> None:
        self.url = url
        self.index = index
        self.title = title
        self.settings = coerce_settings(settings)
        self.auth_opts = auth_opts
        self.auth_opts_provider = auth_opts_provider
        self.proxy_url = proxy_url or self.settings.build_proxy_url()
        self.on_progress = on_progress
        self.on_complete = on_complete
        self.on_error = on_error
        self.is_cancelled = is_cancelled
        self._cancel_requested = False
        self._last_progress = 0.0
        self._last_emitted_progress = -1.0
        self._last_emit_timestamp = 0.0
        self._sanitized_title = self.sanitize_filename(self.title)
        logger.debug("DownloadTask initialised for index %s, URL: %s", index, url)

    def cancel(self) -> None:
        """Signal the running download to halt."""
        self._cancel_requested = True

    def _should_cancel(self) -> bool:
        if self._cancel_requested:
            return True
        if self.is_cancelled and self.is_cancelled():
            return True
        return False

    def run(self) -> None:
        """
        Execute the download process with exception handling.
        Calls progress/error/completion callbacks as appropriate.
        """
        try:
            self._perform_download()
        except yt_dlp.utils.DownloadCancelled:
            self._emit_cancelled_progress()
        except yt_dlp.utils.DownloadError as e:
            logger.exception("Download error for %s: %s", self.url, e)
            self._emit_progress_error(f"Download error: {e}")
        except (ConnectionError, TimeoutError) as e:
            logger.exception("Network error for %s: %s", self.url, e)
            self._emit_progress_error(f"Network error: {e}")
        except Exception as e:  # noqa: BLE001
            logger.exception("Unexpected error for %s: %s", self.url, e)
            self._emit_progress_error(f"Unexpected error: {e}")

    def _perform_download(self) -> None:
        logger.info("Download started for index %s", self.index)
        ydl_opts, auth_opts = self._build_download_options(self._sanitized_title)

        if self.settings.audio_only:
            result_details = self._download_audio_only_flow(ydl_opts)
        else:
            result_details = self._download_video_flow(ydl_opts, auth_opts)

        self._emit_download_details(result_details)

        if self.on_complete:
            self.on_complete(self.index)
        logger.info("Download finished successfully for index %s", self.index)

    def _build_download_options(self, sanitized_title):
        download_directory = self.settings.download_directory
        write_thumbnail = self.settings.download_thumbnail
        output_stem = self._build_output_stem(sanitized_title)
        ydl_opts = {
            'outtmpl': os.path.join(download_directory, f'{output_stem}.%(ext)s'),
            'progress_hooks': [self.dl_hook],
            'writethumbnail': write_thumbnail,
            'quiet': True,
            'no_warnings': True,
            'logger': QuietYDLLogger(),
        }
        if self.settings.ffmpeg_location:
            ydl_opts['ffmpeg_location'] = self.settings.ffmpeg_location
        js_runtimes = self.settings.build_js_runtimes()
        if js_runtimes:
            ydl_opts['js_runtimes'] = js_runtimes

        auth_opts = self._build_auth_options()
        if self.proxy_url:
            auth_opts = dict(auth_opts) if auth_opts else {}
            auth_opts['proxy'] = self.proxy_url
            ydl_opts['proxy'] = self.proxy_url

        if auth_opts:
            ydl_opts.update(auth_opts)

        return ydl_opts, auth_opts

    def _build_output_stem(self, sanitized_title: str) -> str:
        suffix = self._download_quality_suffix()
        if not suffix:
            return sanitized_title
        return f"{sanitized_title}_{suffix}"

    def _download_quality_suffix(self) -> str:
        if self.settings.audio_only:
            _, audio_quality = self._audio_preferences()
            return self._normalize_quality_suffix(audio_quality)

        _, video_quality = self._video_preferences()
        return self._normalize_quality_suffix(video_quality)

    @staticmethod
    def _normalize_quality_suffix(value: Optional[str]) -> str:
        if not value:
            return "best"

        normalized = str(value).strip().lower()
        if normalized in {"best", "bestvideo", "bestaudio"}:
            return "best"

        compact = re.sub(r'[^a-z0-9]+', '', normalized)
        return compact or "best"

    def _build_auth_options(self) -> Dict[str, Any]:
        if self.auth_opts_provider:
            try:
                opts = self.auth_opts_provider() or {}
            except Exception:  # noqa: BLE001
                logger.exception("Auth provider failed; proceeding without auth opts")
                opts = {}
        else:
            opts = dict(self.auth_opts) if self.auth_opts else {}

        if self.settings.ffmpeg_location:
            opts = dict(opts) if opts else {}
            opts.setdefault("ffmpeg_location", self.settings.ffmpeg_location)
        js_runtimes = self.settings.build_js_runtimes()
        if js_runtimes:
            opts = dict(opts) if opts else {}
            opts.setdefault("js_runtimes", js_runtimes)

        return opts

    def _download_audio_only_flow(self, ydl_opts: Dict[str, Any]) -> Dict[str, Any]:
        audio_format, audio_quality = self._audio_preferences()
        requested_quality_label = self._requested_quality_label(audio_quality)
        audio_filter = f"[ext={audio_format}]" if audio_format and audio_format != 'Any' else ''
        if audio_filter:
            ydl_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': audio_format
            }]
        ydl_opts['format'] = f"{audio_quality}{audio_filter}/bestaudio/best"

        primary_opts, planned_details = self._prepare_download_execution(
            ydl_opts,
            requested_quality_label=requested_quality_label,
            media_type="audio",
            ffmpeg_available=self._has_ffmpeg(self.settings.ffmpeg_location),
        )

        try:
            info = self._execute_download(primary_opts)
            return self._collect_download_details(
                info,
                primary_opts,
                requested_quality_label=requested_quality_label,
                media_type="audio",
                ffmpeg_available=self._has_ffmpeg(self.settings.ffmpeg_location),
                planned_details=planned_details,
            )
        except yt_dlp.utils.DownloadError as err:
            return self._download_audio_fallback(
                err,
                ydl_opts,
                audio_format,
                requested_quality_label,
            )

    def _download_audio_fallback(self, err, ydl_opts, audio_format, requested_quality_label):
        err_str = str(err)
        if not any(token in err_str for token in (
            "Requested format is not available",
            "HTTP Error 403",
            "HTTP Error 404",
        )):
            raise err

        fallback_opts = dict(ydl_opts)
        fallback_opts['format'] = 'best'
        postprocessors = fallback_opts.get('postprocessors')
        if not postprocessors:
            preferred_codec = audio_format if audio_format and audio_format != 'Any' else 'mp3'
            fallback_opts['postprocessors'] = [{
                'key': 'FFmpegExtractAudio',
                'preferredcodec': preferred_codec
            }]
        fallback_reason = f"Primary selector failed: {err_str}"
        logger.warning(
            "Audio-only format unavailable for index %s (%s); falling back to progressive best.",
            self.index,
            err_str,
        )
        prepared_fallback_opts, planned_details = self._prepare_download_execution(
            fallback_opts,
            requested_quality_label=requested_quality_label,
            media_type="audio",
            ffmpeg_available=self._has_ffmpeg(self.settings.ffmpeg_location),
            fallback_reason=fallback_reason,
        )
        info = self._execute_download(prepared_fallback_opts)
        return self._collect_download_details(
            info,
            prepared_fallback_opts,
            requested_quality_label=requested_quality_label,
            media_type="audio",
            ffmpeg_available=self._has_ffmpeg(self.settings.ffmpeg_location),
            planned_details=planned_details,
        )

    def _audio_preferences(self):
        audio_format = settings_map['preferred_audio_format'].get(
            self.settings.preferred_audio_format,
            'Any')
        audio_quality = settings_map['preferred_audio_quality'].get(
            self.settings.preferred_audio_quality,
            'bestaudio')
        return audio_format, audio_quality

    def _download_video_flow(self, ydl_opts: Dict[str, Any], auth_opts: Dict[str, Any]) -> Dict[str, Any]:
        video_format, video_quality = self._video_preferences()
        requested_quality_label = self._requested_quality_label(video_quality)
        ydl_opts['format_sort'] = ['hasvid']
        ydl_opts['format_sort_force'] = True
        height_value = self._parse_height(video_quality)
        ffmpeg_available = self._has_ffmpeg(self.settings.ffmpeg_location)

        if ffmpeg_available:
            format_candidates = get_format_candidates(
                self.url,
                video_quality,
                video_format,
                auth_opts,
            )
            if not format_candidates:
                logger.warning(
                    "No exact format candidates for index %s (requested=%s/%s). Will attempt generic fallback.",
                    self.index,
                    video_quality,
                    video_format or 'Any',
                )
            ydl_opts['format_candidates'] = format_candidates
            format_string = self._build_format_selector(format_candidates, height_value, video_format)
        else:
            format_string = self._build_progressive_format_selector(height_value, video_format)
            logger.warning(
                "FFmpeg is unavailable for index %s; using progressive-only selector %s",
                self.index,
                format_string,
            )

        primary_opts = dict(ydl_opts)
        primary_opts['format'] = format_string
        logger.debug("Format selector for index %s: %s", self.index, format_string)
        prepared_primary_opts, planned_details = self._prepare_download_execution(
            primary_opts,
            requested_quality_label=requested_quality_label,
            media_type="video",
            ffmpeg_available=ffmpeg_available,
            fallback_reason=(
                "Bundled FFmpeg unavailable; using progressive-only selector."
                if not ffmpeg_available
                else ""
            ),
        )

        try:
            info = self._execute_download(prepared_primary_opts)
            return self._collect_download_details(
                info,
                prepared_primary_opts,
                requested_quality_label=requested_quality_label,
                media_type="video",
                ffmpeg_available=ffmpeg_available,
                planned_details=planned_details,
            )
        except yt_dlp.utils.DownloadError as err:
            return self._download_video_fallback(
                err,
                ydl_opts,
                height_value,
                video_format,
                requested_quality_label=requested_quality_label,
                ffmpeg_available=ffmpeg_available,
                already_progressive_only=not ffmpeg_available,
            )

    def _download_video_fallback(
        self,
        err,
        ydl_opts,
        height,
        file_ext,
        requested_quality_label,
        ffmpeg_available,
        already_progressive_only=False,
    ):
        err_str = str(err)
        if not any(token in err_str for token in (
            "Requested format is not available",
            "HTTP Error 403",
            "ffmpeg",
            "ffprobe",
            "incompatible formats",
        )):
            raise err

        fallback_opts = dict(ydl_opts)
        fallback_opts.pop('postprocessors', None)
        if already_progressive_only:
            fallback_opts['format'] = 'best'
        else:
            fallback_opts['format'] = self._build_progressive_format_selector(height, file_ext)
        fallback_reason = f"Primary selector failed: {err_str}"
        logger.warning(
            "Preferred format unavailable for index %s (%s); falling back to %s.",
            self.index,
            err_str,
            fallback_opts['format'],
        )
        prepared_fallback_opts, planned_details = self._prepare_download_execution(
            fallback_opts,
            requested_quality_label=requested_quality_label,
            media_type="video",
            ffmpeg_available=ffmpeg_available,
            fallback_reason=fallback_reason,
        )
        info = self._execute_download(prepared_fallback_opts)
        return self._collect_download_details(
            info,
            prepared_fallback_opts,
            requested_quality_label=requested_quality_label,
            media_type="video",
            ffmpeg_available=ffmpeg_available,
            planned_details=planned_details,
        )

    def _video_preferences(self):
        video_format = settings_map['preferred_video_format'].get(
            self.settings.preferred_video_format, 'Any')
        video_quality = settings_map['preferred_video_quality'].get(
            self.settings.preferred_video_quality,
            'Any')
        if video_format == 'Any':
            video_format = None
        if video_quality in ('Any', None):
            video_quality = 'bestvideo'
        return video_format, video_quality

    @staticmethod
    def _parse_height(video_quality):
        if not video_quality or video_quality == 'bestvideo':
            return None
        digits = ''.join(filter(str.isdigit, video_quality))
        if not digits:
            return None
        try:
            return int(digits)
        except ValueError:
            return None

    def _emit_cancelled_progress(self):
        payload = {
            "index": str(self.index),
            "error": "Cancelled",
            "progress": self._last_progress,
            "speed": "N/A",
        }
        if self.on_progress:
            self.on_progress(payload)
        logger.info("Download cancelled for index %s", self.index)

    def _emit_progress_error(self, message: str):
        payload = {
            "index": str(self.index),
            "error": message,
            "speed": "N/A",
        }
        if self.on_error:
            self.on_error(payload)
        elif self.on_progress:
            self.on_progress(payload)

    def _build_format_selector(self, candidates, height, file_ext):
        selectors = []
        for fmt in candidates:
            selectors.append(f"{fmt}+bestaudio")
        if height:
            selectors.append(f"bestvideo[height<={height}]+bestaudio")
            selectors.append(f"bestvideo[height<={height}]")
        if file_ext and file_ext != 'Any':
            selectors.append(f"bestvideo[ext={file_ext}]+bestaudio")
            selectors.append(f"bestvideo[ext={file_ext}]")
        selectors.append("bestvideo*+bestaudio/bestvideo*/best")
        seen = set()
        ordered = []
        for item in selectors:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return '/'.join(ordered)

    @staticmethod
    def _build_progressive_format_selector(height, file_ext):
        selectors = []
        if height and file_ext:
            selectors.append(f"best[height<={height}][ext={file_ext}]")
        if height:
            selectors.append(f"best[height<={height}]")
        if file_ext:
            selectors.append(f"best[ext={file_ext}]")
        selectors.append("best")
        seen = set()
        ordered = []
        for item in selectors:
            if item not in seen:
                seen.add(item)
                ordered.append(item)
        return '/'.join(ordered)

    @staticmethod
    def _has_ffmpeg(ffmpeg_location=None):
        if ffmpeg_location:
            candidate_path = os.path.abspath(str(ffmpeg_location))
            if os.path.isdir(candidate_path):
                ffmpeg_path = os.path.join(candidate_path, "ffmpeg")
                ffprobe_path = os.path.join(candidate_path, "ffprobe")
                if not (os.path.isfile(ffmpeg_path) and os.path.isfile(ffprobe_path)):
                    ffmpeg_path = os.path.join(candidate_path, "libffmpeg.so")
                    ffprobe_path = os.path.join(candidate_path, "libffprobe.so")
            else:
                ffmpeg_path = candidate_path
                ffprobe_name = "libffprobe.so" if os.path.basename(candidate_path) == "libffmpeg.so" else "ffprobe"
                ffprobe_path = os.path.join(os.path.dirname(candidate_path), ffprobe_name)
            return os.path.isfile(ffmpeg_path) and os.path.isfile(ffprobe_path)
        return bool(shutil.which("ffmpeg") and shutil.which("ffprobe"))

    def _execute_download(self, options):
        with yt_dlp.YoutubeDL(options) as ydl:
            if self._should_cancel():
                raise yt_dlp.utils.DownloadCancelled("Cancelled by user")
            return ydl.extract_info(self.url, download=True)

    def _prepare_download_execution(
        self,
        options: Dict[str, Any],
        requested_quality_label: str,
        media_type: str,
        ffmpeg_available: bool,
        fallback_reason: str = "",
    ) -> tuple[Dict[str, Any], Dict[str, Any]]:
        prepared = dict(options)
        planned_details = self._probe_download_details(
            prepared,
            requested_quality_label=requested_quality_label,
            media_type=media_type,
            ffmpeg_available=ffmpeg_available,
            fallback_reason=fallback_reason,
        )
        output_suffix = str(planned_details.get("output_suffix") or "").strip()
        if output_suffix:
            prepared["outtmpl"] = os.path.join(
                self.settings.download_directory,
                f"{self._build_output_stem_with_suffix(self._sanitized_title, output_suffix)}.%(ext)s",
            )
            actual_ext = str(planned_details.get("actual_ext") or "").strip()
            if actual_ext:
                planned_details["output_filename"] = (
                    f"{self._build_output_stem_with_suffix(self._sanitized_title, output_suffix)}.{actual_ext}"
                )
                planned_details["diagnostic"] = self._build_diagnostic_message(planned_details)
        return prepared, planned_details

    def _probe_download_details(
        self,
        options: Dict[str, Any],
        requested_quality_label: str,
        media_type: str,
        ffmpeg_available: bool,
        fallback_reason: str = "",
    ) -> Dict[str, Any]:
        details = self._default_download_details(
            requested_quality_label=requested_quality_label,
            media_type=media_type,
            ffmpeg_available=ffmpeg_available,
            fallback_reason=fallback_reason,
            format_selector=str(options.get("format") or ""),
        )
        probe_opts = dict(options)
        probe_opts.pop("progress_hooks", None)
        probe_opts["skip_download"] = True
        probe_opts["simulate"] = True
        try:
            with yt_dlp.YoutubeDL(probe_opts) as ydl:
                info = ydl.extract_info(self.url, download=False)
            probed = self._extract_download_details(
                info,
                requested_quality_label=requested_quality_label,
                media_type=media_type,
                ffmpeg_available=ffmpeg_available,
                fallback_reason=fallback_reason,
                format_selector=str(options.get("format") or ""),
            )
            logger.info("Planned download for index %s: %s", self.index, probed.get("diagnostic") or "")
            return probed
        except Exception as exc:  # noqa: BLE001
            details["diagnostic"] = self._build_diagnostic_message(details, probe_error=str(exc))
            logger.warning("Probe failed for index %s: %s", self.index, exc)
            return details

    def _collect_download_details(
        self,
        info: Dict[str, Any],
        options: Dict[str, Any],
        requested_quality_label: str,
        media_type: str,
        ffmpeg_available: bool,
        planned_details: Optional[Dict[str, Any]] = None,
    ) -> Dict[str, Any]:
        fallback_reason = str((planned_details or {}).get("fallback_reason") or "")
        details = self._extract_download_details(
            info,
            requested_quality_label=requested_quality_label,
            media_type=media_type,
            ffmpeg_available=ffmpeg_available,
            fallback_reason=fallback_reason,
            format_selector=str(options.get("format") or ""),
        )
        current_path = self._extract_output_filepath(info)
        final_path = self._rename_output_to_actual_suffix(current_path, details.get("output_suffix"))
        if final_path:
            details["output_filename"] = os.path.basename(final_path)
        elif current_path:
            details["output_filename"] = os.path.basename(current_path)
        elif planned_details and planned_details.get("output_filename"):
            details["output_filename"] = planned_details["output_filename"]
        details["diagnostic"] = self._build_diagnostic_message(details)
        logger.info("Download outcome for index %s: %s", self.index, details.get("diagnostic") or "")
        return details

    def _extract_download_details(
        self,
        info: Dict[str, Any],
        requested_quality_label: str,
        media_type: str,
        ffmpeg_available: bool,
        fallback_reason: str = "",
        format_selector: str = "",
    ) -> Dict[str, Any]:
        streams = self._candidate_streams(info)
        video_stream = self._pick_video_stream(streams, info)
        audio_stream = self._pick_audio_stream(streams, info)
        selection_mode = "audio_only" if media_type == "audio" else self._selection_mode(streams, video_stream, audio_stream)

        actual_width = self._coerce_optional_int(
            (video_stream or {}).get("width") or info.get("width")
        )
        actual_height = self._coerce_optional_int(
            (video_stream or {}).get("height") or info.get("height")
        )
        actual_ext = str(info.get("ext") or (video_stream or {}).get("ext") or "").strip()
        actual_abr = self._coerce_optional_float(
            (audio_stream or {}).get("abr")
            or info.get("abr")
            or (audio_stream or {}).get("tbr")
        )
        actual_quality = self._actual_quality_label(
            media_type=media_type,
            actual_height=actual_height,
            actual_abr=actual_abr,
        )
        output_suffix = self._normalize_quality_suffix(actual_quality)
        format_ids = self._format_ids(streams, info)
        format_summary = self._format_summary(
            format_ids=format_ids,
            selection_mode=selection_mode,
            actual_width=actual_width,
            actual_height=actual_height,
            actual_ext=actual_ext,
        )
        warning = self._quality_warning(
            requested_quality_label=requested_quality_label,
            actual_quality=actual_quality,
            actual_height=actual_height,
            media_type=media_type,
            ffmpeg_available=ffmpeg_available,
            fallback_reason=fallback_reason,
        )
        details = {
            "requested_quality": requested_quality_label,
            "actual_quality": actual_quality,
            "actual_width": actual_width,
            "actual_height": actual_height,
            "actual_ext": actual_ext,
            "output_suffix": output_suffix,
            "format_summary": format_summary,
            "warning": warning,
            "fallback_reason": fallback_reason,
            "ffmpeg_available": ffmpeg_available,
            "selection_mode": selection_mode,
            "format_selector": format_selector,
            "output_filename": "",
        }
        details["diagnostic"] = self._build_diagnostic_message(details)
        return details

    def _default_download_details(
        self,
        requested_quality_label: str,
        media_type: str,
        ffmpeg_available: bool,
        fallback_reason: str,
        format_selector: str,
    ) -> Dict[str, Any]:
        actual_quality = self._requested_quality_label(None) if media_type == "audio" else requested_quality_label
        return {
            "requested_quality": requested_quality_label,
            "actual_quality": actual_quality,
            "actual_width": None,
            "actual_height": None,
            "actual_ext": "",
            "output_suffix": self._normalize_quality_suffix(actual_quality),
            "format_summary": "",
            "warning": "",
            "fallback_reason": fallback_reason,
            "ffmpeg_available": ffmpeg_available,
            "selection_mode": "unknown",
            "format_selector": format_selector,
            "output_filename": "",
            "diagnostic": "",
        }

    def _emit_download_details(self, details: Optional[Dict[str, Any]]) -> None:
        if not details or not self.on_progress:
            return
        payload = {
            "index": str(self.index),
            "progress": self._last_progress,
            "speed": "N/A",
        }
        for key in (
            "requested_quality",
            "actual_quality",
            "actual_width",
            "actual_height",
            "output_filename",
            "format_summary",
            "warning",
            "diagnostic",
            "fallback_reason",
        ):
            value = details.get(key)
            if value is not None and value != "":
                payload[key] = value
        self.on_progress(payload)

    def _requested_quality_label(self, selected_quality: Optional[str]) -> str:
        if self.settings.audio_only:
            return str(self.settings.preferred_audio_quality or selected_quality or "Best available")
        return str(self.settings.preferred_video_quality or selected_quality or "Best available")

    @staticmethod
    def _build_output_stem_with_suffix(sanitized_title: str, suffix: str) -> str:
        normalized_suffix = DownloadTask._normalize_quality_suffix(suffix)
        if not normalized_suffix:
            return sanitized_title
        return f"{sanitized_title}_{normalized_suffix}"

    @staticmethod
    def _coerce_optional_int(value: Any) -> Optional[int]:
        try:
            if value is None or value == "":
                return None
            return int(float(value))
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _coerce_optional_float(value: Any) -> Optional[float]:
        try:
            if value is None or value == "":
                return None
            return float(value)
        except (TypeError, ValueError):
            return None

    @staticmethod
    def _candidate_streams(info: Dict[str, Any]) -> List[Dict[str, Any]]:
        for key in ("requested_formats", "requested_downloads"):
            value = info.get(key)
            if isinstance(value, list) and value:
                return [entry for entry in value if isinstance(entry, dict)]
        return [info] if isinstance(info, dict) else []

    @staticmethod
    def _pick_video_stream(streams: List[Dict[str, Any]], info: Dict[str, Any]) -> Dict[str, Any]:
        for stream in streams:
            vcodec = str(stream.get("vcodec") or "")
            if vcodec and vcodec != "none":
                return stream
            if stream.get("height") or stream.get("width"):
                return stream
        return info if (info.get("height") or info.get("width")) else {}

    @staticmethod
    def _pick_audio_stream(streams: List[Dict[str, Any]], info: Dict[str, Any]) -> Dict[str, Any]:
        for stream in streams:
            acodec = str(stream.get("acodec") or "")
            vcodec = str(stream.get("vcodec") or "")
            if acodec and acodec != "none" and (not vcodec or vcodec == "none"):
                return stream
        return info if info.get("abr") else {}

    @staticmethod
    def _selection_mode(streams: List[Dict[str, Any]], video_stream: Dict[str, Any], audio_stream: Dict[str, Any]) -> str:
        if len(streams) > 1:
            return "adaptive"
        if video_stream and audio_stream and video_stream is not audio_stream:
            return "adaptive"
        return "progressive"

    @staticmethod
    def _format_ids(streams: List[Dict[str, Any]], info: Dict[str, Any]) -> List[str]:
        collected: List[str] = []
        for stream in streams:
            format_id = str(stream.get("format_id") or "").strip()
            if format_id and format_id not in collected:
                collected.append(format_id)
        top_level_format_id = str(info.get("format_id") or "").strip()
        if top_level_format_id and top_level_format_id not in collected:
            collected.append(top_level_format_id)
        return collected

    @staticmethod
    def _format_summary(
        format_ids: List[str],
        selection_mode: str,
        actual_width: Optional[int],
        actual_height: Optional[int],
        actual_ext: str,
    ) -> str:
        parts: List[str] = []
        if format_ids:
            parts.append("+".join(format_ids))
        if actual_width and actual_height:
            parts.append(f"{actual_width}x{actual_height}")
        elif actual_height:
            parts.append(f"{actual_height}p")
        if actual_ext:
            parts.append(actual_ext)
        if selection_mode:
            parts.append(selection_mode)
        return " | ".join(parts)

    def _actual_quality_label(
        self,
        media_type: str,
        actual_height: Optional[int],
        actual_abr: Optional[float],
    ) -> str:
        if media_type == "audio":
            if actual_abr:
                return f"{int(round(actual_abr))}k"
            return "best"
        if actual_height:
            return f"{actual_height}p"
        return "best"

    def _quality_warning(
        self,
        requested_quality_label: str,
        actual_quality: str,
        actual_height: Optional[int],
        media_type: str,
        ffmpeg_available: bool,
        fallback_reason: str,
    ) -> str:
        if media_type != "video":
            return ""

        requested_height = self._parse_height(
            settings_map['preferred_video_quality'].get(
                requested_quality_label,
                requested_quality_label,
            )
        )
        if not requested_height or not actual_height or actual_height >= requested_height:
            return ""

        warning = f"Requested {requested_height}p, got {actual_quality}."
        if fallback_reason:
            return f"{warning} {fallback_reason}"
        if not ffmpeg_available:
            return f"{warning} Bundled FFmpeg unavailable; used progressive-only selection."
        return warning

    def _build_diagnostic_message(self, details: Dict[str, Any], probe_error: str = "") -> str:
        parts: List[str] = []
        requested_quality = str(details.get("requested_quality") or "").strip()
        actual_quality = str(details.get("actual_quality") or "").strip()
        format_summary = str(details.get("format_summary") or "").strip()
        output_filename = str(details.get("output_filename") or "").strip()
        fallback_reason = str(details.get("fallback_reason") or "").strip()
        selector = str(details.get("format_selector") or "").strip()

        if requested_quality:
            parts.append(f"requested={requested_quality}")
        if actual_quality:
            parts.append(f"actual={actual_quality}")
        if format_summary:
            parts.append(f"format={format_summary}")
        parts.append(f"ffmpeg={'yes' if details.get('ffmpeg_available') else 'no'}")
        if output_filename:
            parts.append(f"saved_as={output_filename}")
        if fallback_reason:
            parts.append(f"fallback={fallback_reason}")
        if probe_error:
            parts.append(f"probe_error={probe_error}")
        if selector:
            parts.append(f"selector={selector}")
        return "; ".join(parts)

    def _extract_output_filepath(self, info: Dict[str, Any]) -> Optional[str]:
        for key in ("filepath", "_filename"):
            value = info.get(key)
            if isinstance(value, str) and value:
                return value
        for collection_key in ("requested_downloads", "requested_formats"):
            value = info.get(collection_key)
            if not isinstance(value, list):
                continue
            for entry in value:
                if not isinstance(entry, dict):
                    continue
                for key in ("filepath", "_filename"):
                    path_value = entry.get(key)
                    if isinstance(path_value, str) and path_value:
                        return path_value
        return None

    def _rename_output_to_actual_suffix(self, current_path: Optional[str], output_suffix: Optional[str]) -> Optional[str]:
        if not current_path or not output_suffix:
            return current_path
        if not os.path.isfile(current_path):
            return current_path

        directory = os.path.dirname(current_path)
        _, ext = os.path.splitext(current_path)
        desired_base = self._build_output_stem_with_suffix(self._sanitized_title, str(output_suffix))
        desired_path = os.path.join(directory, f"{desired_base}{ext}")
        if os.path.abspath(current_path) == os.path.abspath(desired_path):
            return current_path

        candidate_path = desired_path
        counter = 2
        while os.path.exists(candidate_path):
            candidate_path = os.path.join(directory, f"{desired_base}_{counter}{ext}")
            counter += 1

        os.replace(current_path, candidate_path)
        return candidate_path

    @staticmethod
    def _format_speed(speed_bytes_per_sec):
        """
        Convert a byte-per-second speed reading into a human-readable string.
        Displays speeds in KB/s for sub-megabyte transfers and in MB/s beyond that.
        """
        if not speed_bytes_per_sec or speed_bytes_per_sec <= 0:
            return "N/A"

        kilobyte_per_sec = speed_bytes_per_sec / 1024
        if kilobyte_per_sec < 1:
            return f"{speed_bytes_per_sec:.0f} B/s"

        if kilobyte_per_sec < 1024:
            return f"{kilobyte_per_sec:.1f} KB/s"

        megabyte_per_sec = kilobyte_per_sec / 1024
        if megabyte_per_sec < 1024:
            return f"{megabyte_per_sec:.2f} MB/s"

        gigabyte_per_sec = megabyte_per_sec / 1024
        return f"{gigabyte_per_sec:.2f} GB/s"

    def dl_hook(self, d):
        """
        Callback function used by yt-dlp to handle download progress updates.

        Args:
            d (dict): A dictionary containing status information about the
            ongoing download.
        """
        if self._should_cancel():
            raise yt_dlp.utils.DownloadCancelled("Cancelled by user")
        if d['status'] == 'downloading':
            progress_str = ANSI_ESCAPE_RE.sub('', d['_percent_str'])
            progress = float(progress_str.strip('%'))
            self._last_progress = progress
            now = time.monotonic()
            should_emit = (
                progress >= 100.0
                or self._last_emitted_progress < 0.0
                or abs(progress - self._last_emitted_progress) >= 1.0
                or (now - self._last_emit_timestamp) >= 0.25
            )
            if should_emit:
                raw_speed = d.get('speed')
                speed_display = self._format_speed(raw_speed)
                self._last_emit_timestamp = now
                self._last_emitted_progress = progress
                if self.on_progress:
                    self.on_progress(
                        {
                            "index": str(self.index),
                            "progress": progress,
                            "speed": speed_display,
                            "speed_bps": raw_speed,
                        }
                    )

    @staticmethod
    def sanitize_filename(filename):
        """
        Sanitizes the filename by removing illegal characters, emoji, hashtags, and
        other symbols unsuitable for file names. Also checks against reserved filenames.

        Args:
            filename (str): The initial filename based on the video title.

        Returns:
            str: A sanitized filename safe for use in file systems.
        """
        # Remove leading and trailing whitespace
        filename = filename.strip()

        # Normalize Unicode characters to decompose accents and remove emojis
        filename = unicodedata.normalize("NFKD", filename)

        # Remove emoji and other non-ASCII characters
        filename = ''.join(c for c in filename if not
                           unicodedata.category(c).startswith("So"))

        # Replace spaces with underscores
        filename = filename.replace(' ', '_')

        # Remove characters that are illegal in Windows filenames and hashtags
        filename = re.sub(r'[\\/*?:"<>|\[\]#]', '', filename)

        filename = filename[:250]

        # Check for Windows reserved filenames and modify if necessary
        reserved_filenames = {
            "CON", "PRN", "AUX", "NUL", "COM1", "COM2", "COM3", "COM4", "COM5",
            "COM6", "COM7", "COM8", "COM9", "LPT1", "LPT2", "LPT3", "LPT4",
            "LPT5", "LPT6", "LPT7", "LPT8", "LPT9"
        }
        if filename.upper() in reserved_filenames:
            filename += "_"

        return filename

    @staticmethod
    def is_download_complete(filepath):
        """
        Checks if the download for a given file is complete by looking for
        temporary `.part` or `.ytdl` files.

        Args:
            filepath (str): The path to the file without the extension.

        Returns:
            bool: True if the download is complete, False otherwise.
        """

        part_files = glob.glob(f"{filepath}*.part")
        ytdl_files = glob.glob(f"{filepath}*.ytdl")

        # If any partially downloaded files are found,
        # the download is incomplete
        if part_files or ytdl_files:
            return False

        matching_files = glob.glob(f"{filepath}.*")

        # Otherwise only completely downloaded files would be found
        if not matching_files:
            return False

        return True
