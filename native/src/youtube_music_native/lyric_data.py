"""Normalize provider lyrics and retain fetched text without requiring offline auth."""

import hashlib
import json
import math
from pathlib import Path
import re
import time

from .media import MediaFiles
from .lyric_options import clean_options
from .lyric_providers import Providers, ProviderUnavailable, track_identity


class LyricsError(RuntimeError):
    pass


def valid_cached(value, video_id):
    if not isinstance(value, dict) or value.get("videoId") != video_id or not isinstance(value.get("source"), str) or not isinstance(value.get("timed"), bool) or not isinstance(value.get("available"), bool):
        return False
    lines = value.get("lines")
    if isinstance(lines, list):
        for line in lines:
            if not isinstance(line, dict):
                return False
            words = line.get("words", [])
            if not isinstance(words, list) or len(words) > 30000:
                return False
            for word in words:
                if not isinstance(word, dict) or not isinstance(word.get("text"), str) or not isinstance(word.get("offset"), int):
                    return False
                if any(not isinstance(word.get(key), (int, float)) or not math.isfinite(word[key]) for key in ("start", "end")):
                    return False
                if not 0 <= word["offset"] <= len(line.get("text", "")) or line.get("text", "")[word["offset"]:word["offset"] + len(word["text"])] != word["text"]:
                    return False
                if not all(isinstance(line.get(key), (int, float)) for key in ("start", "end")) or not line["start"] <= word["start"] < word["end"] <= line["end"]:
                    return False
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
    def __init__(self, auth, data_dir, providers=None):
        self.auth = auth
        self.data_dir = Path(data_dir)
        self.providers = providers if providers is not None else Providers()
        self.media = MediaFiles(Path(data_dir) / "media")
        self.db = self.media.db
        self.db.execute("CREATE TABLE IF NOT EXISTS lyrics (video_id TEXT PRIMARY KEY, saved REAL NOT NULL, body TEXT NOT NULL)")
        self.db.execute("CREATE TABLE IF NOT EXISTS lyric_variants (video_id TEXT NOT NULL, signature TEXT NOT NULL, saved REAL NOT NULL, body TEXT NOT NULL, PRIMARY KEY(video_id,signature))")

    def fetch(self, video_id, refresh=False, track=None, options=None):
        options = clean_options(options)
        if not options["external"] and not options["captions"]:
            return self._native(video_id, refresh)
        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise LyricsError("Choose a song to view its lyrics.")
        track = track if isinstance(track, dict) else {}
        native_row = self.db.execute("SELECT body FROM lyrics WHERE video_id=?", (video_id,)).fetchone()
        if native_row and not refresh:
            try:
                native_cached = json.loads(native_row[0])
                if valid_cached(native_cached, video_id) and native_cached["timed"]:
                    return {**native_cached, "cached": True, "provider": "native", "syncLevel": "line", "source": native_cached["source"] or "YouTube Music"}
            except (ValueError, TypeError):
                pass
        lookup = {key: options[key] for key in ("external", "captions", "approximate", "providers")}
        signature = hashlib.sha256(json.dumps([track_identity(track), lookup], sort_keys=True).encode()).hexdigest()
        row = self.db.execute("SELECT saved,body FROM lyric_variants WHERE video_id=? AND signature=?", (video_id, signature)).fetchone()
        if row and not refresh:
            try:
                cached = json.loads(row[1])
                if valid_cached(cached, video_id) and (cached["available"] or time.time() - row[0] < 86400):
                    return {**cached, "cached": True}
            except (ValueError, TypeError):
                pass
        notes, fallback = [], None
        try:
            native = self._native(video_id, refresh)
            if native["timed"]:
                return native
            fallback = native
        except Exception:
            notes.append("Native lyrics are unavailable.")
        result = None
        deadline = time.monotonic() + 20
        if options["external"]:
            for choice in options["providers"]:
                if not choice["enabled"] or time.monotonic() >= deadline:
                    continue
                try:
                    value = self.providers.fetch(choice["id"], video_id, track, options["approximate"])
                    if value["timed"]:
                        result = value
                        break
                    if fallback is None or not fallback["available"]:
                        fallback = value
                except ProviderUnavailable as error:
                    notes.append(choice["id"] + ": " + str(error))
                except Exception:
                    notes.append(choice["id"] + ": Invalid lyric data; trying another source.")
        if result is None and options["captions"]:
            try:
                caption = self.providers.captions(self.auth, video_id, track, self.data_dir)
                if caption["available"]:
                    result = caption
            except ProviderUnavailable as error:
                notes.append(str(error))
            except Exception:
                notes.append("Human captions are unavailable for this song.")
        result = result or fallback or normalize(None, video_id)
        result = {**result, "provider": result.get("provider", "native"), "syncLevel": result.get("syncLevel", "line" if result["timed"] else "plain"), "status": " ".join(notes), "cached": bool(result.get("cached"))}
        if not valid_cached(result, video_id):
            raise LyricsError("These lyrics could not be displayed.")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO lyric_variants VALUES (?, ?, ?, ?)", (video_id, signature, time.time(), json.dumps(result)))
            protected = "AND video_id NOT IN (SELECT video_id FROM media_refs)" if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='media_refs'").fetchone() else ""
            self.db.execute("DELETE FROM lyric_variants WHERE rowid IN (SELECT rowid FROM lyric_variants WHERE 1=1 " + protected + " ORDER BY saved DESC LIMIT -1 OFFSET 500)")
        return result

    def _native(self, video_id, refresh=False):
        if not isinstance(video_id, str) or not re.fullmatch(r"[A-Za-z0-9_-]{11}", video_id):
            raise LyricsError("Choose a song to view its lyrics.")
        row = self.db.execute("SELECT saved,body FROM lyrics WHERE video_id=?", (video_id,)).fetchone()
        if row and not refresh:
            try:
                cached = json.loads(row[1])
                if valid_cached(cached, video_id) and (cached["available"] or time.time() - row[0] < 86400):
                    return {**cached, "cached": True, "provider": "native", "syncLevel": "line" if cached["timed"] else "plain", "source": cached["source"] or "YouTube Music"}
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
        result.update(provider="native", syncLevel="line" if result["timed"] else "plain", source=result["source"] or "YouTube Music")
        with self.db:
            self.db.execute("INSERT OR REPLACE INTO lyrics VALUES (?, ?, ?)", (video_id, time.time(), json.dumps(result)))
            protected = "AND video_id NOT IN (SELECT video_id FROM media_refs)" if self.db.execute("SELECT 1 FROM sqlite_master WHERE name='media_refs'").fetchone() else ""
            self.db.execute("DELETE FROM lyrics WHERE video_id IN (SELECT video_id FROM lyrics WHERE 1=1 " + protected + " ORDER BY saved DESC LIMIT -1 OFFSET 500)")
        return {**result, "cached": False}

    def close(self):
        self.media.close()
