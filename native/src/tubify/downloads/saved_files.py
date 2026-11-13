"""Save downloaded songs as tagged audio files in a folder the person chose.

The audio is copied without re-encoding. A saved file belongs to the person: Tubify never
overwrites, moves or deletes one, and removing a download leaves it in place.
"""

import base64
import json
import os
from pathlib import Path
import re
import subprocess

from ..compat import hidden_window

# Container and extension for each codec Tubify downloads, so the copy needs no re-encoding.
CONTAINERS = {"opus": ("opus", "ogg"), "vorbis": ("ogg", "ogg"), "aac": ("m4a", "ipod"), "alac": ("m4a", "ipod"),
              "mp3": ("mp3", "mp3"), "flac": ("flac", "flac")}
FALLBACK = ("mka", "matroska")
RESERVED = {"CON", "PRN", "AUX", "NUL", *(f"COM{number}" for number in range(1, 10)), *(f"LPT{number}" for number in range(1, 10))}
NAME_LIMIT = 120


class SaveError(RuntimeError):
    pass


def safe_name(value, fallback):
    """A file or folder name that is valid on Windows, macOS and Linux."""
    text = re.sub(r'[\x00-\x1f<>:"/\\|?*]', " ", str(value or ""))
    text = " ".join(text.split()).strip(" .")[:NAME_LIMIT].strip(" .")
    if not text or text.upper().split(".")[0] in RESERVED:
        text = (fallback + " " + text).strip() if text else fallback
    return text


def default_folder():
    from PySide6.QtCore import QStandardPaths

    music = QStandardPaths.writableLocation(QStandardPaths.StandardLocation.MusicLocation) or str(Path.home() / "Music")
    return str(Path(music) / "Tubify")


def primary_artist(track):
    artists = [artist.get("name", "") for artist in track.get("artists") or [] if isinstance(artist, dict) and artist.get("name")]
    return artists[0] if artists else str(track.get("artist") or "").split(" • ")[0]


def relative_path(track, number, extension):
    """Artist/Album/NN Title.ext, or Artist/Title.ext for a song without an album."""
    artist = safe_name(primary_artist(track), "Unknown artist")
    album = (track.get("album") or {}).get("name", "") if isinstance(track.get("album"), dict) else ""
    title = safe_name(track.get("title"), "Untitled")
    name = (f"{number:02} " if number else "") + title
    parts = [artist] + ([safe_name(album, "Unknown album")] if album else []) + [name + "." + extension]
    return Path(*parts)


def codec(path):
    try:
        result = subprocess.run(["ffprobe", "-v", "error", "-select_streams", "a:0", "-show_entries", "stream=codec_name", "-of", "json", str(path)],
                                capture_output=True, text=True, timeout=30, check=True, **hidden_window())
        return str((json.loads(result.stdout).get("streams") or [{}])[0].get("codec_name", "")).lower()
    except (OSError, subprocess.SubprocessError, ValueError, IndexError):
        return ""


def jpeg(image_path):
    """A cover as JPEG bytes, whatever format the cached artwork is in."""
    if not image_path:
        return b""
    from PySide6.QtCore import QBuffer, QByteArray, QIODevice
    from PySide6.QtGui import QImage

    image = QImage(str(image_path))
    if image.isNull():
        return b""
    data = QByteArray()
    buffer = QBuffer(data)
    buffer.open(QIODevice.OpenModeFlag.WriteOnly)
    image.save(buffer, "JPG", 92)
    return bytes(data.data())


def embed_cover(path, extension, cover):
    if not cover:
        return
    if extension in {"opus", "ogg"}:
        from mutagen import File
        from mutagen.flac import Picture

        audio = File(str(path))
        picture = Picture()
        picture.type, picture.mime, picture.data = 3, "image/jpeg", cover
        audio["metadata_block_picture"] = [base64.b64encode(picture.write()).decode("ascii")]
        audio.save()
    elif extension == "m4a":
        from mutagen.mp4 import MP4, MP4Cover

        audio = MP4(str(path))
        audio["covr"] = [MP4Cover(cover, imageformat=MP4Cover.FORMAT_JPEG)]
        audio.save()
    elif extension == "mp3":
        from mutagen.id3 import APIC, ID3, ID3NoHeaderError

        try:
            tags = ID3(str(path))
        except ID3NoHeaderError:
            tags = ID3()
        tags.add(APIC(encoding=3, mime="image/jpeg", type=3, desc="Cover", data=cover))
        tags.save(str(path))
    elif extension == "flac":
        from mutagen.flac import FLAC, Picture

        audio = FLAC(str(path))
        picture = Picture()
        picture.type, picture.mime, picture.data = 3, "image/jpeg", cover
        audio.add_picture(picture)
        audio.save()


def place(temporary, target):
    """Give the finished file its name without replacing anything already there."""
    stem, suffix = target.stem, target.suffix
    for attempt in range(1, 1000):
        candidate = target if attempt == 1 else target.with_name(f"{stem} ({attempt}){suffix}")
        try:
            os.link(temporary, candidate)
        except FileExistsError:
            continue
        except OSError:
            # File systems without hard links (such as FAT and exFAT): check, then rename.
            if candidate.exists():
                continue
            os.replace(temporary, candidate)
            return candidate
        temporary.unlink(missing_ok=True)
        return candidate
    raise SaveError("A file with this song's name already exists. Rename or move it and retry.")


def save(source, track, folder, number=0, cover_image=""):
    """Copy a downloaded song into folder as a tagged file and return its path."""
    found = codec(source)
    extension, container = CONTAINERS.get(found, FALLBACK)
    folder = Path(folder)
    target = folder / relative_path(track, number, extension)
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
    except OSError:
        raise SaveError(f"Tubify can't save files in {folder}. Choose another folder in Settings.") from None
    # Hidden and ending in .part, so Local Music skips it until it is complete.
    temporary = target.with_name("." + target.name + ".part")
    album = (track.get("album") or {}).get("name", "") if isinstance(track.get("album"), dict) else ""
    tags = {"title": track.get("title", ""), "artist": track.get("artist", "") or primary_artist(track), "album": album,
            "album_artist": primary_artist(track) if album else "", "track": str(number) if number else ""}
    command = ["ffmpeg", "-v", "error", "-nostdin", "-y", "-i", str(source), "-map", "0:a:0", "-c", "copy", "-map_metadata", "-1"]
    for key, value in tags.items():
        if value:
            command += ["-metadata", f"{key}={value}"]
    command += ["-f", container, str(temporary)]
    try:
        subprocess.run(command, capture_output=True, timeout=600, check=True, **hidden_window())
        try:
            embed_cover(temporary, extension, jpeg(cover_image))
        except Exception:
            # The song is still worth keeping without its cover.
            pass
        return place(temporary, target)
    except OSError as error:
        if getattr(error, "errno", None) == 28:
            raise
        raise SaveError(f"Tubify can't save files in {folder}. Choose another folder in Settings.") from None
    except subprocess.SubprocessError:
        raise SaveError("This song's audio file couldn't be saved. Retry.") from None
    finally:
        temporary.unlink(missing_ok=True)
