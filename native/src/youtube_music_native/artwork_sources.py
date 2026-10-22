"""Normalized artwork variants shared by catalog, downloads and large covers."""

import math
from urllib.parse import urlsplit


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
