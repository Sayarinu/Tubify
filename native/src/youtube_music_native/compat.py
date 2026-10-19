"""Real-account streaming/download proof with a separate native player process."""

import argparse
from functools import partial
import json
import locale
import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile

from .session import SessionError, read_browser_session, read_tauri_session


class ProbeError(RuntimeError):
    pass


FAILURE_MESSAGES = {
    "prerequisites": "Check libmpv, FFmpeg, the JavaScript runtime and Linux network-namespace support.",
    "account": "Reconnect the session and make sure the account has a saved library song.",
    "source_resolution": "Audio extraction failed; reconnect or update the extraction dependencies.",
    "audio_stream": "The resolved audio did not play; check native playback and network access.",
    "download": "The download or media validation failed; check connectivity and free disk space.",
    "offline_restart": "Offline replay failed; check libmpv and Linux network-namespace support.",
}


class QuietLogger:
    def debug(self, message):
        pass

    def warning(self, message):
        pass

    def error(self, message):
        pass


def player_command(offline=False):
    command = [sys.executable, "-m", "youtube_music_native.compat", "play"]
    if offline:
        if sys.platform != "linux" or not shutil.which("unshare"):
            raise ProbeError("Network-isolated proof requires Linux unshare.")
        command = ["unshare", "--user", "--map-root-user", "--net", *command]
    return command


def play_source(source, headers=None, offline=False):
    if offline and not Path(source).is_file():
        raise ProbeError("The downloaded file is missing.")
    # Signed URLs and headers go through stdin, never process arguments or logs.
    result = subprocess.run(
        player_command(offline),
        input=json.dumps({"source": str(source), "headers": headers or []}),
        capture_output=True, text=True, timeout=50,
    )
    if result.returncode != 0:
        raise ProbeError("Native playback did not reach one second.")


def play_child(payload):
    # Never create a YTMusic instance in this process: it changes global locale.
    locale.setlocale(locale.LC_NUMERIC, "C")
    import mpv

    player = mpv.MPV(
        vid="no", vo="null", ao="null", ytdl=False, load_scripts=False,
        config=False, terminal=False, msg_level="all=no",
    )
    try:
        if payload.get("headers"):
            player.http_header_fields = payload["headers"]
        player.play(payload["source"])
        player.wait_for_property("time-pos", lambda value: value is not None and value >= 1, timeout=40)
    finally:
        player.terminate()


def extractor_options(directory):
    runtimes = {}
    for name in ("deno", "node"):
        path = shutil.which(name)
        if path:
            runtimes[name] = {"path": path}
    if not runtimes:
        raise ProbeError("Install Deno or a supported Node.js runtime for YouTube extraction.")
    return {
        "quiet": True, "no_warnings": True, "noprogress": True,
        "logger": QuietLogger(), "format": "bestaudio",
        "socket_timeout": 30, "retries": 1, "fragment_retries": 1,
        "outtmpl": str(directory / "audio.%(ext)s"), "js_runtimes": runtimes,
    }


def validate_media(path):
    result = subprocess.run(
        ["ffprobe", "-v", "error", "-show_entries", "format=duration", "-of", "json", str(path)],
        capture_output=True, text=True, timeout=30, check=True,
    )
    if float(json.loads(result.stdout)["format"]["duration"]) <= 0:
        raise ProbeError("The downloaded media has no playable duration.")


def run_probe(session, directory):
    import requests
    from ytmusicapi import YTMusic
    from yt_dlp import YoutubeDL

    report = {
        "account_access": False, "catalog_access": False, "audio_stream": False,
        "download_validated": False, "offline_restart": False,
        "audio_output": "null", "provider_isolation": "separate process from libmpv",
    }
    stage = "prerequisites"
    try:
        player_command(offline=True)
        if not shutil.which("ffprobe"):
            raise ProbeError("Install FFmpeg and ffprobe first.")
        options = extractor_options(directory)
        stage = "account"
        http = requests.Session()
        http.request = partial(http.request, timeout=30)
        try:
            catalog = YTMusic(auth=session.headers, requests_session=http)
            account = catalog.get_account_info()
            songs = catalog.get_library_songs(limit=1)
            report["account_access"] = bool(account)
            report["catalog_access"] = isinstance(songs, list)
            if not report["account_access"] or not report["catalog_access"]:
                raise ProbeError("The session did not provide authenticated catalog access.")
            video_id = next(song["videoId"] for song in songs if song.get("videoId"))
        finally:
            http.close()
        stage = "source_resolution"
        with YoutubeDL(options) as extractor:
            for cookie in session.cookie_jar():
                extractor.cookiejar.set_cookie(cookie)
            info = extractor.extract_info("https://www.youtube.com/watch?v=" + video_id, download=False)
            if not info or not info.get("url") or info.get("vcodec") != "none":
                raise ProbeError("No audio-only source is available.")
            stage = "audio_stream"
            play_source(info["url"], [f"{k}: {v}" for k, v in info.get("http_headers", {}).items()])
            report["audio_stream"] = True
            stage = "download"
            extractor.process_info(info)
            if info.get("ext") not in {"webm", "m4a", "mp4", "opus", "ogg", "aac", "mp3", "mkv", "flac", "wav"}:
                raise ProbeError("The downloaded audio container is not supported by the probe.")
            media = directory / ("audio." + info["ext"])
            if not media.is_file() or media.stat().st_size == 0:
                raise ProbeError("The download did not produce a completed file.")
            validate_media(media)
            report["download_validated"] = True
            report["download_bytes"] = media.stat().st_size
            report["audio_codec"] = info.get("acodec")
        stage = "offline_restart"
        play_source(media, offline=True)
        report["offline_restart"] = True
        report["network_isolation"] = "new Linux network namespace"
        report["status"] = "passed"
    except Exception as error:
        # Provider exceptions can contain cookies or signed URLs. Do not serialize them.
        message = str(error) if isinstance(error, ProbeError) else FAILURE_MESSAGES[stage]
        report.update(status="failed", failed_stage=stage, error_type=type(error).__name__, message=message)
    return report


def main(argv=None):
    parser = argparse.ArgumentParser(description=__doc__)
    subparsers = parser.add_subparsers(dest="command", required=True)
    check = subparsers.add_parser("check", help="Run the real-account compatibility gate on Linux")
    source = check.add_mutually_exclusive_group(required=True)
    source.add_argument("--tauri-cookies", type=Path, help="Explicitly selected Linux Tauri cookie file")
    source.add_argument("--session", type=Path, help="Explicitly selected browser.json export")
    check.add_argument("--output", type=Path, default=Path(tempfile.gettempdir()))
    subparsers.add_parser("play", help="Internal native playback worker")
    args = parser.parse_args(argv)
    if os.name == "posix":
        import resource

        resource.setrlimit(resource.RLIMIT_CORE, (0, 0))
    try:
        if args.command == "play":
            play_child(json.load(sys.stdin))
            return 0
        session = read_tauri_session(args.tauri_cookies) if args.tauri_cookies else read_browser_session(args.session)
        args.output.mkdir(parents=True, exist_ok=True)
        directory = Path(tempfile.mkdtemp(prefix="youtube-music-proof-", dir=args.output))
        report = run_probe(session, directory)
        report_path = directory / "report.json"
        descriptor = os.open(report_path, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(descriptor, "w") as handle:
            json.dump(report, handle, indent=2)
            handle.write("\n")
        print(json.dumps(report))
        print("Private proof report:", report_path)
        return 0 if report["status"] == "passed" else 1
    except Exception as error:
        message = str(error) if isinstance(error, (SessionError, ProbeError)) else "Check the selected session and native playback prerequisites."
        print(json.dumps({"status": "failed", "failed_stage": "import_or_playback", "error_type": type(error).__name__, "message": message}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
