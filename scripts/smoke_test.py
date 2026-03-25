#!/usr/bin/env python3
import argparse
import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "src"))

from yt_channel_downloader.core import CoreClient, CoreSettings
from yt_channel_downloader.core.validators import YouTubeURLValidator


def _load_json(path: str):
    try:
        with open(path, "r", encoding="utf-8") as handle:
            return json.load(handle)
    except FileNotFoundError:
        raise SystemExit(f"settings file not found: {path}")
    except json.JSONDecodeError as exc:
        raise SystemExit(f"invalid json in {path}: {exc}")


def _build_settings(args):
    settings = {
        "download_directory": str(args.download_dir),
        "download_thumbnail": bool(args.download_thumbnail),
        "audio_only": bool(args.audio_only),
        "proxy_server_type": "None",
        "proxy_server_addr": "",
        "proxy_server_port": "",
    }
    if args.settings_json:
        settings.update(_load_json(args.settings_json))
    return CoreSettings.from_dict(settings)


def _build_auth_opts(args):
    if not args.auth_json:
        return None
    return _load_json(args.auth_json)


def _print_item_preview(items, label):
    if not items:
        print(f"[{label}] no items")
        return
    first = items[0]
    title = first.get("title") if isinstance(first, dict) else None
    url = first.get("url") if isinstance(first, dict) else None
    duration = first.get("duration") if isinstance(first, dict) else None
    print(f"[{label}] {len(items)} items")
    if title or url:
        print(f"[{label}] first: title={title!r} url={url!r} duration={duration!r}")


def _progress_handler(state):
    def on_progress(payload):
        if payload.get("error"):
            state["errors"].append(payload)
            print(f"[download] error: {payload.get('error')}", file=sys.stderr)
            return
        requested = payload.get("requested_quality")
        actual = payload.get("actual_quality")
        warning = payload.get("warning")
        diagnostic = payload.get("diagnostic")
        output_filename = payload.get("output_filename")
        if requested or actual or warning or diagnostic or output_filename:
            print(
                "[download] details:"
                f" requested={requested!r}"
                f" actual={actual!r}"
                f" file={output_filename!r}"
                f" warning={warning!r}"
            )
            if diagnostic:
                print(f"[download] diagnostic: {diagnostic}")
        progress = payload.get("progress")
        speed = payload.get("speed")
        if progress is not None:
            print(f"[download] {progress:.1f}% speed={speed}")
    return on_progress


def _error_handler(state):
    def on_error(payload):
        state["errors"].append(payload)
        print(f"[error] {payload}", file=sys.stderr)
    return on_error


def _playlist_progress():
    def on_progress(current, total):
        total_display = total if total is not None else "unknown"
        print(f"[playlist] {current}/{total_display}")
    return on_progress


def _channel_progress():
    def on_progress(current, total):
        total_display = total if total is not None else "unknown"
        print(f"[channel] {current}/{total_display}")
    return on_progress


def parse_args(argv):
    parser = argparse.ArgumentParser(description="Smoke test yt-channel-downloader core.")
    parser.add_argument(
        "--url",
        default="https://www.youtube.com/watch?v=jNQXAC9IVRw",
        help="Video URL or ID for validation/metadata/download",
    )
    parser.add_argument(
        "--download",
        action="store_true",
        help="Perform a download for the --url target",
    )
    parser.add_argument(
        "--audio-only",
        action="store_true",
        help="Download audio only",
    )
    parser.add_argument(
        "--download-thumbnail",
        action="store_true",
        help="Download thumbnails alongside media",
    )
    parser.add_argument(
        "--download-dir",
        default=str(ROOT / "tmp_downloads"),
        help="Directory for downloads",
    )
    parser.add_argument(
        "--settings-json",
        help="Optional JSON file to override default settings",
    )
    parser.add_argument(
        "--auth-json",
        help="Optional JSON file with yt-dlp auth options",
    )
    parser.add_argument(
        "--proxy-url",
        help="Optional proxy URL passed to yt-dlp",
    )
    parser.add_argument(
        "--skip-validate",
        action="store_true",
        help="Skip URL validation",
    )
    parser.add_argument(
        "--playlist-url",
        help="Optional playlist URL to fetch",
    )
    parser.add_argument(
        "--playlist-limit",
        type=int,
        default=10,
        help="Max playlist items to collect",
    )
    parser.add_argument(
        "--channel-url",
        help="Optional channel URL to fetch",
    )
    parser.add_argument(
        "--channel-limit",
        type=int,
        default=25,
        help="Max channel items to collect",
    )
    return parser.parse_args(argv)


def main(argv=None):
    args = parse_args(argv or sys.argv[1:])
    download_dir = Path(args.download_dir)
    download_dir.mkdir(parents=True, exist_ok=True)

    settings = _build_settings(args)
    auth_opts = _build_auth_opts(args)

    state = {"errors": []}
    client = CoreClient(
        settings=settings,
        auth_opts=auth_opts,
        proxy_url=args.proxy_url,
    )

    if not args.skip_validate:
        valid, normalized = YouTubeURLValidator.is_valid(args.url, auth_opts)
        print(f"[validate] valid={valid} normalized={normalized}")
        if not valid:
            return 1

    print("[metadata] fetching")
    items = client.fetch_video(args.url, on_error=lambda msg: state["errors"].append({"error": msg}))
    _print_item_preview(items, "metadata")

    if args.playlist_url:
        print("[playlist] fetching")
        playlist_items = client.fetch_playlist(
            args.playlist_url,
            limit=args.playlist_limit,
            progress_callback=_playlist_progress(),
            on_error=lambda msg: state["errors"].append({"error": msg}),
        )
        _print_item_preview(playlist_items, "playlist")

    if args.channel_url:
        print("[channel] fetching")
        channel_items = client.fetch_channel(
            args.channel_url,
            limit=args.channel_limit,
            progress_callback=_channel_progress(),
            on_error=lambda msg: state["errors"].append({"error": msg}),
        )
        _print_item_preview(channel_items, "channel")

    if args.download:
        print("[download] starting")
        client.download(
            url=args.url,
            index=0,
            title=(items[0].get("title") if items else "download"),
            on_progress=_progress_handler(state),
            on_error=_error_handler(state),
            on_complete=lambda idx: print(f"[download] complete index={idx}"),
        )

    if state["errors"]:
        print(f"[result] errors={len(state['errors'])}")
        return 1

    print("[result] ok")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
