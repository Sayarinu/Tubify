"""Normalize provider lyrics and retain fetched text without requiring offline auth."""

import json
import math
from pathlib import Path
import re
import time

from .media import MediaFiles


class LyricsError(RuntimeError):
    pass


def valid_cached(value, video_id):
    if not isinstance(value, dict) or value.get("videoId") != video_id or not isinstance(value.get("source"), str) or not isinstance(value.get("timed"), bool) or not isinstance(value.get("available"), bool):
        return False
    lines = value.get("lines")
    return isinstance(lines, list) and len(lines) <= 10000 and all(isinstance(row, dict) and isinstance(row.get("text"), str) and all(isinstance(row.get(key), (int, float)) and math.isfinite(row[key]) and row[key] >= -1 for key in ("start", "end")) for row in lines) and sum(len(row["text"]) for row in lines) <= 512 * 1024


def normalize(value, video_id):
    result = {"videoId": video_id, "lines": [], "source": "", "timed": False, "available": False}
    if not isinstance(value, dict):
        return result
    source = value.get("source")
    result["source"] = source if isinstance(source, str) else ""
    raw = value.get("lyrics")
    if isinstance(raw, str):
        lines = [{"text": line, "start": -1., "end": -1.} for line in raw.splitlines()]
    elif isinstance(raw, list):
        lines = []
        for row in raw:
            text = row.get("text") if isinstance(row, dict) else getattr(row, "text", None)
            if not isinstance(text, str):
                continue
            start = row.get("start_time") if isinstance(row, dict) else getattr(row, "start_time", None)
            end = row.get("end_time") if isinstance(row, dict) else getattr(row, "end_time", None)
            valid = all(isinstance(v, (int, float)) and math.isfinite(v) for v in (start, end)) and 0 <= start <= end
            lines.append({"text": text, "start": start / 1000 if valid else -1., "end": end / 1000 if valid else -1.})
        result["timed"] = bool(lines) and all(line["start"] >= 0 for line in lines)
        if result["timed"]:
            lines.sort(key=lambda line: line["start"])
        else:
            for line in lines:
                line["start"], line["end"] = -1., -1.
    else:
        lines = []
    if len(lines) > 10000 or sum(len(line["text"]) for line in lines) > 512 * 1024:
        raise LyricsError("These lyrics are too large to display.")
    result.update(lines=lines, available=any(line["text"].strip() for line in lines))
    return result


class Lyrics:
    def __init__(self, auth, data_dir):
        self.auth = auth
        self.media = MediaFiles(Path(data_dir) / "media")
        self.db = self.media.db
        self.db.execute("CREATE TABLE IF NOT EXISTS lyrics (video_id TEXT PRIMARY KEY, saved REAL NOT NULL, body TEXT NOT NULL)")

    def fetch(self, video_id, refresh=False):
        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise LyricsError("Choose a song to view its lyrics.")
        row = self.db.execute("SELECT saved,body FROM lyrics WHERE video_id=?", (video_id,)).fetchone()
        if row and not refresh:
            try:
                cached = json.loads(row[1])
                if valid_cached(cached, video_id) and (cached["available"] or time.time() - row[0] < 86400):
                    return {**cached, "cached": True}
            except (ValueError, TypeError):
                pass
        client = self.auth.catalog()
        watch = client.get_watch_playlist(videoId=video_id, limit=1)
        browse_id = watch.get("lyrics")
        raw = None
        if browse_id:
            try:
                raw = client.get_lyrics(browse_id, timestamps=True)
            except Exception:
                pass
            if raw is None:
                raw = client.get_lyrics(browse_id, timestamps=False)
        result = normalize(raw, video_id)
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO lyrics VALUES (?, ?, ?)", (video_id, time.time(), json.dumps(result)))
            protected = "AND video_id NOT IN (SELECT video_id FROM media_refs)" if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='media_refs'").fetchone() else ""
            self.db.execute("DELETE FROM lyrics WHERE video_id IN (SELECT video_id FROM lyrics WHERE 1=1 " + protected + " ORDER BY saved DESC LIMIT -1 OFFSET 500)")
        return {**result, "cached": False}

    def close(self):
        self.media.close()
