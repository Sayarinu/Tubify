"""Read a local audio file's tags and embedded picture without changing the file."""

import base64
import json
from pathlib import Path
import re
import subprocess

from ..compat import hidden_window

# Formats the playback backend decodes. Files are listed by extension, then their tags are read.
EXTENSIONS = {"mp3", "m4a", "m4b", "mp4", "aac", "flac", "ogg", "oga", "opus", "wav", "aif", "aiff", "aifc",
              "wma", "ape", "wv", "mpc", "tta", "dsf", "mka", "webm"}
# Embedded pictures larger than this are ignored rather than read into memory.
PICTURE_LIMIT = 16 * 1024 * 1024

# Readable names for the codecs mutagen reports.
CODECS = {"MP3": "MP3", "FLAC": "FLAC", "OggVorbis": "Vorbis", "OggOpus": "Opus", "OggFLAC": "FLAC", "OggSpeex": "Speex",
          "WAVE": "WAV", "AIFF": "AIFF", "ASF": "WMA", "MonkeysAudio": "APE", "WavPack": "WavPack",
          "Musepack": "Musepack", "TrueAudio": "TTA", "DSF": "DSD", "AAC": "AAC"}

ID3_KEYS = {"title": "TIT2", "artist": "TPE1", "album": "TALB", "albumArtist": "TPE2", "track": "TRCK", "disc": "TPOS", "year": "TDRC"}
MP4_KEYS = {"title": "\xa9nam", "artist": "\xa9ART", "album": "\xa9alb", "albumArtist": "aART", "track": "trkn", "disc": "disk", "year": "\xa9day"}
VORBIS_KEYS = {"title": "title", "artist": "artist", "album": "album", "albumArtist": "albumartist", "track": "tracknumber", "disc": "discnumber", "year": "date"}
APE_KEYS = {"title": "Title", "artist": "Artist", "album": "Album", "albumArtist": "Album Artist", "track": "Track", "disc": "Disc", "year": "Year"}
ASF_KEYS = {"title": "Title", "artist": "Author", "album": "WM/AlbumTitle", "albumArtist": "WM/AlbumArtist", "track": "WM/TrackNumber", "disc": "WM/PartOfSet", "year": "WM/Year"}


def _text(value):
    """One tag value as plain text; several values are joined."""
    if value is None:
        return ""
    if isinstance(value, (list, tuple)):
        values = [_text(item) for item in value]
        return ", ".join(item for item in values if item)
    if hasattr(value, "text") and not isinstance(value, str):
        return _text(value.text)
    if hasattr(value, "value") and not isinstance(value, (str, bytes)):
        return _text(value.value)
    if isinstance(value, bytes):
        value = value.decode("utf-8", "replace")
    return " ".join(str(value).replace("\0", " ").split())[:1024]


def _number(value):
    """A track or disc number from "3", "3/12" or mutagen's (3, 12) pair."""
    if isinstance(value, list) and value:
        value = value[0]
    if isinstance(value, tuple):
        value = value[0] if value else 0
    match = re.match(r"\s*(\d+)", _text(value))
    number = int(match.group(1)) if match else 0
    return number if 0 < number < 10000 else 0


def _year(value):
    match = re.search(r"(1[0-9]{3}|20[0-9]{2})", _text(value))
    return int(match.group(1)) if match else 0


def _values(tags, keys, read):
    found = {name: read(tags, key) for name, key in keys.items()}
    return {
        "title": _text(found["title"]), "artist": _text(found["artist"]), "album": _text(found["album"]),
        "albumArtist": _text(found["albumArtist"]), "track": _number(found["track"]), "disc": _number(found["disc"]),
        "year": _year(found["year"]),
    }


def _get(tags, key):
    try:
        return tags[key] if key in tags else None
    except (KeyError, ValueError, TypeError):
        return None


def _vorbis_get(tags, key):
    try:
        values = tags.get(key) or tags.get(key.upper())
    except (KeyError, ValueError, TypeError):
        return None
    if not values and key == "albumartist":
        values = tags.get("album artist") or tags.get("ALBUM ARTIST")
    return values


def _picture_bytes(data):
    return bytes(data) if data and len(data) <= PICTURE_LIMIT else b""


def _id3_picture(tags):
    pictures = [frame for key, frame in tags.items() if key.startswith("APIC")]
    # Prefer the front cover, then any picture.
    pictures.sort(key=lambda frame: getattr(frame, "type", 0) != 3)
    return next((_picture_bytes(frame.data) for frame in pictures if getattr(frame, "data", None)), b"")


def _flac_picture(audio):
    pictures = sorted(getattr(audio, "pictures", []) or [], key=lambda picture: picture.type != 3)
    return next((_picture_bytes(picture.data) for picture in pictures if picture.data), b"")


def _ogg_picture(tags):
    from mutagen.flac import Picture

    for raw in _vorbis_get(tags, "metadata_block_picture") or []:
        try:
            if len(raw) > PICTURE_LIMIT * 4 // 3 + 4:
                continue
            data = Picture(base64.b64decode(raw)).data
        except Exception:
            continue
        if data:
            return _picture_bytes(data)
    return b""


def _ape_picture(tags):
    item = _get(tags, "Cover Art (Front)")
    value = bytes(getattr(item, "value", b"") or b"")
    # APEv2 binary covers start with a filename and a NUL.
    return _picture_bytes(value.split(b"\0", 1)[1]) if b"\0" in value else b""


def _codec(audio):
    name = type(audio).__name__
    if name in {"MP4", "EasyMP4"}:
        codec = str(getattr(audio.info, "codec", "")).lower()
        return "ALAC" if codec.startswith("alac") else "AAC" if codec.startswith("mp4a") else codec.upper()[:16]
    return CODECS.get(name.replace("Easy", ""), name[:16])


def read_with_mutagen(path):
    """Tags, duration, codec and embedded picture, or None if mutagen can't read the file."""
    import mutagen

    try:
        audio = mutagen.File(str(path))
    except Exception:
        return None
    if audio is None or getattr(audio, "info", None) is None:
        return None
    tags, picture = audio.tags, b""
    name = type(audio).__name__
    values = {key: "" for key in ("title", "artist", "album", "albumArtist")} | {"track": 0, "disc": 0, "year": 0}
    try:
        if tags is None:
            pass
        elif name in {"MP4"}:
            values = _values(tags, MP4_KEYS, _get)
            covers = _get(tags, "covr") or []
            picture = next((_picture_bytes(cover) for cover in covers if cover), b"")
        elif name == "ASF":
            values = _values(tags, ASF_KEYS, _get)
        elif hasattr(tags, "getall") and hasattr(tags, "version"):
            # ID3, used by MP3, AIFF, WAV and DSF.
            values = _values(tags, ID3_KEYS, _get)
            picture = _id3_picture(tags)
        elif name in {"MonkeysAudio", "WavPack", "Musepack", "TrueAudio", "OptimFROG"} or type(tags).__name__ == "APEv2":
            values = _values(tags, APE_KEYS, _get)
            picture = _ape_picture(tags)
        else:
            # Vorbis comments: FLAC, Ogg Vorbis, Opus, Speex.
            values = _values(tags, VORBIS_KEYS, _vorbis_get)
            picture = _flac_picture(audio) if name == "FLAC" else _ogg_picture(tags)
    except Exception:
        return {"tagsReadable": False, "duration": float(getattr(audio.info, "length", 0) or 0), "codec": _codec(audio), "picture": b"",
                "sampleRate": int(getattr(audio.info, "sample_rate", 0) or 0)}
    return {**values, "tagsReadable": True, "duration": float(getattr(audio.info, "length", 0) or 0), "codec": _codec(audio),
            "sampleRate": int(getattr(audio.info, "sample_rate", 0) or 0), "picture": picture}


def read_with_ffprobe(path):
    """Tags and duration from FFmpeg, for containers mutagen can't read (such as Matroska and WebM)."""
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries",
                                 "format=duration:format_tags:stream=codec_name,sample_rate:stream_tags", "-of", "json", str(path)],
                                capture_output=True, text=True, timeout=20, check=True, **hidden_window())
        media = json.loads(result.stdout)
    except (OSError, subprocess.SubprocessError, ValueError):
        return None
    streams = media.get("streams") or []
    if not streams:
        return None
    tags = {str(key).lower(): value for key, value in {**(streams[0].get("tags") or {}), **((media.get("format") or {}).get("tags") or {})}.items()}
    try:
        duration = float((media.get("format") or {}).get("duration") or 0)
    except (TypeError, ValueError):
        duration = 0.
    codec = str(streams[0].get("codec_name", "")).upper()[:16]
    return {"title": _text(tags.get("title")), "artist": _text(tags.get("artist")), "album": _text(tags.get("album")),
            "albumArtist": _text(tags.get("album_artist") or tags.get("albumartist")), "track": _number(tags.get("track")),
            "disc": _number(tags.get("disc")), "year": _year(tags.get("date") or tags.get("year")),
            "tagsReadable": True, "duration": duration, "codec": {"VORBIS": "Vorbis", "OPUS": "Opus"}.get(codec, codec),
            "sampleRate": int(streams[0].get("sample_rate") or 0), "picture": b""}


def read(path):
    """A file's metadata. A file nothing can read is still listed under its file name, marked as unreadable."""
    path = Path(path)
    values = read_with_mutagen(path) or read_with_ffprobe(path)
    if values is None:
        values = {"title": "", "artist": "", "album": "", "albumArtist": "", "track": 0, "disc": 0, "year": 0,
                  "tagsReadable": False, "duration": 0., "codec": path.suffix[1:].upper()[:16], "sampleRate": 0, "picture": b""}
    if not values["title"]:
        values["title"] = path.stem[:1024]
    if values["duration"] != values["duration"] or values["duration"] < 0:
        values["duration"] = 0.
    return values
