import json
import logging
import threading
import time
import uuid
from collections.abc import Mapping as MappingABC
from urllib.parse import parse_qs, urlparse
from typing import Any, Callable, Dict, List, Mapping, Optional

from .api import CoreClient
from .logger import configure_android_logging as _configure_android_logging
from .settings import CoreSettings


def _iter_java_collection(collection: Any):
    """Yield items from Java collection-like objects exposed by Chaquopy."""
    iterator_fn = getattr(collection, "iterator", None)
    if callable(iterator_fn):
        iterator = iterator_fn()
        has_next = getattr(iterator, "hasNext", None)
        next_item = getattr(iterator, "next", None)
        if callable(has_next) and callable(next_item):
            while has_next():
                yield next_item()
            return

    to_array = getattr(collection, "toArray", None)
    if callable(to_array):
        for item in to_array():
            yield item
        return

    # Final fallback for native Python iterables.
    for item in collection:
        yield item


def _as_python_dict(value: Optional[Any], field_name: str) -> Dict[str, Any]:
    """Normalize Python/Java map-like objects into a plain Python dict."""
    if value is None:
        return {}
    if isinstance(value, dict):
        return value
    if isinstance(value, str):
        loaded = json.loads(value)
        if not isinstance(loaded, dict):
            raise ValueError(f"{field_name} JSON must decode to an object")
        return loaded
    if isinstance(value, MappingABC):
        return dict(value)

    # Handle java.util.Map objects passed via Chaquopy (e.g., Kotlin HashMap).
    key_set = getattr(value, "keySet", None)
    get_value = getattr(value, "get", None)
    if callable(key_set) and callable(get_value):
        items: Dict[str, Any] = {}
        for key in _iter_java_collection(key_set()):
            items[key] = get_value(key)
        return items

    entry_set = getattr(value, "entrySet", None)
    if callable(entry_set):
        items: Dict[str, Any] = {}
        for entry in _iter_java_collection(entry_set()):
            items[entry.getKey()] = entry.getValue()
        return items

    try:
        return dict(value)
    except Exception as exc:  # noqa: BLE001
        raise TypeError(f"{field_name} must be a mapping-like object") from exc


def _as_python_list(value: Optional[Any], field_name: str) -> List[Any]:
    """Normalize Python/Java list-like objects into a plain Python list."""
    if value is None:
        return []
    if isinstance(value, list):
        return value
    if isinstance(value, tuple):
        return list(value)
    if isinstance(value, str):
        loaded = json.loads(value)
        if not isinstance(loaded, list):
            raise ValueError(f"{field_name} JSON must decode to an array")
        return loaded

    try:
        return list(_iter_java_collection(value))
    except Exception as exc:  # noqa: BLE001
        raise TypeError(f"{field_name} must be a list-like object") from exc


def _coerce_optional_int(
    value: Optional[Any],
    field_name: str,
    minimum: int = 1,
) -> Optional[int]:
    if value is None:
        return None
    try:
        number = int(value)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{field_name} must be an integer") from exc
    if number < minimum:
        raise ValueError(f"{field_name} must be >= {minimum}")
    return number


_DOWNLOAD_JOBS: Dict[str, Dict[str, Any]] = {}
_DOWNLOAD_JOBS_LOCK = threading.Lock()
_TERMINAL_JOB_STATUSES = {"completed", "completed_with_errors", "error", "cancelled", "missing"}


def _copy_download_job_state(state: Dict[str, Any]) -> Dict[str, Any]:
    copied = dict(state)
    copied["items"] = [dict(item) for item in state.get("items", [])]
    return copied


def _recompute_job_progress_locked(state: Dict[str, Any]) -> None:
    items = state.get("items") or []
    total = len(items)
    state["total_count"] = total
    if total == 0:
        state["completed_count"] = 0
        state["failed_count"] = 0
        state["progress"] = 0.0
        state["error"] = ""
        return

    completed_count = 0
    failed_count = 0
    progress_sum = 0.0
    first_error = ""
    for item in items:
        status = str(item.get("status") or "queued")
        try:
            item_progress = float(item.get("progress") or 0.0)
        except (TypeError, ValueError):
            item_progress = 0.0
        item_progress = min(100.0, max(0.0, item_progress))

        item_error = str(item.get("error") or "").strip()
        if not first_error and item_error:
            first_error = item_error

        if status == "completed":
            completed_count += 1
            item_progress = 100.0
        elif status == "error":
            failed_count += 1

        progress_sum += item_progress

    state["completed_count"] = completed_count
    state["failed_count"] = failed_count
    state["progress"] = progress_sum / total
    if failed_count > 0:
        state["error"] = first_error or str(state.get("error") or "Unknown error")
    elif state.get("status") in {"completed", "starting", "downloading", "queued"}:
        state["error"] = ""


def _is_job_terminal(state: Mapping[str, Any]) -> bool:
    return str(state.get("status") or "") in _TERMINAL_JOB_STATUSES


def _is_job_cancel_requested(job_id: str) -> bool:
    with _DOWNLOAD_JOBS_LOCK:
        state = _DOWNLOAD_JOBS.get(job_id)
        if state is None:
            return False
        return bool(state.get("cancel_requested"))


def _update_download_job(job_id: str, updates: Dict[str, Any]) -> None:
    with _DOWNLOAD_JOBS_LOCK:
        state = _DOWNLOAD_JOBS.get(job_id)
        if state is None:
            return
        state.update(updates)
        _recompute_job_progress_locked(state)


def _read_download_job(job_id: str) -> Dict[str, Any]:
    with _DOWNLOAD_JOBS_LOCK:
        state = _DOWNLOAD_JOBS.get(job_id)
        if state is None:
            return {
                "job_id": job_id,
                "status": "missing",
                "error": "Unknown job id",
                "progress": 0.0,
                "speed": "N/A",
                "cancel_requested": False,
                "total_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "current_item_index": None,
                "current_item_title": "",
                "items": [],
            }
        return _copy_download_job_state(state)


def _update_download_job_item(job_id: str, item_position: int, updates: Dict[str, Any]) -> None:
    with _DOWNLOAD_JOBS_LOCK:
        state = _DOWNLOAD_JOBS.get(job_id)
        if state is None:
            return
        items = state.get("items") or []
        if item_position < 0 or item_position >= len(items):
            return
        items[item_position].update(updates)
        if str(updates.get("status") or "") == "error":
            item_error = str(updates.get("error") or "").strip()
            if item_error:
                state["error"] = item_error
        state["updated_at"] = time.time()
        _recompute_job_progress_locked(state)


def _error_from_payload(payload: Any) -> str:
    if isinstance(payload, MappingABC):
        error_value = payload.get("error")
        if error_value:
            return str(error_value)
    return str(payload) if payload is not None else "Unknown error"


def _job_item_metadata_updates(payload: Any) -> Dict[str, Any]:
    if not isinstance(payload, MappingABC):
        return {}

    updates: Dict[str, Any] = {}
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
        if key in payload and payload.get(key) is not None:
            updates[key] = payload.get(key)
    return updates


def _normalize_download_items(items: Optional[Any]) -> List[Dict[str, Any]]:
    raw_items = _as_python_list(items, "items")
    if not raw_items:
        raise ValueError("items must contain at least one entry")

    normalized_items: List[Dict[str, Any]] = []
    for position, raw_item in enumerate(raw_items):
        item = _as_python_dict(raw_item, f"items[{position}]")
        url = str(item.get("url") or "").strip()
        if not url:
            raise ValueError(f"items[{position}].url is required")

        title = str(item.get("title") or f"Item {position + 1}")
        try:
            item_index = int(item.get("index", position))
        except (TypeError, ValueError) as exc:
            raise ValueError(f"items[{position}].index must be an integer") from exc

        normalized_items.append(
            {
                "index": item_index,
                "title": title,
                "url": url,
                "status": "queued",
                "progress": 0.0,
                "speed": "N/A",
                "error": "",
                "requested_quality": "",
                "actual_quality": "",
                "actual_width": None,
                "actual_height": None,
                "output_filename": "",
                "format_summary": "",
                "warning": "",
                "diagnostic": "",
                "fallback_reason": "",
            }
        )
    return normalized_items


def _infer_url_kind(url: str) -> str:
    parsed = urlparse(url)
    query = parse_qs(parsed.query)
    path = parsed.path.lower()

    if query.get("list"):
        return "playlist"

    if any(token in path for token in ("/channel/", "/@", "/user/", "/c/")):
        return "channel"

    return "video"


def build_settings(settings: Optional[Mapping[str, Any]] = None) -> CoreSettings:
    """Build CoreSettings from a mapping using CoreSettings.from_dict."""
    return CoreSettings.from_dict(_as_python_dict(settings, "settings"))


def build_settings_from_json(payload: str) -> CoreSettings:
    """Build CoreSettings from a JSON string."""
    return CoreSettings.from_dict(_as_python_dict(payload, "settings"))


def configure_android_logging(level: Any = "INFO") -> bool:
    """Enable Python logging to Android Logcat when running under Chaquopy."""
    if isinstance(level, str):
        level_name = level.strip().upper() or "INFO"
        level_value = getattr(logging, level_name, logging.INFO)
    else:
        try:
            level_value = int(level)
        except (TypeError, ValueError):
            level_value = logging.INFO
    return _configure_android_logging(level=level_value)


def create_client(
    settings: Optional[Mapping[str, Any]] = None,
    auth_opts: Optional[Dict[str, Any]] = None,
    auth_opts_provider: Optional[Callable[[], Dict[str, Any]]] = None,
    proxy_url: Optional[str] = None,
) -> CoreClient:
    """Create a CoreClient from settings and optional auth/proxy inputs."""
    normalized_auth_opts = None
    if auth_opts is not None:
        normalized_auth_opts = _as_python_dict(auth_opts, "auth_opts")

    return CoreClient(
        settings=build_settings(settings),
        auth_opts=normalized_auth_opts,
        auth_opts_provider=auth_opts_provider,
        proxy_url=proxy_url,
    )


def fetch_video(url: str, settings: Optional[Mapping[str, Any]] = None):
    client = create_client(settings=settings)
    return client.fetch_video(url)


def fetch_playlist(
    playlist_url: str,
    settings: Optional[Mapping[str, Any]] = None,
    limit: Optional[int] = None,
    progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
):
    client = create_client(settings=settings)
    return client.fetch_playlist(
        playlist_url,
        limit=limit,
        progress_callback=progress_callback,
        is_cancelled=is_cancelled,
    )


def fetch_channel(
    channel_url: str,
    settings: Optional[Mapping[str, Any]] = None,
    limit: Optional[int] = None,
    batch_size: Optional[int] = None,
    progress_callback: Optional[Callable[[int, Optional[int]], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
    start_index: int = 1,
):
    client = create_client(settings=settings)
    return client.fetch_channel(
        channel_url,
        limit=limit,
        batch_size=batch_size,
        progress_callback=progress_callback,
        is_cancelled=is_cancelled,
        start_index=start_index,
    )


def download(
    url: str,
    index: int,
    title: str,
    settings: Optional[Mapping[str, Any]] = None,
    on_progress: Optional[Callable[[Dict[str, Any]], None]] = None,
    on_complete: Optional[Callable[[int], None]] = None,
    on_error: Optional[Callable[[Dict[str, Any]], None]] = None,
    is_cancelled: Optional[Callable[[], bool]] = None,
):
    client = create_client(settings=settings)
    return client.download(
        url=url,
        index=index,
        title=title,
        on_progress=on_progress,
        on_complete=on_complete,
        on_error=on_error,
        is_cancelled=is_cancelled,
    )


def resolve_url(
    url: str,
    settings: Optional[Mapping[str, Any]] = None,
    limit: Optional[int] = None,
    batch_size: Optional[int] = None,
    start_index: int = 1,
) -> Dict[str, Any]:
    normalized_url = str(url or "").strip()
    if not normalized_url:
        raise ValueError("url must not be empty")

    normalized_settings = _as_python_dict(settings, "settings")
    effective_settings = build_settings(normalized_settings)
    client = create_client(settings=normalized_settings)

    safe_limit = _coerce_optional_int(limit, "limit")
    safe_batch_size = _coerce_optional_int(batch_size, "batch_size")
    safe_start_index = _coerce_optional_int(start_index, "start_index") or 1

    playlist_limit = safe_limit if safe_limit is not None else effective_settings.playlist_fetch_limit
    channel_limit = safe_limit if safe_limit is not None else effective_settings.channel_fetch_limit
    channel_batch_size = (
        safe_batch_size
        if safe_batch_size is not None
        else effective_settings.channel_fetch_batch_size
    )

    kind_hint = _infer_url_kind(normalized_url)
    if kind_hint == "playlist":
        candidates = ["playlist", "video", "channel"]
    elif kind_hint == "channel":
        candidates = ["channel", "video", "playlist"]
    else:
        candidates = ["video"]

    attempt_errors: List[str] = []
    for kind in candidates:
        try:
            if kind == "video":
                items = client.fetch_video(normalized_url)
            elif kind == "playlist":
                items = client.fetch_playlist(
                    normalized_url,
                    limit=playlist_limit,
                )
            else:
                items = client.fetch_channel(
                    normalized_url,
                    limit=channel_limit,
                    batch_size=channel_batch_size,
                    start_index=safe_start_index,
                )

            normalized_items = list(items or [])
            if not normalized_items:
                attempt_errors.append(f"{kind}: empty result")
                continue

            canonical_url = normalized_url
            first_item = normalized_items[0]
            if isinstance(first_item, MappingABC):
                first_item_url = first_item.get("url")
                if first_item_url:
                    canonical_url = str(first_item_url)

            return {
                "ok": True,
                "kind": kind,
                "kind_hint": kind_hint,
                "input_url": normalized_url,
                "normalized_url": canonical_url,
                "count": len(normalized_items),
                "items": normalized_items,
                "error": "",
            }
        except Exception as exc:  # noqa: BLE001
            attempt_errors.append(f"{kind}: {exc}")

    error_message = "; ".join(attempt_errors) if attempt_errors else "Unable to resolve URL"
    return {
        "ok": False,
        "kind": "unknown",
        "kind_hint": kind_hint,
        "input_url": normalized_url,
        "normalized_url": normalized_url,
        "count": 0,
        "items": [],
        "error": error_message,
    }


def resolve_url_json(
    url: str,
    settings: Optional[Mapping[str, Any]] = None,
    limit: Optional[int] = None,
    batch_size: Optional[int] = None,
    start_index: int = 1,
) -> str:
    return json.dumps(
        resolve_url(
            url=url,
            settings=settings,
            limit=limit,
            batch_size=batch_size,
            start_index=start_index,
        )
    )


def start_batch_download(
    items: Optional[Any],
    settings: Optional[Mapping[str, Any]] = None,
) -> str:
    normalized_items = _normalize_download_items(items)
    normalized_settings = _as_python_dict(settings, "settings")

    job_id = str(uuid.uuid4())
    now = time.time()
    initial_state = {
        "job_id": job_id,
        "status": "queued",
        "progress": 0.0,
        "speed": "N/A",
        "error": "",
        "cancel_requested": False,
        "total_count": len(normalized_items),
        "completed_count": 0,
        "failed_count": 0,
        "current_item_index": None,
        "current_item_title": "",
        "items": normalized_items,
        "created_at": now,
        "updated_at": now,
    }
    with _DOWNLOAD_JOBS_LOCK:
        _DOWNLOAD_JOBS[job_id] = initial_state
        _recompute_job_progress_locked(initial_state)

    def runner() -> None:
        try:
            _update_download_job(job_id, {"status": "starting", "updated_at": time.time()})
            for item_position, item in enumerate(normalized_items):
                if _is_job_cancel_requested(job_id):
                    _update_download_job(
                        job_id,
                        {
                            "status": "cancelled",
                            "speed": "N/A",
                            "updated_at": time.time(),
                        },
                    )
                    _update_download_job_item(
                        job_id,
                        item_position,
                        {
                            "status": "cancelled",
                            "speed": "N/A",
                            "error": "Cancelled",
                        },
                    )
                    return

                _update_download_job(
                    job_id,
                    {
                        "status": "downloading",
                        "current_item_index": item_position,
                        "current_item_title": item["title"],
                        "speed": "N/A",
                        "updated_at": time.time(),
                    },
                )
                _update_download_job_item(
                    job_id,
                    item_position,
                    {
                        "status": "starting",
                        "progress": 0.0,
                        "speed": "N/A",
                        "error": "",
                    },
                )

                def is_cancelled() -> bool:
                    return _is_job_cancel_requested(job_id)

                def on_progress(payload: Dict[str, Any]) -> None:
                    if not isinstance(payload, MappingABC):
                        return

                    if payload.get("error"):
                        error_message = _error_from_payload(payload)
                        status = "cancelled" if _is_job_cancel_requested(job_id) else "error"
                        _update_download_job_item(
                            job_id,
                            item_position,
                            {
                                "status": status,
                                "error": error_message,
                                "speed": "N/A",
                            },
                        )
                        return

                    updates: Dict[str, Any] = {
                        "status": "downloading",
                        "error": "",
                    }
                    progress_value = payload.get("progress")
                    speed_value = payload.get("speed")
                    if progress_value is not None:
                        try:
                            updates["progress"] = float(progress_value)
                        except (TypeError, ValueError):
                            pass
                    if speed_value is not None:
                        updates["speed"] = str(speed_value)
                    updates.update(_job_item_metadata_updates(payload))

                    _update_download_job_item(job_id, item_position, updates)
                    _update_download_job(
                        job_id,
                        {
                            "status": "downloading",
                            "speed": str(updates.get("speed", "N/A")),
                            "updated_at": time.time(),
                        },
                    )

                def on_complete(_index: int) -> None:
                    _update_download_job_item(
                        job_id,
                        item_position,
                        {
                            "status": "completed",
                            "progress": 100.0,
                            "speed": "N/A",
                            "error": "",
                        },
                    )

                def on_error(payload: Dict[str, Any]) -> None:
                    error_message = _error_from_payload(payload)
                    status = "cancelled" if _is_job_cancel_requested(job_id) else "error"
                    updates = {
                        "status": status,
                        "error": error_message,
                        "speed": "N/A",
                    }
                    updates.update(_job_item_metadata_updates(payload))
                    _update_download_job_item(
                        job_id,
                        item_position,
                        updates,
                    )

                download(
                    url=item["url"],
                    index=int(item["index"]),
                    title=item["title"],
                    settings=normalized_settings,
                    on_progress=on_progress,
                    on_complete=on_complete,
                    on_error=on_error,
                    is_cancelled=is_cancelled,
                )

                job_snapshot = _read_download_job(job_id)
                job_items = job_snapshot.get("items", [])
                if item_position < len(job_items):
                    current_item = job_items[item_position]
                    if str(current_item.get("status")) in {"queued", "starting", "downloading"}:
                        item_status = "cancelled" if _is_job_cancel_requested(job_id) else "completed"
                        _update_download_job_item(
                            job_id,
                            item_position,
                            {
                                "status": item_status,
                                "progress": 100.0 if item_status == "completed" else current_item.get("progress", 0.0),
                                "speed": "N/A",
                                "error": "Cancelled" if item_status == "cancelled" else "",
                            },
                        )

                if _is_job_cancel_requested(job_id):
                    _update_download_job(
                        job_id,
                        {
                            "status": "cancelled",
                            "speed": "N/A",
                            "updated_at": time.time(),
                        },
                    )
                    return

            final_state = _read_download_job(job_id)
            failed_count = int(final_state.get("failed_count") or 0)
            completed_count = int(final_state.get("completed_count") or 0)
            total_count = int(final_state.get("total_count") or 0)
            if failed_count and completed_count:
                final_status = "completed_with_errors"
            elif failed_count and completed_count == 0 and total_count > 0:
                final_status = "error"
            else:
                final_status = "completed"

            updates: Dict[str, Any] = {
                "status": final_status,
                "speed": "N/A",
                "updated_at": time.time(),
            }
            if final_status == "completed":
                updates["progress"] = 100.0
                updates["error"] = ""
            elif final_status == "error":
                updates["error"] = str(final_state.get("error") or "All download items failed.")
            elif final_status == "completed_with_errors":
                updates["error"] = str(final_state.get("error") or "One or more items failed.")
            _update_download_job(job_id, updates)
        except Exception as exc:  # noqa: BLE001
            _update_download_job(
                job_id,
                {
                    "status": "error",
                    "error": str(exc),
                    "speed": "N/A",
                    "updated_at": time.time(),
                },
            )

    thread = threading.Thread(target=runner, daemon=True, name=f"download-job-{job_id}")
    thread.start()
    return job_id


def start_download_job(
    url: str,
    title: str,
    settings: Optional[Mapping[str, Any]] = None,
    index: int = 0,
) -> str:
    return start_batch_download(
        items=[{"url": url, "title": title, "index": int(index)}],
        settings=settings,
    )


def cancel_download_job(job_id: str) -> Dict[str, Any]:
    with _DOWNLOAD_JOBS_LOCK:
        state = _DOWNLOAD_JOBS.get(job_id)
        if state is None:
            return {
                "job_id": job_id,
                "status": "missing",
                "error": "Unknown job id",
                "progress": 0.0,
                "speed": "N/A",
                "cancel_requested": False,
                "total_count": 0,
                "completed_count": 0,
                "failed_count": 0,
                "current_item_index": None,
                "current_item_title": "",
                "items": [],
            }
        if not _is_job_terminal(state):
            state["cancel_requested"] = True
            state["status"] = "cancelling"
            state["updated_at"] = time.time()
        return _copy_download_job_state(state)


def get_job_state(job_id: str) -> Dict[str, Any]:
    return _read_download_job(job_id)


def get_job_state_json(job_id: str) -> str:
    return json.dumps(_read_download_job(job_id))


def get_download_job(job_id: str) -> Dict[str, Any]:
    return get_job_state(job_id)


def get_download_job_json(job_id: str) -> str:
    return get_job_state_json(job_id)
