"""Normalized artwork variants shared by catalog, downloads and large covers."""

import math
import re
from urllib.parse import urlsplit

# Google image hosts serve any square size from the same URL stem, so a larger cover
# never needs the album/song lookups the worker would otherwise make.
RESIZABLE = re.compile(r"^(https://(?:lh\d+\.googleusercontent\.com|yt\d+\.(?:ggpht|googleusercontent)\.com)/[^=?#\s]+)=[a-zA-Z0-9_-]*$")
MAX_RESIZED = 2048
# Requests snap to a few sizes so the same URL repeats across windows, scales and
# songs and is served from the disk cache instead of downloaded again.
SIZE_BUCKETS = (256, 544, 1080, 1440, MAX_RESIZED)


def bucket(pixels):
    pixels = max(1, min(MAX_RESIZED, int(pixels)))
    return next(size for size in SIZE_BUCKETS if size >= pixels)


def variants(value):
    if isinstance(value, dict):
        value = value.get("thumbnails", [])
    if not isinstance(value, list):
        return []
    result = {}
    for row in value[:100]:
        if not isinstance(row, dict):
            continue
        url = row.get("url")
        if not isinstance(url, str) or len(url) > 8192:
            continue
        try:
            parsed = urlsplit(url)
            if parsed.scheme != "https" or not parsed.hostname or parsed.username or parsed.password:
                continue
        except ValueError:
            continue
        size = {}
        for key in ("width", "height"):
            number = row.get(key, 0)
            size[key] = int(number) if isinstance(number, (int, float)) and math.isfinite(number) and 0 < number <= 32768 else 0
        candidate = {"url": url, **size}
        if url not in result or quality(candidate) > quality(result[url]):
            result[url] = candidate
    return list(result.values())


def quality(value):
    return min(value.get("width", 0), value.get("height", 0))


def media_variants(media):
    return variants(list(media.get("artworkVariants") or []) + [
        {"url": media.get("thumbnail", "")}, {"url": media.get("largeThumbnail", "")},
    ])


def resized(values, pixels):
    """Return a square variant of a resizable Google image at the requested size."""
    pixels = bucket(pixels)
    for value in sorted(variants(values), key=quality, reverse=True):
        match = RESIZABLE.match(value["url"])
        if match and (not value.get("width") or not value.get("height") or abs(value["width"] - value["height"]) <= 2):
            return [{"url": f"{match.group(1)}=w{pixels}-h{pixels}-l90-rj", "width": pixels, "height": pixels}]
    return []


def with_resized(values, pixels):
    values = variants(values)
    if quality(max(values, key=quality, default={})) >= pixels:
        return values
    return values + resized(values, pixels)


def choose(values, pixels):
    """Choose the smallest source covering both physical dimensions."""
    values = variants(values)
    adequate = [value for value in values if quality(value) >= pixels]
    return min(adequate, key=quality) if adequate else max(values, key=quality, default={})


def apply_artwork(media, values):
    values = variants(values)
    media["artworkVariants"] = values
    if values:
        media["largeThumbnail"] = max(values, key=quality)["url"]
    return media
