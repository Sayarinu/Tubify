"""Resolve large covers in a worker; downloaded artwork upgrades are atomic."""

import hashlib
import json
import os
from pathlib import Path
import tempfile

from PySide6.QtCore import QUrl
from PySide6.QtGui import QImageReader

from .artwork_sources import apply_artwork, choose, media_variants, quality, variants
from .downloads import DownloadStore, VIDEO_ID, cache_artwork


def local_image(url):
    parsed = QUrl(url)
    if not parsed.isLocalFile():
        return {}
    size = QImageReader(parsed.toLocalFile()).size()
    return {"url": url, "width": size.width(), "height": size.height()} if size.isValid() else {}


def resolve(auth, data_dir, media, pixels, online, fetch=cache_artwork):
    video_id = media.get("videoId") or media.get("id", "")
    if not isinstance(video_id, str) or not VIDEO_ID.fullmatch(video_id):
        return {}
    pixels = max(1, min(4096, int(pixels)))
    store = DownloadStore(data_dir)
    try:
        values = media_variants(media)
        local, downloaded = {}, False
        for raw, in store.db.execute("SELECT body FROM collections"):
            body = json.loads(raw)
            for track in body["items"]:
                if track["videoId"] != video_id:
                    continue
                downloaded = True
                values += media_variants(track)
                image = local_image(store._artwork_uri(track.get("localThumbnail", "")))
                if quality(image) > quality(local):
                    local = image
        if quality(local) >= pixels or not online:
            return {"videoId": video_id, **local}
        chosen = choose(values, pixels)
        if quality(chosen) < pixels:
            try:
                client = auth.catalog()
                album = media.get("album")
                album_id = album.get("id") if isinstance(album, dict) else None
                if album_id:
                    try:
                        values += variants(client.get_album(album_id).get("thumbnails"))
                    except Exception:
                        pass
                if quality(choose(values, pixels)) < pixels:
                    song = client.get_song(video_id).get("videoDetails", {})
                    if song.get("videoId") == video_id:
                        values += variants(song.get("thumbnail"))
            except Exception:
                pass
            chosen = choose(values, pixels)
        if not chosen or local and quality(local) >= quality(chosen) and quality(chosen) > 0:
            return {"videoId": video_id, **local}
        if not downloaded:
            # QML's existing 128 MiB URL cache owns replaceable, online artwork.
            return {"videoId": video_id, **chosen}
        staging = store.root / "staging"
        staging.mkdir(exist_ok=True)
        with tempfile.TemporaryDirectory(prefix="artwork-", dir=staging) as temporary:
            image = local_image(fetch(chosen["url"], Path(temporary)))
            if quality(image) <= quality(local):
                return {"videoId": video_id, **local}
            folder = store.root / "artwork"
            folder.mkdir(exist_ok=True)
            target = folder / (hashlib.sha256(chosen["url"].encode()).hexdigest() + ".image")
            # The file and fresh references publish under the same write lock used
            # by collection removal/GC. A removed download is never recreated.
            with store.db:
                store.db.execute("BEGIN IMMEDIATE")
                updates = []
                for identifier, raw in store.db.execute("SELECT id,body FROM collections"):
                    body = json.loads(raw)
                    matching = [track for track in body["items"] if track["videoId"] == video_id]
                    if not matching:
                        continue
                    for track in matching:
                        current = local_image(store._artwork_uri(track.get("localThumbnail", "")))
                        if quality(current) > quality(image):
                            return {"videoId": video_id, **current}
                        track["localThumbnail"] = target.as_uri()
                        apply_artwork(track, media_variants(track) + values)
                    updates.append((json.dumps(body), identifier))
                if not updates:
                    return {"videoId": video_id}
                os.replace(QUrl(image["url"]).toLocalFile(), target)
                store.db.executemany("UPDATE collections SET body=? WHERE id=?", updates)
            return {"videoId": video_id, **image, "url": target.as_uri(), "upgraded": True}
    finally:
        store.close()
