"""Allowlisted public metadata and current-cover bytes for paired local clients."""
import hashlib
import math
from pathlib import Path
import re
from urllib.parse import unquote, urlsplit
from urllib.request import HTTPRedirectHandler, ProxyHandler, Request, build_opener

from .api_access import ApiError

IMAGE_HOSTS = {'i.ytimg.com', 'img.youtube.com', 'yt3.ggpht.com', 'yt3.googleusercontent.com', 'lh3.googleusercontent.com'}


def text(value, limit=300):
    return ''.join(char for char in value[:limit] if ord(char) >= 32) if isinstance(value, str) else ''


def number(value):
    return float(value) if type(value) in {int, float} and math.isfinite(value) and value >= 0 else 0.


def metadata(track):
    raw_artists = track.get('artists')
    artists = [text(row.get('name')) for row in raw_artists[:20] if isinstance(row, dict)] if isinstance(raw_artists, list) else []
    if not any(artists) and track.get('artist'):
        artists = [text(track['artist'])]
    album = track.get('album') or track.get('albumName') or ''
    identifier = track.get('videoId') or track.get('id')
    identifier = identifier if isinstance(identifier, str) and re.fullmatch('[A-Za-z0-9_-]{11}', identifier) else ''
    return {'videoId': identifier, 'title': text(track.get('title')), 'artists': [name for name in artists if name], 'album': text(album.get('name') if isinstance(album, dict) else album)}


def safe_source(source, artwork_root):
    if not isinstance(source, str) or len(source) > 8192:
        return ''
    try:
        parsed = urlsplit(source)
        if parsed.username or parsed.password or parsed.fragment:
            return ''
        if parsed.scheme == 'https' and parsed.hostname in IMAGE_HOSTS and parsed.port in {None, 443}:
            return source
        if parsed.scheme == 'file' and not parsed.netloc:
            raw_path = unquote(parsed.path)
            # Strip the URI drive prefix before Path normalizes Windows separators.
            if re.match(r'^/[A-Za-z]:/', raw_path):
                raw_path = raw_path[1:]
            path = Path(raw_path).resolve()
            if path.is_relative_to(Path(artwork_root).resolve()):
                return path.as_uri()
    except (ValueError, OSError):
        pass
    return ''


def artwork_key(source):
    return hashlib.sha256(source.encode()).hexdigest()[:24] if source else ''


class NoRedirect(HTTPRedirectHandler):
    def redirect_request(self, *args, **kwargs):
        raise ApiError(502, 'Artwork redirect is unavailable.')


def load_artwork(source, artwork_root):
    source = safe_source(source, artwork_root)
    if not source:
        raise ApiError(404, 'Artwork is unavailable.')
    parsed = urlsplit(source)
    try:
        if parsed.scheme == 'file':
            raw_path = unquote(parsed.path)
            if re.match(r'^/[A-Za-z]:/', raw_path):
                raw_path = raw_path[1:]
            with Path(raw_path).open('rb') as handle:
                body = handle.read(8 * 1024 * 1024 + 1)
        else:
            # No account headers, ambient proxies, arbitrary hosts or redirects.
            opener = build_opener(ProxyHandler({}), NoRedirect())
            with opener.open(Request(source, headers={'User-Agent': 'YouTubeMusicNative/0.1 artwork'}), timeout=5) as response:
                body = response.read(8 * 1024 * 1024 + 1)
    except ApiError:
        raise
    except Exception:
        raise ApiError(502, 'Current artwork could not be read.') from None
    if len(body) > 8 * 1024 * 1024:
        raise ApiError(413, 'Artwork is too large.')
    kind = 'image/png' if body.startswith(b'\x89PNG\r\n\x1a\n') else 'image/jpeg' if body.startswith(b'\xff\xd8\xff') else 'image/gif' if body.startswith((b'GIF87a', b'GIF89a')) else 'image/webp' if body[:4] == b'RIFF' and body[8:12] == b'WEBP' else ''
    if not kind:
        raise ApiError(415, 'Only raster artwork is available.')
    return body, kind


def validate_command(values):
    if not isinstance(values, dict) or not isinstance(values.get('command'), str):
        raise ApiError(400, 'A command is required.')
    command = values['command']
    simple = {'play', 'pause', 'stop', 'toggle', 'next', 'previous', 'mute', 'like', 'dislike', 'cycleRepeat', 'clearQueue', 'show'}
    fields = {'seek': {'position'}, 'volume': {'value'}, 'shuffle': {'value'}, 'repeat': {'mode'}, 'navigate': {'page'}, 'search': {'query'}, 'select': {'key'}, 'remove': {'key'}, 'move': {'key', 'direction'}, 'moveToManual': {'key', 'target', 'after'}, 'openMedia': {'kind', 'id'}, 'playMedia': {'kind', 'id'}, 'enqueue': {'kind', 'id', 'next'}}
    expected = set() if command in simple else fields.get(command)
    if expected is None or set(values) != expected | {'command'}:
        raise ApiError(400, 'Unknown command or invalid command fields.')
    if command in {'seek', 'volume'}:
        key, upper = ('position', 7 * 24 * 3600) if command == 'seek' else ('value', 100)
        if type(values[key]) not in {int, float} or not math.isfinite(values[key]) or not 0 <= values[key] <= upper:
            raise ApiError(400, 'Command value is outside its allowed range.')
    if command == 'shuffle' and type(values['value']) is not bool or command == 'repeat' and (not isinstance(values['mode'], str) or values['mode'] not in {'off', 'one', 'all'}):
        raise ApiError(400, 'Invalid playback mode.')
    if command == 'navigate' and (not isinstance(values['page'], str) or values['page'] not in {'Home', 'Explore', 'Library', 'Downloads'}):
        raise ApiError(400, 'Unknown navigation page.')
    if command == 'search' and (not isinstance(values['query'], str) or not values['query'].strip() or len(values['query']) > 256 or text(values['query'], 256) != values['query']):
        raise ApiError(400, 'Search text must contain 1–256 printable characters.')
    if command in {'select', 'remove', 'move', 'moveToManual'}:
        if not isinstance(values['key'], str) or not re.fullmatch('[A-Za-z0-9_-]{1,128}', values['key']):
            raise ApiError(400, 'Invalid queue occurrence key.')
        if command == 'move' and (type(values['direction']) is not int or values['direction'] not in {-1, 1}):
            raise ApiError(400, 'Queue direction must be -1 or 1.')
        if command == 'moveToManual' and (not isinstance(values['target'], str) or not re.fullmatch('[A-Za-z0-9_-]{0,128}', values['target']) or type(values['after']) is not bool):
            raise ApiError(400, 'Invalid manual queue target.')
    if command in {'openMedia', 'playMedia', 'enqueue'}:
        kinds = {'album', 'playlist', 'artist'} if command == 'openMedia' else {'song', 'album', 'playlist'}
        if not isinstance(values['kind'], str) or values['kind'] not in kinds or not isinstance(values['id'], str) or not re.fullmatch('[A-Za-z0-9_-]{1,256}', values['id']):
            raise ApiError(400, 'Use a supported media kind and identifier.')
        if values['kind'] == 'song' and len(values['id']) != 11:
            raise ApiError(400, 'Song identifiers contain 11 characters.')
        if command == 'enqueue' and type(values['next']) is not bool:
            raise ApiError(400, 'Queue next must be true or false.')
    return command
